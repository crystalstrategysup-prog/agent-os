"""Focused opt-in projection archive tests; no source execution or host access.

Large history fixtures exercise the real 32 MiB selection bound, not a raised
limit. Every test works in a newly created temporary root.
"""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/atlas/scripts'
sys.path.insert(0, str(SCRIPTS))
import atlas
import navigator as nav

PROJECT = '.atlas/project.json'
TIMES = ['2026-10-17T03:00:00Z', '2026-10-17T03:10:00Z', '2026-10-17T03:20:00Z', '2026-10-17T03:30:00Z']


class ProjectionArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'project'
        self.root.mkdir()
        atlas.initialize(self.root, 'ARCHIVE-DEMO', 'Archive demo', 'Preserve selected history',
                         'demo-writer', 'synthetic-local-only', 'projection', TIMES[0])
        self.out = self.root / '.atlas/output'
        self.project = self.read(PROJECT)
        self.doc_path = self.project['documents']['path']
        self.dn = self.read(self.doc_path)
        self.base_doc = copy.deepcopy(self.dn['documents'][0])

    def read(self, relative):
        return nav.parse((self.root / relative).read_bytes())

    def write(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(nav.canonical(value))

    def pin(self, relative):
        raw = (self.root / relative).read_bytes()
        return {'path': relative, 'sha256': nav.digest(raw), 'bytes': len(raw)}

    def save(self):
        self.write(self.doc_path, self.dn)
        self.project['documents'] = self.pin(self.doc_path)
        self.write(PROJECT, self.project)

    def page(self, label, index, size=0):
        relative = f'.atlas/imports/source-{label}.json'
        self.write(relative, {'id': label, 'padding': 'x' * size})
        return {'id': 'M-' + label, 'at': TIMES[index], 'source_ref': 'synthetic/matrix/' + label,
                'kind': 'FULL_MATRIX', 'file': self.pin(relative)}

    def docs(self, names, index):
        rows = [copy.deepcopy(self.base_doc)]
        for name in names:
            relative = f'.atlas/imports/document-{name}.md'
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('Synthetic immutable version ' + name + '\n', encoding='utf-8')
            rows.append({**self.base_doc, 'id': 'D-' + name, 'title': name, 'version': name,
                         **self.pin(relative), 'source_ref': 'synthetic/document/' + name, 'readback_at': TIMES[index]})
        self.dn['documents'] = rows
        self.dn['release'] = {'id': 'D-' + str(index), 'created_at': TIMES[index], 'previous': None}
        self.dn['history'] = [{'id': 'H-' + str(index), 'at': TIMES[index], 'kind': 'IMPORTED',
                               'summary': 'Synthetic current document graph', 'entity_ids': [d['id'] for d in rows]}]

    def contracts(self, names):
        self.dn['modules'] = [{'id': 'MODULE', 'title': 'Module', 'purpose': 'Bounded graph', 'state_owner': 'demo',
                               'dependencies': [], 'docs': [self.base_doc['id']]}]
        self.dn['contracts'] = [
            {'id': 'C-' + name, 'contract_key': 'K-' + name, 'title': name, 'version': name, 'lifecycle': 'current',
             'module': 'MODULE', 'state_owner': 'demo', 'input': 'in', 'output': 'out', 'parameters': [], 'errors': [],
             'auth': 'UNKNOWN', 'dependencies': [], 'usage': 'Synthetic', 'docs': [self.base_doc['id']],
             'evidence_state': 'DESIGN', 'execution': 'NOT_RUN'} for name in names]

    def cycle(self, index):
        self.save()
        return atlas.cycle(self.root, PROJECT, self.out, release='R-' + str(index), at=TIMES[index])

    def checkpoint(self, index, entries=None):
        pointer, previous = atlas.current_output(self.out)
        entries = [] if entries is None else entries
        total = previous['atlas'].get('matrix_history_total', len(previous['atlas'].get('matrix_history', [])))
        self.project['projection_archive'] = {
            'schema': 'atlas.projection-archive/v1', 'output': '.atlas/output',
            'previous_release': pointer['release'], 'previous_manifest_sha256': pointer['manifest_sha256'],
            'matrix_history_total': total + len(entries)}
        self.project['matrix_history'] = entries
        self.docs(['v' + str(index)], index)

    def load(self, index=2):
        self.save()
        return atlas.load_project(self.root, PROJECT, at=TIMES[index])

    def output_tree(self):
        return {p.relative_to(self.out).as_posix(): nav.digest(p.read_bytes()) for p in self.out.rglob('*') if p.is_file()}

    def test_current_documents_roll_over_beyond_200_lifetime_versions(self):
        self.docs(['old' + str(i) for i in range(198)], 0)
        first = self.cycle(0)
        old_tree = self.output_tree()
        self.checkpoint(1)
        self.docs(['new1', 'new2'], 1)
        self.assertEqual(self.cycle(1)['status'], 'BUILT_LOCAL')
        _, old = nav.verify_release(self.out, first['release'], first['manifest_sha256'])
        _, new = atlas.current_output(self.out)
        self.assertEqual(len(old['documents']), 199)
        self.assertEqual(len(new['documents']), 3)
        self.assertEqual(len({d['id'] for d in old['documents'] + new['documents']}), 201)
        self.assertTrue(all(self.output_tree()[p] == digest for p, digest in old_tree.items() if p.startswith('releases/')))

    def test_current_contracts_roll_over_beyond_1000_lifetime_versions(self):
        self.docs([], 0)
        self.contracts(['old' + str(i) for i in range(990)])
        self.cycle(0)
        self.checkpoint(1)
        self.contracts(['new' + str(i) for i in range(20)])
        self.assertEqual(self.cycle(1)['status'], 'BUILT_LOCAL')
        _, old = nav.verify_release(self.out, 'R-0')
        _, new = atlas.current_output(self.out)
        self.assertEqual(len(old['input']['contracts']) + len(new['input']['contracts']), 1010)

    def test_discover_reads_a_valid_manifest_over_512kib(self):
        self.docs(['large-manifest-source'], 0)
        self.contracts(['method' + str(i) for i in range(50)])
        for contract in self.dn['contracts']:
            contract['input'] = 'Explicit input description. ' * 500
        self.save()
        self.assertGreater((self.root / self.doc_path).stat().st_size, 512 * 1024)
        self.assertLess((self.root / self.doc_path).stat().st_size, nav.MAX_TOTAL)
        nav.load(self.root, self.doc_path)
        before = (self.root / self.doc_path).read_bytes()
        result = atlas.discover(self.root, PROJECT, ['.atlas/imports'])
        self.assertEqual((self.root / self.doc_path).read_bytes(), before)
        row = next(row for row in result['files'] if row['path'].endswith('document-large-manifest-source.md'))
        self.assertEqual(row['classification'], 'UNCHANGED')

    def test_history_over_32mib_reads_only_the_new_page_and_one_parent(self):
        old_entries = [self.page('old' + str(i), 0, 7 * 1024 * 1024) for i in range(4)]
        self.project['matrix_history'] = old_entries
        self.cycle(0)
        new_entries = [self.page('new' + str(i), 1, 7 * 1024 * 1024) for i in range(4)]
        self.checkpoint(1, new_entries)
        self.save()
        self.assertGreater(sum(e['file']['bytes'] for e in old_entries + new_entries), atlas.MAX_SELECTED)
        original_read = nav.read_selected
        old_paths = {e['file']['path'] for e in old_entries}
        def guard(root, relative, *args, **kwargs):
            if Path(root) == self.root and relative in old_paths:
                self.fail('Refresh reopened an archived raw matrix')
            return original_read(root, relative, *args, **kwargs)
        with patch.object(nav, 'read_selected', side_effect=guard), patch.object(nav, 'verify_release', wraps=nav.verify_release) as verify:
            snapshot = atlas.load_project(self.root, PROJECT, at=TIMES[1])
            self.assertEqual(verify.call_count, 1)
            self.assertEqual(snapshot['atlas']['matrix_history_total'], 8)
            self.assertEqual(len(snapshot['atlas']['matrix_history']), 4)
            self.assertFalse(old_paths.intersection(p['path'] for p in snapshot['atlas']['source_pins']))
            self.assertEqual(snapshot['atlas']['projection_archive']['archived_source_status'], 'VERIFIED_AT_IMPORT')
        with patch.object(nav, 'read_selected', side_effect=guard):
            self.assertEqual(self.cycle(1)['status'], 'BUILT_LOCAL')
            result = atlas.history(self.out)
            self.assertEqual(result['status'], 'VERIFIED_CHAIN')
            self.assertEqual(result['matrix_history_total'], 8)
            self.assertEqual(len(result['imported_matrix_history']), 8)
            self.assertEqual(result['raw_source_reads'], 0)

    def test_archive_total_is_strict_unsigned_integer(self):
        self.cycle(0)
        self.checkpoint(1)
        for value in (True, False, 0.0, -1, 9007199254740992):
            with self.subTest(value=value):
                self.project['projection_archive']['matrix_history_total'] = value
                with self.assertRaisesRegex(nav.Invalid, 'SCHEMA_INTEGER'):
                    self.load(1)

    def test_wrong_total_and_repeated_page_are_refused(self):
        entry = self.page('first', 0)
        self.project['matrix_history'] = [entry]
        self.cycle(0)
        self.checkpoint(1, [self.page('second', 1)])
        self.project['projection_archive']['matrix_history_total'] += 1
        with self.assertRaisesRegex(nav.Invalid, 'ARCHIVE_HISTORY_TOTAL'):
            self.load(1)
        self.project['matrix_history'] = [entry]
        self.project['projection_archive']['matrix_history_total'] = 2
        with self.assertRaisesRegex(nav.Invalid, 'ARCHIVE_PAGE_ALREADY_RETAINED'):
            self.load(1)

    def test_native_mode_cannot_use_archive_exception(self):
        self.cycle(0)
        self.checkpoint(1)
        self.project['mode'] = 'native'
        with self.assertRaisesRegex(nav.Invalid, 'ARCHIVE_REQUIRES_PROJECTION'):
            self.load(1)

    def test_missing_or_modified_parent_fails_closed(self):
        self.cycle(0)
        self.checkpoint(1)
        self.project['projection_archive']['previous_manifest_sha256'] = '0' * 64
        with self.assertRaisesRegex(nav.Invalid, 'OUTPUT_MANIFEST_HASH'):
            self.load(1)
        self.checkpoint(1)
        path = self.out / 'releases/R-0/snapshot.json'
        raw = path.read_bytes()
        path.write_bytes(raw + b' ')
        with self.assertRaisesRegex(nav.Invalid, 'OUTPUT_FILE_HASH'):
            self.load(1)
        path.write_bytes(raw)
        self.project['projection_archive']['previous_release'] = 'MISSING'
        with self.assertRaisesRegex(nav.Invalid, 'MISSING_SELECTED_PATH'):
            self.load(1)

    def test_archive_output_cannot_escape_or_be_published_elsewhere(self):
        self.cycle(0)
        self.checkpoint(1)
        self.project['projection_archive']['output'] = '../outside'
        with self.assertRaisesRegex(nav.Invalid, 'UNSAFE_PATH'):
            self.load(1)
        self.checkpoint(1)
        self.save()
        with self.assertRaisesRegex(nav.Invalid, 'ARCHIVE_OUTPUT_BINDING'):
            atlas.cycle(self.root, PROJECT, self.root / 'other-output', release='OTHER', at=TIMES[1])
        self.assertFalse((self.root / 'other-output').exists())

    def test_stale_parent_cannot_rewrite_current_or_existing_releases(self):
        self.cycle(0)
        self.checkpoint(1)
        self.cycle(1)
        before = self.output_tree()
        self.docs(['changed'], 2)
        with self.assertRaisesRegex(nav.Invalid, 'ARCHIVE_PARENT_MISMATCH'):
            self.cycle(2)
        self.assertEqual(self.output_tree(), before)

    def test_surviving_document_version_is_immutable(self):
        self.cycle(0)
        self.checkpoint(1)
        self.dn['documents'][0]['title'] = 'Redefined existing version'
        with self.assertRaisesRegex(nav.Invalid, 'HISTORICAL_MEMBER_REWRITE'):
            self.cycle(1)

    def test_surviving_contract_version_is_immutable_but_module_can_evolve(self):
        self.docs([], 0)
        self.contracts(['stable'])
        self.cycle(0)
        self.checkpoint(1)
        self.dn['modules'][0]['purpose'] = 'More precise declared scope'
        self.assertEqual(self.cycle(1)['status'], 'BUILT_LOCAL')
        self.checkpoint(2)
        self.dn['contracts'][0]['input'] = 'Redefined existing contract version'
        with self.assertRaisesRegex(nav.Invalid, 'HISTORICAL_MEMBER_REWRITE'):
            self.cycle(2)

    def test_work_event_history_remains_strict(self):
        work_path = self.project['work_files'][0]
        work = self.read(work_path)
        extra = copy.deepcopy(work['events'][0])
        extra.update(id='EXTRA-EVENT', kind='CHECKPOINT', summary='Earlier actual fixture checkpoint')
        work['events'].append(extra)
        self.write(work_path, work)
        self.cycle(0)
        self.checkpoint(1)
        work['events'].pop(0)
        self.write(work_path, work)
        with self.assertRaisesRegex(nav.Invalid, 'WORK_EVENT_REWRITE'):
            self.cycle(1)

    def test_archive_cannot_be_silently_disabled(self):
        self.cycle(0)
        self.checkpoint(1)
        self.cycle(1)
        del self.project['projection_archive']
        self.docs(['second'], 2)
        with self.assertRaisesRegex(nav.Invalid, 'ARCHIVE_CHECKPOINT_REQUIRED'):
            self.cycle(2)

    def test_native_history_still_refuses_removed_document(self):
        self.project['mode'] = 'native'
        self.docs(['old'], 0)
        self.dn['history'][0]['entity_ids'] = [self.base_doc['id']]
        self.cycle(0)
        old_history = copy.deepcopy(self.dn['history'])
        self.docs(['new'], 1)
        self.dn['history'] = old_history + self.dn['history']
        with self.assertRaisesRegex(nav.Invalid, 'HISTORY_MEMBER_REMOVED'):
            self.cycle(1)

    def test_paginated_history_preserves_exact_source_pins_and_targets(self):
        self.project['matrix_history'] = [self.page('first', 0)]
        self.cycle(0)
        for index in (1, 2):
            self.checkpoint(index, [self.page('version' + str(index), index)])
            self.cycle(index)
        cursor = None; ids = []; refs = []
        for index in range(3):
            result = atlas.history(self.out, limit=1, cursor=cursor)
            self.assertEqual(result['status'], 'VERIFIED_PAGE')
            self.assertEqual(len(result['revisions']), 1)
            self.assertEqual(result['raw_source_reads'], 0)
            self.assertEqual(result['readback']['legacy_manifest_headers_read'], 0)
            ids.extend(row['id'] for row in result['revisions'])
            refs.extend(result['imported_matrix_history'])
            cursor = result['next_cursor']
            self.assertEqual(result['has_more'], index != 2)
        self.assertEqual(ids, ['R-2', 'R-1', 'R-0'])
        self.assertEqual(len({row['id'] for row in refs}), 3)
        for row in refs:
            self.assertEqual(row['file_target'], str(self.root / row['file']['path']))
            self.assertEqual(row['source_validation'], 'VERIFIED_AT_IMPORT')
            self.assertEqual(self.pin(row['file']['path']), row['file'])
        self.assertEqual(atlas.history(self.out)['status'], 'VERIFIED_CHAIN')

    def test_missing_non_immediate_page_is_found_by_history_request(self):
        self.project['matrix_history'] = [self.page('first', 0)]
        self.cycle(0)
        for index in (1, 2):
            self.checkpoint(index, [self.page('v' + str(index), index)])
            self.cycle(index)
        (self.out / 'releases/R-0').rename(self.out / 'retained-outside-release-tree')
        # Current load checks its one immediate parent and does not claim a full audit.
        self.assertEqual(self.load(2)['atlas']['matrix_history_total'], 3)
        with self.assertRaisesRegex(nav.Invalid, 'MISSING_SELECTED_PATH'):
            atlas.history(self.out)

    def test_history_cursor_and_limit_are_validated(self):
        self.cycle(0)
        self.checkpoint(1)
        self.cycle(1)
        for value in (0, 101, True, 0.5):
            with self.subTest(limit=value), self.assertRaisesRegex(nav.Invalid, 'HISTORY_PAGE_LIMIT'):
                atlas.history(self.out, limit=value)
        for cursor in ('../outside/' + '0' * 64, 'no-slash', 'R-0/not-a-sha'):
            with self.subTest(cursor=cursor), self.assertRaises(nav.Invalid):
                atlas.history(self.out, cursor=cursor)


if __name__ == '__main__':
    unittest.main(verbosity=2)
