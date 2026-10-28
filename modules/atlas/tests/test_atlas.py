"""Atlas work contract regression tests against a synthetic workflow.

Only temporary fixture copies are changed. Tests do not execute receipts, import
product source, contact hosts, or establish runtime / owner acceptance.
"""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
SCRIPTS = BASE / 'skills' / 'atlas' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import atlas
import navigator as nav

PROJECT = '.atlas/project.json'
AS_OF = '2026-10-17T03:15:00Z'


class AtlasTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'project'
        shutil.copytree(BASE / 'examples/workflow', self.root)
        self.project = self.read(PROJECT)
        docs = nav.load(self.root, 'docs/DOCS_INDEX.json')
        self.entities = {x['id'] for x in docs['documents'] + docs['input']['modules'] + docs['input']['contracts']}

    def read(self, path):
        return nav.parse((self.root / path).read_bytes())

    def write(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(nav.canonical(value))

    def work(self, wid):
        return self.read(f'.atlas/work/{wid}.json')

    def save_work(self, work):
        self.write(f'.atlas/work/{work["id"]}.json', work)

    def load(self, at=AS_OF):
        return atlas.load_project(self.root, PROJECT, at=at)

    def validate(self, work, at=AS_OF):
        return atlas.validate_work(work, self.root, self.entities, nav.stamp(at), {})

    def assert_refused(self, code, call):
        with self.assertRaisesRegex(nav.Invalid, code):
            call()

    def pin(self, path):
        raw = (self.root / path).read_bytes()
        return {'path': path, 'sha256': nav.digest(raw), 'bytes': len(raw)}

    def tree(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def evidence(self, work, scope='TEST', eid='E-TEST', subjects=None):
        return {'id': eid, 'check_id': 'batch.limit.test', 'scope': scope,
                'subjects': subjects if subjects is not None else [{'artifact_id': a['id'], 'sha256': a['sha256']} for a in work['artifacts']],
                'environment': 'synthetic-example', 'actor': 'reviewer-demo', 'at': '2026-10-17T03:05:00Z',
                'receipt': self.pin('receipts/source-test.json'), 'result': 'PASS'}

    def with_acceptance(self, work, scope='TEST'):
        work = copy.deepcopy(work)
        ev = self.evidence(work, scope=scope)
        work['evidence'].append(ev)
        work['acceptance'] = [{'criterion_id': work['criteria'][0]['id'], 'decision': 'ACCEPTED', 'actor': 'reviewer-demo',
                               'at': '2026-10-17T03:05:00Z', 'evidence_ids': [ev['id']], 'basis_sha256': atlas.basis(work)}]
        return work

    def patch_work(self):
        work = self.work('W-01')
        work['state'] = 'REVIEW'
        work['acceptance'] = []
        work['next_action'] = {'actor': 'reviewer-demo', 'action': 'Review the explicitly proposed patch'}
        work['events'].append({'id': 'TEST-REOPEN', 'at': '2026-10-17T03:01:00Z', 'actor': 'reviewer-demo', 'kind': 'REOPEN', 'summary': 'Reopen synthetic work for bounded review', 'evidence_ids': []})
        work['events'].append({'id': 'TEST-REVIEW', 'at': '2026-10-17T03:02:00Z', 'actor': 'reviewer-demo', 'kind': 'REVIEWED', 'summary': 'Synthetic work is in review', 'evidence_ids': []})
        return work

    def accepted_state(self, work):
        work.update(state='ACCEPTED', activity=None, result='Synthetic source result')
        work['events'].append({'id': 'TEST-ACCEPTED', 'at': '2026-10-17T03:05:00Z', 'actor': 'reviewer-demo', 'kind': 'ACCEPTED', 'summary': 'Synthetic acceptance recorded', 'evidence_ids': ['E-TEST']})
        return work

    def applied_patch(self):
        work = self.patch_work()
        self.write('docs/CONTRACT-v2.json', {'limit': 200})
        result = {'id': 'A-RESULT', **self.pin('docs/CONTRACT-v2.json'), 'role': 'output', 'entity_ids': []}
        work['artifacts'].append(result)
        patch = work['artifacts'][1]['patch']
        patch['state'] = 'APPLIED'
        patch['result_artifact_id'] = 'A-RESULT'
        ev = self.evidence(work, scope='SOURCE', eid='E-APPLY')
        work['evidence'].append(ev)
        patch['decision_evidence_ids'].append(ev['id'])
        return work

    def graph_work(self, wid, scope=None, state='DOING'):
        work = self.work('W-02')
        work.update(id=wid, state=state, assigned_to='actor-' + wid, writer='writer-' + wid,
                    depends_on=[], write_scope=scope or [], activity=None, artifacts=[], evidence=[], acceptance=[], criteria=[])
        return work

    def test_workflow_validates_without_input_writes_or_runtime_claim(self):
        before = self.tree()
        snapshot = self.load()
        self.assertEqual(self.tree(), before)
        records = {w['id']: w for w in snapshot['atlas']['works']}
        self.assertEqual(records['W-01']['state'], 'ACCEPTED')
        self.assertEqual(records['W-01']['derived']['accepted_criteria'], 1)
        self.assertEqual(records['W-02']['state'], 'DOING')
        self.assertEqual(records['W-02']['derived']['activity_state'], 'EXPIRED')
        self.assertEqual(records['W-03']['derived']['accepted_criteria'], 0)
        self.assertEqual(records['W-03']['state'], 'BLOCKED')
        self.assertTrue(any(p['path'] == 'receipts/contract-review.json' for p in snapshot['atlas']['source_pins']))
        self.assertEqual(snapshot['atlas']['document_release'], self.read('docs/DOCS_INDEX.json')['release'])

    def test_artifact_bytes_and_receipt_bytes_are_both_pinned(self):
        for path in ('src/batch.py', 'receipts/activity.json'):
            with self.subTest(path=path):
                target = self.root / path
                old = target.read_bytes()
                target.write_bytes(old + b'\nchanged')
                self.assert_refused('PIN_MISMATCH', self.load)
                target.write_bytes(old)

    def test_document_index_pin_is_not_replaced_by_mtime_or_name(self):
        target = self.root / 'docs/DOCS_INDEX.json'
        target.write_bytes(target.read_bytes() + b' ')
        self.assert_refused('PIN_MISMATCH:document_manifest', self.load)

    def test_loaded_product_source_is_data_and_never_imported(self):
        path = self.root / 'src/batch.py'
        path.write_text('raise AssertionError("SOURCE_MUST_NOT_EXECUTE")\n', encoding='utf-8')
        for wid in ('W-02', 'W-03'):
            w = self.work(wid)
            w['artifacts'][0].update(self.pin('src/batch.py'))
            self.save_work(w)
        self.assertEqual(self.load()['atlas']['summary']['total'], 3)

    def test_artifact_and_receipt_symlinks_are_refused(self):
        for path in ('src/batch.py', 'receipts/activity.json'):
            with self.subTest(path=path):
                target = self.root / path
                backup = target.with_name(target.name + '.original')
                target.rename(backup)
                target.symlink_to(backup)
                self.assert_refused('SYMLINK', self.load)
                target.unlink()
                backup.rename(target)

    def test_unknown_entity_in_artifact_is_not_silently_dropped(self):
        w = self.work('W-02'); w['artifacts'][0]['entity_ids'] = ['UNKNOWN-DOC']
        self.assert_refused('DANGLING', lambda: self.validate(w))

    def test_source_or_test_proof_does_not_accept_runtime(self):
        for wrong_scope in ('SOURCE', 'TEST', 'DOCUMENTARY'):
            with self.subTest(scope=wrong_scope):
                w = self.with_acceptance(self.work('W-03'), scope=wrong_scope)
                self.assert_refused('ACCEPTANCE_SCOPE_OR_SUBJECT', lambda: self.validate(w))

    def test_pass_for_previous_artifact_hash_does_not_accept_current_bytes(self):
        w = self.with_acceptance(self.work('W-02'))
        w['evidence'][-1]['subjects'][0]['sha256'] = '0' * 64
        self.assert_refused('ACCEPTANCE_SCOPE_OR_SUBJECT', lambda: self.validate(w))

    def test_fail_and_unknown_receipts_do_not_accept_criteria(self):
        for result in ('FAIL', 'UNKNOWN'):
            with self.subTest(result=result):
                w = self.with_acceptance(self.work('W-02')); w['evidence'][-1]['result'] = result
                self.assert_refused('ACCEPTANCE_SCOPE_OR_SUBJECT', lambda: self.validate(w))

    def test_semantic_change_stales_prior_acceptance_instead_of_reusing_it(self):
        w = self.with_acceptance(self.work('W-02'))
        self.assertEqual(self.validate(w)['accepted_criteria'], 1)
        w['outcome'] = 'A different acceptance obligation'
        result = self.validate(w)
        self.assertEqual(result['accepted_criteria'], 0)
        self.assertEqual(result['issues'][0]['code'], 'ACCEPTANCE_STALE')
        self.accepted_state(w)
        self.assert_refused('ACCEPTED_WITHOUT_CURRENT_CRITERIA', lambda: self.validate(w))

    def test_accepted_work_requires_current_criteria_and_recorded_result(self):
        w = self.with_acceptance(self.work('W-02'))
        self.accepted_state(w)
        self.assertEqual(self.validate(w)['accepted_criteria'], 1)
        w['result'] = None
        self.assert_refused('ACCEPTED_RESULT_REQUIRED', lambda: self.validate(w))
        w['result'] = 'claimed'; w['criteria'] = []; w['acceptance'] = []
        self.assert_refused('ACCEPTED_WITHOUT_CURRENT_CRITERIA', lambda: self.validate(w))

    def test_activity_is_not_an_acceptance_level(self):
        w = self.work('W-02'); w['criteria'][0]['required_scope'] = 'ACTIVITY'
        self.assert_refused('ACTIVITY_IS_NOT_ACCEPTANCE', lambda: self.validate(w))

    def test_blocker_next_action_and_known_active_owner_are_required(self):
        w = self.work('W-03'); w['blocker'] = None
        self.assert_refused('BLOCKER_REQUIRED', lambda: self.validate(w))
        w = self.work('W-02'); w['next_action'] = None
        self.assert_refused('NEXT_ACTION_REQUIRED', lambda: self.validate(w))
        w = self.work('W-02'); w['writer'] = 'UNKNOWN'
        self.assert_refused('ACTIVE_ACTOR_REQUIRED', lambda: self.validate(w))

    def test_declared_state_cannot_override_the_latest_recorded_transition(self):
        work = self.work('W-02')
        work['state'] = 'ACCEPTED'; work['activity'] = None; work['result'] = 'Unsubstantiated claim'
        self.assert_refused('WORK_STATE_EVENT_MISMATCH', lambda: self.validate(work))

    def test_active_state_requires_a_real_transition_event(self):
        work = self.work('W-02')
        work['events'][0]['kind'] = 'IMPORTED'
        self.assert_refused('WORK_STATE_EVENT_REQUIRED', lambda: self.validate(work))

    def test_receipt_and_acceptance_cannot_predate_or_postdate_their_basis(self):
        w = self.with_acceptance(self.work('W-02')); w['acceptance'][0]['at'] = '2026-10-17T03:04:00Z'
        self.assert_refused('ACCEPTANCE_BEFORE_EVIDENCE', lambda: self.validate(w))
        w = self.with_acceptance(self.work('W-02')); w['evidence'][-1]['at'] = '2026-10-17T04:00:00Z'
        self.assert_refused('EVIDENCE_AFTER_SNAPSHOT', lambda: self.validate(w))

    def test_graph_refuses_active_write_overlap_even_with_same_writer(self):
        for a, b in [('src/', 'src/batch.py'), ('src/batch.py', 'src/'), ('src/batch.py', 'src/batch.py')]:
            with self.subTest(a=a, b=b):
                one, two = self.graph_work('A', [a]), self.graph_work('B', [b], state='REVIEW')
                two['writer'] = one['writer']
                self.assert_refused('WRITE_SCOPE_CONFLICT', lambda: atlas.validate_graph([one, two]))

    def test_graph_allows_unrelated_exact_paths_and_inactive_plans(self):
        for a, b in [('src/a.py', 'src/b.py'), ('src/', 'src-other/file.py'), ('src', 'src/file.py')]:
            with self.subTest(a=a, b=b):
                atlas.validate_graph([self.graph_work('A', [a]), self.graph_work('B', [b])])
        atlas.validate_graph([self.graph_work('A', ['src/']), self.graph_work('B', ['src/'], state='PLANNED')])

    def test_write_scope_has_explicit_path_semantics(self):
        for path in ('../outside', '/absolute', 'src/*', 'src\\file.py'):
            with self.subTest(path=path):
                w = self.work('W-02'); w['write_scope'] = [path]
                self.assert_refused('UNSAFE_PATH|PATH_GLOB_NOT_SUPPORTED', lambda: self.validate(w))

    def test_graph_rejects_dependency_and_parent_cycles(self):
        for edge, code in [('depends_on', 'WORK_DEPENDENCY_CYCLE'), ('parent_id', 'WORK_PARENT_CYCLE')]:
            with self.subTest(edge=edge):
                a, b = self.graph_work('A'), self.graph_work('B')
                a[edge] = ['B'] if edge == 'depends_on' else 'B'
                b[edge] = ['A'] if edge == 'depends_on' else 'A'
                self.assert_refused(code, lambda: atlas.validate_graph([a, b]))

    def test_graph_requires_real_dependencies_before_start(self):
        a, b = self.graph_work('A'), self.graph_work('B', state='PLANNED')
        a['depends_on'] = ['B']
        self.assert_refused('UNMET_DEPENDENCY', lambda: atlas.validate_graph([a, b]))
        b['state'] = 'ACCEPTED'; atlas.validate_graph([a, b])
        a['depends_on'] = ['MISSING']
        self.assert_refused('DANGLING', lambda: atlas.validate_graph([a, b]))

    def test_parent_is_aggregate_and_cannot_hide_open_children(self):
        parent, child = self.graph_work('P', state='PLANNED'), self.graph_work('C', ['src/file.py'])
        child['parent_id'] = 'P'; atlas.validate_graph([parent, child])
        parent['write_scope'] = ['docs/']
        self.assert_refused('PARENT_WRITE_SCOPE_NOT_LEAF', lambda: atlas.validate_graph([parent, child]))
        parent['write_scope'] = []; parent['state'] = 'ACCEPTED'
        self.assert_refused('PARENT_HAS_OPEN_CHILDREN', lambda: atlas.validate_graph([parent, child]))
        child['state'] = 'CANCELLED'; atlas.validate_graph([parent, child])

    def test_patch_has_explicit_role_metadata_target_and_base(self):
        w = self.patch_work(); del w['artifacts'][1]['patch']
        self.assert_refused('PATCH_METADATA_REQUIRED', lambda: self.validate(w))
        w = self.patch_work(); w['artifacts'][1]['patch']['target_id'] = 'MISSING'
        self.assert_refused('PATCH_TARGET', lambda: self.validate(w))
        w = self.patch_work(); w['artifacts'][1]['patch']['base_sha256'] = '0' * 64
        self.assert_refused('PATCH_BASE_CHANGED', lambda: self.validate(w))
        w = self.patch_work(); w['artifacts'][1]['role'] = 'input'
        self.assert_refused('PATCH_ROLE', lambda: self.validate(w))

    def test_patch_acceptance_is_bound_to_patch_and_base_subjects(self):
        w = self.patch_work(); w['evidence'][0]['subjects'] = w['evidence'][0]['subjects'][:1]
        self.assert_refused('PATCH_DECISION_PROOF', lambda: self.validate(w))
        w['artifacts'][1]['patch']['state'] = 'PROPOSED'; w['artifacts'][1]['patch']['decision_evidence_ids'] = []
        self.validate(w)

    def test_applied_patch_requires_output_and_readback_of_all_three_artifacts(self):
        w = self.applied_patch(); self.validate(w)
        w['evidence'][-1]['subjects'] = w['evidence'][-1]['subjects'][1:]
        self.assert_refused('PATCH_APPLY_READBACK', lambda: self.validate(w))
        w = self.applied_patch(); w['artifacts'][1]['patch']['result_artifact_id'] = None
        self.assert_refused('PATCH_RESULT_REQUIRED', lambda: self.validate(w))
        w = self.applied_patch(); w['artifacts'][-1]['role'] = 'input'
        self.assert_refused('PATCH_RESULT_ROLE', lambda: self.validate(w))

    def test_unapplied_patch_cannot_claim_output_and_readback_cannot_be_documentary_only(self):
        w = self.applied_patch(); w['artifacts'][1]['patch']['state'] = 'ACCEPTED_UNAPPLIED'
        self.assert_refused('UNAPPLIED_PATCH_HAS_RESULT', lambda: self.validate(w))
        w = self.applied_patch(); w['evidence'][-1]['scope'] = 'DOCUMENTARY'
        self.assert_refused('PATCH_APPLY_READBACK', lambda: self.validate(w))

    def test_distinct_overlapping_accepted_patches_cannot_be_composed_silently(self):
        a, b = self.patch_work(), self.patch_work()
        b['id'] = 'W-OTHER'; b['artifacts'][1]['sha256'] = 'a' * 64
        self.assert_refused('PATCH_CONFLICT', lambda: atlas.validate_graph([a, b]))
        b['artifacts'][1]['patch']['selectors'] = ['/different-field']
        atlas.validate_graph([a, b])
        b['artifacts'][1]['sha256'] = a['artifacts'][1]['sha256']
        b['artifacts'][1]['patch']['selectors'] = ['/limit']
        atlas.validate_graph([a, b])

    def test_activity_has_current_expired_and_unknown_states_without_rewriting_status(self):
        work = self.work('W-02')
        self.assertEqual(self.validate(work, '2026-10-17T03:05:00Z')['activity_state'], 'CURRENT')
        self.assertEqual(self.validate(work, '2026-10-17T03:10:00Z')['activity_state'], 'EXPIRED')
        self.assertEqual(work['state'], 'DOING')
        work['activity'] = None
        self.assertEqual(self.validate(work)['activity_state'], 'UNKNOWN')

    def test_activity_receipt_window_cannot_be_extended_without_new_proof(self):
        work = self.work('W-02'); work['activity']['valid_until'] = '2026-10-17T03:30:00Z'
        self.assert_refused('ACTIVITY_PROOF_EXPIRY', lambda: self.validate(work))
        before = self.load(); after = copy.deepcopy(before)
        w = next(w for w in after['atlas']['works'] if w['id'] == 'W-02')
        w['activity']['valid_until'] = '2026-10-17T03:30:00Z'
        w['evidence'][0]['valid_until'] = '2026-10-17T03:30:00Z'
        self.assert_refused('WORK_EVIDENCE_REWRITE|ACTIVITY_PROOF_REUSE_CHANGED', lambda: atlas.check_history(before, after))

    def test_activity_window_is_bounded_and_cannot_be_from_future(self):
        work = self.work('W-02'); work['activity']['valid_until'] = '2026-10-17T04:00:01Z'
        work['evidence'][0]['valid_until'] = work['activity']['valid_until']
        self.assert_refused('ACTIVITY_WINDOW_TOO_LONG', lambda: self.validate(work))
        work = self.work('W-02'); work['activity']['observed_at'] = '2026-10-17T03:20:00Z'
        self.assert_refused('ACTIVITY_WINDOW', lambda: self.validate(work))

    def test_activity_requires_matching_actor_work_scope_time_and_current_attempt(self):
        changes = [('actor', 'different', 'ACTIVITY_ACTOR_MISMATCH'), ('observed_at', '2026-10-17T03:01:00Z', 'ACTIVITY_PROOF_TIME')]
        for key, value, code in changes:
            with self.subTest(key=key):
                w = self.work('W-02'); w['activity'][key] = value
                self.assert_refused(code, lambda: self.validate(w))
        w = self.work('W-02'); w['evidence'][0]['work_id'] = 'W-OTHER'
        self.assert_refused('ACTIVITY_PROOF_WORK', lambda: self.validate(w))
        w = self.work('W-02'); w['evidence'][0]['scope'] = 'SOURCE'
        self.assert_refused('ACTIVITY_PROOF_SCOPE', lambda: self.validate(w))
        w = self.work('W-02'); w['events'].append({'id': 'EV-RESUME', 'kind': 'RESUMED', 'actor': w['assigned_to'], 'at': '2026-10-17T03:01:00Z', 'summary': 'New attempt', 'evidence_ids': []})
        self.assert_refused('ACTIVITY_BEFORE_CURRENT_ATTEMPT', lambda: self.validate(w))

    def test_packet_contains_named_work_dependencies_pins_and_existing_authority(self):
        s = self.load(); packet = atlas.packet(s, 'W-01')
        self.assertEqual(packet['work']['id'], 'W-01')
        self.assertEqual(packet['authority_ref'], s['atlas']['project']['authority_ref'])
        self.assertIn('not a new authorization', packet['authority_note'])
        self.assertEqual({d['id'] for d in packet['documents']}, {'DOC-PROJECT', 'DOC-CONTRACT', 'DOC-PATCH'})
        self.assertTrue(all('sha256' in d and 'content' not in d for d in packet['documents']))
        self.assert_refused('UNKNOWN_WORK', lambda: atlas.packet(s, 'NO-SUCH-WORK'))

    def test_packet_keeps_module_documentation_for_module_referenced_work(self):
        packet = atlas.packet(self.load(), 'W-02')
        self.assertTrue(packet['documents'], 'Module-only reference must not yield an empty context packet')
        self.assertEqual(packet['dependencies'][0]['id'], 'W-01')
        self.assertEqual(packet['dependencies'][0]['state'], 'ACCEPTED')

    def test_impact_propagates_declared_dependency_but_keeps_unrelated_paths_unmapped(self):
        result = atlas.impact(self.root, PROJECT, ['docs/CONTRACT-v1.md', 'unrelated/new.py'])
        self.assertEqual({x['id'] for x in result['affected']}, {'W-01', 'W-02', 'W-03'})
        self.assertEqual(next(x for x in result['affected'] if x['id'] == 'W-02')['reason'], 'DEPENDENCY_CHANGED')
        self.assertEqual(result['unmapped'], ['unrelated/new.py'])
        self.assertEqual(result['status'], 'DECLARED_IMPACT_ONLY')
        result = atlas.impact(self.root, PROJECT, ['src/batch2.py'])
        self.assertEqual(result['affected'], [])
        self.assertEqual(result['unmapped'], ['src/batch2.py'])

    def test_impact_maps_work_records_and_receipts_as_inputs(self):
        for path in ('.atlas/work/W-02.json', 'receipts/activity.json'):
            with self.subTest(path=path):
                result = atlas.impact(self.root, PROJECT, [path])
                self.assertEqual({x['id'] for x in result['affected']}, {'W-02', 'W-03'})
                self.assertEqual(result['unmapped'], [])

    def test_impact_is_available_after_source_drift_and_does_not_revalidate_or_execute(self):
        (self.root / 'src/batch.py').write_text('raise Exception("must not execute")\n', encoding='utf-8')
        before = self.tree()
        result = atlas.impact(self.root, PROJECT, ['src/batch.py'])
        self.assertEqual({x['id'] for x in result['affected']}, {'W-02', 'W-03'})
        self.assertEqual(self.tree(), before)

    def test_discover_unknown_files_are_metadata_candidates_without_content_or_semantic_claims(self):
        secret = 'SYNTHETIC_SENTINEL_DO_NOT_READ_UNREGISTERED_CONTENT'
        (self.root / 'docs/new-contract-patch.json').write_text(secret, encoding='utf-8')
        result = atlas.discover(self.root, PROJECT, ['docs/'])
        row = next(x for x in result['files'] if x['path'] == 'docs/new-contract-patch.json')
        self.assertEqual(row['classification'], 'UNREGISTERED')
        self.assertNotIn('sha256', row)
        self.assertNotIn('content', row)
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn('patch', row.keys())

    def test_discover_excludes_sensitive_hidden_roots_and_symlinks(self):
        for path in ('docs/.env', 'docs/secrets/hidden.json', 'docs/.aws/credentials.json', 'docs/.git/HEAD.json'):
            target = self.root / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_text('private synthetic', encoding='utf-8')
        (self.root / 'docs/link.json').symlink_to(self.root / 'receipts/activity.json')
        (self.root / 'docs/link-dir').symlink_to(self.root / 'receipts', target_is_directory=True)
        result = atlas.discover(self.root, PROJECT, ['docs/'])
        paths = [x['path'] for x in result['files']]
        self.assertFalse(any('hidden.json' in p or '.env' in p or 'credentials.json' in p or '/link' in p for p in paths))
        self.assert_refused('DISCOVERY_EXCLUDED_ROOT', lambda: atlas.discover(self.root, PROJECT, ['docs/secrets/']))
        self.assert_refused('UNSAFE_PATH', lambda: atlas.discover(self.root, PROJECT, ['../']))

    def test_discover_identifies_selected_document_drift_and_missing_files(self):
        baseline = atlas.discover(self.root, PROJECT, ['docs/'])
        self.assertEqual(next(x for x in baseline['files'] if x['path'] == 'docs/PROJECT.md')['classification'], 'UNCHANGED')
        target = self.root / 'docs/PROJECT.md'; target.write_bytes(target.read_bytes() + b'\nchanged')
        result = atlas.discover(self.root, PROJECT, ['docs/'])
        self.assertEqual(next(x for x in result['files'] if x['path'] == 'docs/PROJECT.md')['classification'], 'CHANGED')
        target.unlink(); result = atlas.discover(self.root, PROJECT, ['docs/'])
        self.assertEqual(next(x for x in result['files'] if x['path'] == 'docs/PROJECT.md')['classification'], 'MISSING_OR_EXCLUDED')

    def test_coverage_cannot_be_complete_when_binding_is_missing(self):
        self.project['coverage']['bindings'] = [b for b in self.project['coverage']['bindings'] if b['item_id'] != 'DOC-PATCH']
        self.write(PROJECT, self.project)
        c = self.load()['atlas']['coverage']
        self.assertEqual(c['status'], 'PARTIAL')
        self.assertIn('DOC-PATCH', next(d for d in c['domains'] if d['id'] == 'documents')['missing_ids'])
        del self.project['coverage']; self.write(PROJECT, self.project)
        self.assertEqual(self.load()['atlas']['coverage']['status'], 'UNKNOWN')

    def test_matrix_history_reference_bytes_are_pinned_not_a_filename_claim(self):
        self.write('history/matrix-0.json', {'old': 'matrix snapshot'})
        self.project['matrix_history'] = [{'id': 'M-0', 'at': '2026-10-17T02:00:00Z', 'source_ref': 'synthetic', 'kind': 'FULL_MATRIX', 'file': self.pin('history/matrix-0.json')}]
        self.write(PROJECT, self.project)
        self.assertEqual(self.load()['atlas']['matrix_history'][0]['id'], 'M-0')
        (self.root / 'history/matrix-0.json').write_bytes(b'changed')
        self.assert_refused('PIN_MISMATCH:matrix_history:M-0', self.load)


if __name__ == '__main__':
    unittest.main()
