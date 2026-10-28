"""Meaningful selected-file, immutable history, hostile text and UI behavior checks."""
import copy
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
SCRIPTS = BASE / 'skills' / 'atlas' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import navigator as nav


class NavigatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.inputs = self.base / 'input'
        shutil.copytree(BASE / 'examples/synthetic', self.inputs)
        self.out = self.base / 'output'
        self.m = json.loads((self.inputs / 'DOCS_INDEX.json').read_text())
        self.m['release']['previous'] = None
        self.m['release']['id'] = 'DEMO-TEST.1'
        self.save()

    def save(self):
        (self.inputs / 'DOCS_INDEX.json').write_bytes(nav.canonical(self.m))

    def load(self):
        self.save(); return nav.load(self.inputs, 'DOCS_INDEX.json')

    def build(self):
        self.save(); return nav.build(self.inputs, 'DOCS_INDEX.json', self.out)

    def next(self, previous):
        self.m['release']['id'] = 'DEMO-20261017.2'
        self.m['release']['previous'] = previous

    def test_exact_selected_docs_and_no_input_writes(self):
        before = {p.name: p.read_bytes() for p in self.inputs.iterdir()}
        s = nav.load(self.inputs, 'DOCS_INDEX.json')
        self.assertEqual(len(s['documents']), 5)
        nav.build(self.inputs, 'DOCS_INDEX.json', self.out)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.inputs.iterdir()})

    def test_idempotent_current_readback(self):
        a = self.build(); b = self.build()
        self.assertEqual(a['manifest_sha256'], b['manifest_sha256'])
        self.assertEqual(b['status'], 'RECONCILED_IDENTICAL')
        nav.verify_release(self.out, a['release'], a['manifest_sha256'])

    def test_next_preserves_first_release(self):
        a = self.build(); first = self.out / 'releases' / a['release']
        before = {p.name: p.read_bytes() for p in first.iterdir()}
        self.next(a['manifest_sha256']); self.m['documents'][0]['lifecycle'] = 'archived'
        self.m['history'].append({'id':'TEST-ARCHIVE-APPEND','at':self.m['release']['created_at'],'kind':'ARCHIVED','summary':'Example document retained in the archive','entity_ids':['doc.project']})
        b = self.build(); self.assertEqual(b['status'], 'BUILT_LOCAL')
        self.assertEqual(before, {p.name: p.read_bytes() for p in first.iterdir()})
        self.assertEqual(json.loads((self.out/'CURRENT.json').read_text())['release'], b['release'])

    def test_same_release_collision(self):
        self.build(); self.m['modules'][0]['purpose'] = 'changed'
        with self.assertRaisesRegex(nav.Invalid, 'RELEASE_COLLISION'): self.build()

    def test_wrong_previous(self):
        self.build(); self.next('0'*64)
        with self.assertRaisesRegex(nav.Invalid, 'EXPECTED_PREVIOUS'): self.build()

    def test_orphan_reconciles_without_pointer_activation(self):
        self.build(); (self.out/'CURRENT.json').unlink()
        with self.assertRaisesRegex(nav.Invalid, 'ORPHAN_RECONCILE_ONLY'): self.build()
        self.assertFalse((self.out/'CURRENT.json').exists())

    def test_failure_after_release_before_pointer_is_not_replayed(self):
        with patch.object(nav.os, 'replace', side_effect=OSError('synthetic pointer failure')):
            with self.assertRaises(OSError): self.build()
        self.assertTrue((self.out/'releases'/self.m['release']['id']/'MANIFEST.json').is_file())
        self.assertFalse((self.out/'CURRENT.json').exists())
        with self.assertRaisesRegex(nav.Invalid, 'ORPHAN_RECONCILE_ONLY'): self.build()
        self.assertFalse((self.out/'CURRENT.json').exists())

    def test_corrupt_output_detected_before_reuse(self):
        a = self.build(); (self.out/'releases'/a['release']/'index.html').write_text('tampered')
        with self.assertRaisesRegex(nav.Invalid, 'OUTPUT_FILE_HASH'): self.build()

    def test_extra_output_member_is_not_accepted(self):
        a=self.build();(self.out/'releases'/a['release']/'extra.txt').write_text('unlisted')
        with self.assertRaisesRegex(nav.Invalid,'OUTPUT_EXTRA_OR_LINKED_MEMBER'):self.build()

    def test_lock_is_not_overridden(self):
        self.out.mkdir(); (self.out/'.writer.lock').write_text('existing')
        with self.assertRaisesRegex(nav.Invalid, 'WRITER_LOCK'): self.build()
        self.assertEqual((self.out/'.writer.lock').read_text(), 'existing')

    def test_selected_hash_mismatch(self):
        (self.inputs/'PROJECT.md').write_text('changed')
        with self.assertRaisesRegex(nav.Invalid, 'DOCUMENT_HASH'): self.load()

    def test_traversal_is_rejected(self):
        self.m['documents'][0]['path']='../secret.md'
        with self.assertRaisesRegex(nav.Invalid, 'UNSAFE_PATH'): self.load()

    def test_document_symlink_is_rejected(self):
        (self.inputs/'PROJECT.md').unlink(); (self.base/'outside.md').write_text('outside')
        (self.inputs/'PROJECT.md').symlink_to(self.base/'outside.md')
        with self.assertRaisesRegex(nav.Invalid, 'SYMLINK_PATH'): self.load()

    def test_ancestor_symlink_is_rejected(self):
        (self.inputs/'alias').symlink_to(self.base, target_is_directory=True)
        self.m['documents'][0]['path']='alias/secret.md'
        with self.assertRaisesRegex(nav.Invalid, 'SYMLINK_PATH'): self.load()

    def test_output_symlink_is_rejected(self):
        self.out.symlink_to(self.inputs, target_is_directory=True)
        with self.assertRaisesRegex(nav.Invalid, 'OUTPUT_SYMLINK'): self.build()

    def test_duplicate_json_keys(self):
        (self.inputs/'DOCS_INDEX.json').write_text('{"schema":1,"schema":2}')
        with self.assertRaisesRegex(nav.Invalid, 'DUPLICATE_JSON_KEY'): nav.load(self.inputs,'DOCS_INDEX.json')

    def test_duplicate_entity_ids(self):
        self.m['modules'][0]['id']='doc.project'
        with self.assertRaisesRegex(nav.Invalid, 'DUPLICATE_ID'): self.load()

    def test_dangling_entity_edge(self):
        self.m['relations'][0]['to']='absent'
        with self.assertRaisesRegex(nav.Invalid, 'DANGLING:relation'): self.load()

    def test_unproven_relation_cannot_hide_missing_docs(self):
        self.m['relations'][0]['evidence_docs']=[]
        with self.assertRaisesRegex(nav.Invalid, 'SCHEMA_ARRAY:input.relations'): self.load()

    def test_dangling_matrix_step(self):
        self.m['bindings'][0]['step_ids']=['absent']
        with self.assertRaisesRegex(nav.Invalid, 'DANGLING:binding.steps'): self.load()

    def test_dangling_matrix_event(self):
        self.m['bindings'][0]['event_ids']=['absent']
        with self.assertRaisesRegex(nav.Invalid, 'DANGLING:binding.events'): self.load()

    def test_unknown_states_and_bad_field_types_rejected(self):
        self.m['contracts'][0]['module'] = []
        with self.assertRaisesRegex(nav.Invalid, 'SCHEMA_STRING'): self.load()
        self.m['contracts'][0]['module']='module.planner'; self.m['documents'][0]['execution']='RUNNING'
        with self.assertRaisesRegex(nav.Invalid, 'SCHEMA_ENUM'): self.load()

    def test_multiple_current_contract_versions_rejected(self):
        self.m['contracts'][0]['lifecycle']='current'
        with self.assertRaisesRegex(nav.Invalid, 'MULTIPLE_CURRENT_CONTRACT'): self.load()

    def test_readback_future_relative_to_release_rejected(self):
        self.m['documents'][0]['readback_at']='2099-01-01T00:00:00Z'
        with self.assertRaisesRegex(nav.Invalid, 'READBACK_AFTER_RELEASE'): self.load()

    def test_history_rewrite(self):
        a=self.build(); self.next(a['manifest_sha256']); self.m['history'][0]['summary']='rewritten'
        with self.assertRaisesRegex(nav.Invalid, 'HISTORY_REWRITE'): self.build()

    def test_history_member_removal(self):
        a=self.build(); self.next(a['manifest_sha256']); self.m['contracts']=[c for c in self.m['contracts'] if c['id']!='contract.plan.v1']
        self.m['history'][0]['entity_ids']=['doc.old']
        with self.assertRaisesRegex(nav.Invalid, 'HISTORY_REWRITE'): self.build()

    def test_unreferenced_historical_document_removal(self):
        a=self.build(); self.next(a['manifest_sha256'])
        self.m['documents']=[d for d in self.m['documents'] if d['id']!='doc.project']
        self.m['modules'][0]['docs'].remove('doc.project')
        with self.assertRaisesRegex(nav.Invalid, 'HISTORY_MEMBER_REMOVED'): self.build()

    def test_new_release_requires_event(self):
        a=self.build(); self.next(a['manifest_sha256'])
        with self.assertRaisesRegex(nav.Invalid, 'NEW_HISTORY_EVENT_REQUIRED'): self.build()

    def test_matrix_history_rewrite(self):
        a=self.build(); self.next(a['manifest_sha256'])
        old=next(d for d in self.m['documents'] if d['id']=='doc.matrix');old['lifecycle']='archived'
        new=copy.deepcopy(old);new.update(id='doc.matrix.v2',path='MATRIX_REFS_V2.json',lifecycle='current')
        matrix=json.loads((self.inputs/'MATRIX_REFS.json').read_text());matrix['events'][0]['title']='rewritten'
        data=nav.canonical(matrix);(self.inputs/new['path']).write_bytes(data)
        new.update(sha256=nav.digest(data),bytes=len(data));self.m['documents'].append(new);self.m['matrix']['doc']=new['id']
        with self.assertRaisesRegex(nav.Invalid, 'MATRIX_HISTORY_REWRITE'): self.build()

    def test_historical_member_edited(self):
        a=self.build(); self.next(a['manifest_sha256']); self.m['contracts'][0]['input']='rewritten'
        with self.assertRaisesRegex(nav.Invalid, 'HISTORICAL_MEMBER_REWRITE'): self.build()

    def test_archive_reactivation(self):
        a=self.build(); self.next(a['manifest_sha256']); self.m['documents'][2]['lifecycle']='current'
        with self.assertRaisesRegex(nav.Invalid, 'ARCHIVE_REACTIVATED'): self.build()

    def test_limits(self):
        with patch.object(nav,'MAX_TOTAL',20):
            with self.assertRaisesRegex(nav.Invalid,'TOTAL_LIMIT'): self.load()
        (self.inputs/'PROJECT.md').write_bytes(b'x'*(nav.MAX_FILE+1))
        with self.assertRaisesRegex(nav.Invalid,'FILE_LIMIT'): self.load()

    def test_markup_is_inert_and_csp_bound(self):
        s=self.load(); out=nav.render(s).decode()
        self.assertNotIn('<script>globalThis.INJECTED=true',out)
        self.assertIn('\\u003cscript\\u003e',out)
        self.assertIn("default-src 'none'",out)
        self.assertEqual(out.count('<script'),2)
        self.assertNotIn('innerHTML', (SCRIPTS/'viewer.js').read_text())
        self.assertNotIn('fetch(', (SCRIPTS/'viewer.js').read_text())

    def test_ui_logic_and_minimal_dom(self):
        node=shutil.which('node'); self.assertIsNotNone(node,'Existing installed Node required for promised DOM check')
        p=self.base/'snapshot.json';p.write_bytes(nav.canonical(self.load()))
        r=subprocess.run([node,str(BASE/'tests/ui_dom.cjs'),str(p)],capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr+r.stdout)
        result=json.loads(r.stdout);self.assertEqual(result['level'],'PURE_LOGIC_AND_MINIMAL_DOM_NOT_VISUAL');self.assertGreaterEqual(result['checks'],20)
        print(r.stdout.strip())

    def test_unknown_requiredness_not_boolean_coerced(self):
        self.m['contracts'][0]['parameters'][0]['required']='UNKNOWN'
        self.assertEqual(self.load()['input']['contracts'][0]['parameters'][0]['required'],'UNKNOWN')
        self.m['contracts'][0]['parameters'][0]['required']=1
        with self.assertRaisesRegex(nav.Invalid,'SCHEMA_TYPE'):self.load()

    def test_falsy_current_never_starts_a_new_lineage(self):
        first = self.build()
        first_files = {p.name:p.read_bytes() for p in (self.out/'releases'/first['release']).iterdir()}
        self.m['release'].update(id='NEW-GENESIS', previous=None)
        self.m['history'] = []
        for raw in (b'{}', b'[]', b'false', b'null', b'0', b'""'):
            with self.subTest(pointer=raw):
                (self.out/'CURRENT.json').write_bytes(raw)
                with self.assertRaisesRegex(nav.Invalid, 'SHAPE:pointer'):
                    self.build()
                self.assertEqual((self.out/'CURRENT.json').read_bytes(), raw)
                self.assertFalse((self.out/'releases/NEW-GENESIS').exists())
                self.assertEqual(first_files, {p.name:p.read_bytes() for p in (self.out/'releases'/first['release']).iterdir()})

    def test_missing_current_never_starts_a_new_lineage(self):
        self.build(); (self.out/'CURRENT.json').unlink()
        self.m['release'].update(id='NEW-GENESIS', previous=None)
        self.m['history'] = []
        with self.assertRaisesRegex(nav.Invalid, 'ORPHAN_RECONCILE_ONLY'):
            self.build()
        self.assertFalse((self.out/'CURRENT.json').exists())
        self.assertFalse((self.out/'releases/NEW-GENESIS').exists())

    def test_empty_release_directory_accepts_initial_release(self):
        (self.out/'releases').mkdir(parents=True)
        self.assertEqual(self.build()['status'], 'BUILT_LOCAL')

    def test_matrix_historical_event_cannot_postdate_readback(self):
        matrix = nav.parse((self.inputs/'MATRIX_REFS.json').read_bytes())
        matrix['events'][0]['at'] = self.m['release']['created_at']
        raw = nav.canonical(matrix); (self.inputs/'MATRIX_REFS.json').write_bytes(raw)
        doc = next(d for d in self.m['documents'] if d['id'] == 'doc.matrix')
        doc.update(sha256=nav.digest(raw), bytes=len(raw))
        with self.assertRaisesRegex(nav.Invalid, 'MATRIX_EVENT_AFTER_READBACK'):
            self.load()

    def test_unpaired_manifest_surrogate_has_controlled_refusal(self):
        self.m['project']['title'] = '\ud800'
        (self.inputs/'DOCS_INDEX.json').write_bytes(json.dumps(self.m).encode('ascii'))
        with self.assertRaisesRegex(nav.Invalid, 'INVALID_UTF8_JSON'):
            nav.build(self.inputs, 'DOCS_INDEX.json', self.out)
        self.assertFalse(self.out.exists())

    def test_selected_json_surrogate_has_controlled_refusal(self):
        raw = b'{"value":"\\ud800"}'
        (self.inputs/'PLAN.schema.json').write_bytes(raw)
        doc = next(d for d in self.m['documents'] if d['id'] == 'doc.schema')
        doc.update(sha256=nav.digest(raw), bytes=len(raw))
        with self.assertRaisesRegex(nav.Invalid, 'INVALID_UTF8_JSON'):
            self.load()

    def test_only_utf8_input_json_is_accepted(self):
        for encoding in ('utf-16', 'utf-32'):
            with self.subTest(encoding=encoding):
                raw = json.dumps(self.m).encode(encoding)
                (self.inputs/'DOCS_INDEX.json').write_bytes(raw)
                with self.assertRaisesRegex(nav.Invalid, 'INVALID_UTF8_JSON'):
                    nav.load(self.inputs, 'DOCS_INDEX.json')

    def test_nonfinite_json_including_numeric_overflow_is_rejected(self):
        for number in ('NaN', 'Infinity', '-Infinity', '1e400', '-1e400'):
            with self.subTest(number=number):
                with self.assertRaisesRegex(nav.Invalid, 'NONFINITE_JSON'):
                    nav.parse('{"value":' + number + '}')

    def test_parser_integer_limit_has_controlled_refusal(self):
        limit = sys.get_int_max_str_digits()
        if not limit:
            self.skipTest('Python integer digit limit is disabled in this interpreter')
        with self.assertRaisesRegex(nav.Invalid, 'INVALID_UTF8_JSON'):
            nav.parse('{"value":' + '1' * (limit + 1) + '}')

    def test_nul_path_has_controlled_refusal(self):
        self.m['documents'][0]['path'] = 'PROJECT\x00.md'
        with self.assertRaisesRegex(nav.Invalid, 'UNSAFE_PATH'):
            self.load()

    def test_declared_bytes_are_strict_unsigned_integers(self):
        for value in (True, False, -1, 1.0, '1'):
            with self.subTest(value=repr(value)):
                self.m['documents'][0]['bytes'] = value
                with self.assertRaisesRegex(nav.Invalid, 'SCHEMA_INTEGER'):
                    self.load()

    def test_extended_reference_limit_is_explicit_and_compatible(self):
        values = ['REF-' + str(i) for i in range(1001)]
        allowed = set(values)
        with self.assertRaisesRegex(nav.Invalid, 'ARRAY:extended'):
            nav.refs(values, allowed, 'extended')
        nav.refs(values, allowed, 'extended', limit=2000)

    def test_output_pins_are_strict_unsigned_integers(self):
        built = self.build(); release = built['release']
        path = self.out/'releases'/release/'MANIFEST.json'
        original = nav.parse(path.read_bytes())
        for value in (True, False, -1, 1.0, '1'):
            with self.subTest(value=repr(value)):
                m = copy.deepcopy(original); m['files']['index.html']['bytes'] = value
                path.write_bytes(nav.canonical(m))
                with self.assertRaisesRegex(nav.Invalid, 'OUTPUT_PIN_BYTES'):
                    nav.verify_release(self.out, release)

    def test_output_manifest_invalid_shape_has_controlled_refusal(self):
        built = self.build(); path = self.out/'releases'/built['release']/'MANIFEST.json'
        m = nav.parse(path.read_bytes()); m['files'] = []
        path.write_bytes(nav.canonical(m))
        with self.assertRaisesRegex(nav.Invalid, 'SHAPE:output files'):
            nav.verify_release(self.out, built['release'])

    def test_output_template_version_is_bound_to_snapshot(self):
        built = self.build(); path = self.out/'releases'/built['release']/'MANIFEST.json'
        m = nav.parse(path.read_bytes()); m['template_version'] = 'OTHER-TEMPLATE'
        path.write_bytes(nav.canonical(m))
        with self.assertRaisesRegex(nav.Invalid, 'OUTPUT_TEMPLATE_BINDING'):
            nav.verify_release(self.out, built['release'])

    def test_verify_does_not_follow_output_root_symlinks(self):
        built = self.build(); alias = self.base/'alias-output'
        alias.symlink_to(self.out, target_is_directory=True)
        with self.assertRaisesRegex(nav.Invalid, 'OUTPUT_SYMLINK'):
            nav.verify_release(alias, built['release'])

    def test_publish_custom_render_history_and_version_hooks(self):
        first_snapshot = self.load()
        first_snapshot['template_version'] = 'ATLAS-HOOK-TEST.1'
        first_snapshot['extension'] = {'marker': 'caller-owned extension'}
        calls = []
        def history_hook(previous, current):
            calls.append((previous['input']['release']['id'], current['input']['release']['id']))
            nav.check_history(previous, current)
        def renderer(snapshot):
            return ('<p>' + snapshot['extension']['marker'] + '</p>').encode('utf-8')
        first = nav.publish(first_snapshot, self.out, render_fn=renderer,
                            history_fn=history_hook, version='ATLAS-HOOK-TEST.1')
        second = copy.deepcopy(first_snapshot)
        second['input']['release'].update(id='HOOK-RELEASE.2', previous=first['manifest_sha256'])
        second['input']['history'].append({'id':'HOOK-EVENT.2', 'at':second['input']['release']['created_at'],
                                          'kind':'TEST', 'summary':'Hook integration test', 'entity_ids':[]})
        second['input_sha256'] = nav.digest(nav.canonical(second['input']))
        built = nav.publish(second, self.out, render_fn=renderer,
                            history_fn=history_hook, version='ATLAS-HOOK-TEST.1')
        self.assertEqual(calls, [(first['release'], built['release'])])
        _, verified = nav.verify_release(self.out, built['release'], built['manifest_sha256'])
        self.assertEqual(verified['extension'], second['extension'])
        self.assertEqual(verified['template_version'], 'ATLAS-HOOK-TEST.1')
        self.assertEqual((self.out/'releases'/built['release']/'index.html').read_bytes(), renderer(second))

    def test_publish_hook_refusal_preserves_current(self):
        first = self.build(); pointer = (self.out/'CURRENT.json').read_bytes()
        snapshot = self.load(); snapshot['input']['release'].update(id='REFUSED-RELEASE', previous=first['manifest_sha256'])
        def refuse(previous, current):
            raise nav.Invalid('EXTENSION_HISTORY_REFUSED')
        with self.assertRaisesRegex(nav.Invalid, 'EXTENSION_HISTORY_REFUSED'):
            nav.publish(snapshot, self.out, history_fn=refuse)
        self.assertEqual((self.out/'CURRENT.json').read_bytes(), pointer)
        self.assertFalse((self.out/'releases/REFUSED-RELEASE').exists())

    def test_output_limit_is_checked_before_creating_release(self):
        snapshot = self.load()
        with patch.object(nav, 'MAX_HTML', 10):
            with self.assertRaisesRegex(nav.Invalid, 'OUTPUT_LIMIT'):
                nav.publish(snapshot, self.out, render_fn=lambda value: b'x' * 11)
        self.assertFalse((self.out/'CURRENT.json').exists())
        self.assertFalse((self.out/'releases'/snapshot['input']['release']['id']).exists())

    def test_publish_rejects_nonbyte_renderer_result(self):
        with self.assertRaisesRegex(nav.Invalid, 'RENDER_BYTES_REQUIRED'):
            nav.publish(self.load(), self.out, render_fn=lambda value: '<html>text</html>')




if __name__ == '__main__':
    unittest.main(verbosity=2)
