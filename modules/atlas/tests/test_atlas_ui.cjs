'use strict';
// UI state/DOM contract checks, synthetic data only. No browser or visual acceptance.
const assert = require('node:assert/strict');
const {logic, createHarness, descendants} = require('./ui_dom.cjs');
const SHA_A = 'a'.repeat(64), SHA_B = 'b'.repeat(64), SHA_C = 'c'.repeat(64);
const NOW = Date.parse('2026-01-01T10:00:00Z');
const source = {id: 'ART-SOURCE', path: 'src/example.py', sha256: SHA_A, bytes: 8, role: 'source', entity_ids: ['doc.project', 'contract.demo']};
const patch = {id: 'ART-PATCH', path: 'docs/patch.md', sha256: SHA_B, bytes: 10, role: 'contract_patch', entity_ids: ['doc.project'],
  patch: {target_id: 'ART-SOURCE', base_sha256: SHA_A, selectors: ['/method/input'], state: 'ACCEPTED_UNAPPLIED', decision_evidence_ids: ['EV-SOURCE'], result_artifact_id: null}};
const evidence = {id: 'EV-SOURCE', scope: 'SOURCE', subjects: [{artifact_id: 'ART-SOURCE', sha256: SHA_A}], environment: 'synthetic-sandbox', actor: 'reviewer', at: '2026-01-01T09:20:00Z', receipt: {path: 'receipts/source.json', sha256: SHA_C, bytes: 7}, result: 'PASS'};
function work(id, overrides = {}) {
  return {id, parent_id: null, title: id, objective: 'Verifiable objective', outcome: 'Verifiable outcome', criteria: [{id: 'C1', text: 'Source accuracy', required_scope: 'SOURCE'}], state: 'PLANNED', writer: 'coordinator', assigned_to: ['actor-a'], write_scope: ['src/'], depends_on: [], artifacts: [], evidence: [], acceptance: [], activity: null, blocker: null, result: null, remaining: 'Not completed', next_action: {actor: 'actor-a', action: 'Obtain input'}, events: [], derived: {basis_sha256: SHA_C, activity_state: 'UNKNOWN', accepted_criteria: 0, total_criteria: 1, completed_by: [], issues: []}, ...overrides};
}
const snapshot = {
  template_version: 'ATLAS-UI-SYNTHETIC', input_sha256: SHA_C,
  input: {project: {id: 'DEMO', title: 'Project documents', scope_note: 'Synthetic only'}, release: {id: 'ui-demo', created_at: '2026-01-01T10:00:00Z', previous: null},
    documents: [{id: 'doc.project', title: 'Project documentation', lifecycle: 'current', path: 'PROJECT.md', sha256: SHA_A, bytes: 8}],
    modules: [{id: 'module.demo', title: 'Example module', purpose: 'Check relationships', state_owner: 'module.demo', dependencies: [], docs: ['doc.project']}],
    contracts: [{id: 'contract.demo', title: 'Example contract', lifecycle: 'current', module: 'module.demo', contract_key: 'demo.read', version: '1', state_owner: 'module.demo', input: 'id', output: 'result', auth: 'owner', usage: 'SOURCE', parameters: [], errors: [], dependencies: [], docs: ['doc.project']}],
    relations: [{from: 'contract.demo', to: 'doc.project', type: 'documented_by', evidence_docs: ['doc.project']}], history: [{id: 'DOC-E1', at: '2026-01-01T07:00:00Z', kind: 'created', summary: 'Document created', entity_ids: ['doc.project']}], bindings: [], matrix: null},
  documents: [{id: 'doc.project', title: 'Project documentation', lifecycle: 'current', version: '1', content: '<script>globalThis.INJECTED=true</script>', path: 'PROJECT.md', sha256: SHA_A, bytes: 8, source_ref: 'synthetic', readback_at: '2026-01-01T09:00:00Z'}], matrix_snapshot: null,
  atlas: {project: {id: 'DEMO', title: 'Atlas synthetic project', objective: 'Link all work items and documents', scope_note: 'Synthetic UI fixture', mode: 'PRIVATE', writer: 'coordinator'}, as_of: '2026-01-01T10:00:00Z',
    works: [
      work('WORK-ROOT', {title: 'Whole project'}),
      work('WORK-A', {parent_id: 'WORK-ROOT', title: 'Contract binding <img src=x onerror=globalThis.INJECTED=true>', objective: 'Bind the contract to its source', outcome: 'Exact links and evidence', state: 'DOING', artifacts: [source, patch], evidence: [evidence],
        criteria: [{id: 'C1', text: 'Source accuracy', required_scope: 'SOURCE'}, {id: 'C2', text: 'Application in the environment', required_scope: 'INSTALLED'}],
        acceptance: [{criterion_id: 'C1', decision: 'ACCEPTED', actor: 'reviewer', at: '2026-01-01T09:25:00Z', evidence_ids: ['EV-SOURCE'], basis_sha256: SHA_C}],
        activity: {actor: 'actor-a', observed_at: '2026-01-01T09:00:00Z', valid_until: '2026-01-01T11:00:00Z', evidence_id: 'EV-SOURCE'},
        derived: {basis_sha256: SHA_C, activity_state: 'CURRENT', accepted_criteria: 1, total_criteria: 2, completed_by: ['reviewer'], issues: ['C2 has no acceptance']},
        next_action: {actor: 'operator', action: 'Provide an application receipt'},
        events: [{id: 'WORK-E1', at: '2026-01-01T09:25:00Z', actor: 'reviewer', kind: 'acceptance', summary: 'Source criterion accepted', evidence_ids: ['EV-SOURCE']}]}),
      work('WORK-B', {parent_id: 'WORK-ROOT', title: 'Expired activity', state: 'DOING', assigned_to: ['actor-b'],
        activity: {actor: 'actor-b', observed_at: '2026-01-01T08:00:00Z', valid_until: '2026-01-01T09:50:00Z', evidence_id: 'EV-OLD'},
        derived: {basis_sha256: SHA_A, activity_state: 'CURRENT', accepted_criteria: 0, total_criteria: 1, completed_by: [], issues: []}, next_action: null}),
      work('WORK-C', {title: 'Blocked work item', state: 'BLOCKED', depends_on: ['WORK-A'],
        blocker: {reason: 'Required input missing', unblock_condition: 'Receipt obtained', next_owner: 'owner'},
        activity: {actor: 'actor-a', observed_at: '2026-01-01T09:00:00Z', valid_until: '2026-01-02T10:00:00Z', evidence_id: 'EV-NOT-VERIFIED'}}),
      work('WORK-D', {title: 'Completed work item', state: 'ACCEPTED', assigned_to: 'actor-c', result: 'Change accepted',
        derived: {basis_sha256: SHA_B, activity_state: 'EXPIRED', accepted_criteria: 1, total_criteria: 1, completed_by: ['reviewer'], issues: []},
        activity: {actor: 'actor-c', observed_at: '2026-01-01T09:00:00Z', valid_until: '2026-01-02T10:00:00Z', evidence_id: 'EV-NOT-CURRENT'}}),
      work('WORK-U', {title: 'Unknown derived assessment', state: 'REVIEW', assigned_to: [], derived: undefined,
        acceptance: [{criterion_id: 'C1', decision: 'ACCEPTED', actor: 'reviewer', at: '2026-01-01T09:25:00Z', evidence_ids: ['EV-UNVERIFIED'], basis_sha256: SHA_A}]})
    ], summary: {}, issues: ['Partial synthetic coverage'], source_pins: [{path: 'WORKS.json', sha256: SHA_C, bytes: 50}],
    document_release: {id: 'original-doc-release', created_at: '2026-01-01T09:00:00Z'},
    coverage: {status: 'PARTIAL', domains: [{id: 'CORE', title: 'Core', inventory_count: 2, documented_count: 1, missing_ids: ['MISSING-CORE-METHOD'], status: 'PARTIAL'}], issues: ['Some methods are undocumented']},
    revisions: [{id: 'matrix-revision-0', path: 'releases/matrix-revision-0/snapshot.json', sha256: SHA_A}]
  }
};
let checks = 0;
function check(name, test) { try { test(); checks++; } catch (error) { error.message = `${name}: ${error.message}`; throw error; } }
const original = JSON.stringify(snapshot), state = {tab: 'works', query: '', workState: 'all', actor: '', lifecycle: 'current', module: ''};
const byWork = id => snapshot.atlas.works.find(w => w.id === id);
check('all work rows', () => assert.equal(logic.derive(snapshot, state).length, 6));
check('state filter', () => assert.deepEqual(logic.derive(snapshot, {...state, workState: 'DOING'}).map(x => x.id), ['WORK-A', 'WORK-B']));
check('actor assignment array and scalar', () => { assert.equal(logic.derive(snapshot, {...state, actor: 'actor-c'})[0].id, 'WORK-D'); assert.equal(logic.derive(snapshot, {...state, actor: 'actor-a'}).length, 3); });
check('historical actor is searchable/filterable', () => assert.equal(logic.derive(snapshot, {...state, actor: 'reviewer'}).length, 3));
check('path and actor search', () => { assert.equal(logic.derive(snapshot, {...state, query: 'SRC/EXAMPLE.PY'})[0].id, 'WORK-A'); assert.equal(logic.derive(snapshot, {...state, query: 'actor-b'})[0].id, 'WORK-B'); });
check('combined filters', () => assert.equal(logic.derive(snapshot, {...state, actor: 'actor-c', workState: 'DOING'}).length, 0));
check('reset filters leaves tab', () => { const s = {...state, actor: 'actor-c', workState: 'DOING', query: 'x', selection: 'WORK-D'}; logic.reset(s); assert.equal(s.tab, 'works'); assert.equal(s.workState, 'all'); assert.equal(s.actor, ''); assert.equal(s.selection, null); });
check('open work', () => { const s = {...state}; assert.equal(logic.openWork(snapshot, s, 'WORK-A'), true); assert.equal(s.selectionKind, 'work'); assert.equal(s.tab, 'works'); });
check('unknown work stays closed', () => assert.equal(logic.openWork(snapshot, {...state}, 'MISSING'), false));
check('generic openEntity accepts work fallback', () => { const s = {...state}; assert.equal(logic.openEntity(snapshot, s, 'WORK-A'), true); assert.equal(s.tab, 'works'); });
check('progress uses only provided derived', () => { assert.equal(logic.criterionProgress(byWork('WORK-A')), '1 / 2'); assert.equal(logic.criterionProgress(byWork('WORK-U')), 'UNKNOWN'); assert.equal(logic.criterionProgress({derived: {accepted_criteria: 3, total_criteria: 2}}), 'UNKNOWN'); });
check('current needs stored assessment', () => { assert.equal(logic.activityState(byWork('WORK-A'), NOW), 'CURRENT'); assert.equal(logic.activityState(byWork('WORK-C'), NOW), 'UNKNOWN'); });
check('expired is not promoted', () => assert.equal(logic.activityState(byWork('WORK-D'), NOW), 'EXPIRED'));
check('clock expires activity', () => assert.equal(logic.activityState(byWork('WORK-B'), NOW), 'EXPIRED'));
check('clock reversal cannot promote expired', () => assert.equal(logic.activityState(byWork('WORK-A'), NOW, 'EXPIRED'), 'EXPIRED'));
check('current missing receipt interval is unknown', () => assert.equal(logic.activityState({...byWork('WORK-A'), activity: null}, NOW), 'UNKNOWN'));
check('missing derived cannot establish activity', () => assert.equal(logic.activityState({...byWork('WORK-A'), derived: {}}, NOW), 'UNKNOWN'));
check('history includes documents and work events', () => assert.deepEqual(logic.derive(snapshot, {...state, tab: 'history'}).map(x => x.id), ['WORK-E1', 'DOC-E1']));
check('relations include work/document/patch/dependency', () => { const rows = logic.derive(snapshot, {...state, tab: 'relations'}); assert.ok(rows.some(x => x.atlas_relation === 'patch')); assert.ok(rows.some(x => x.from === 'WORK-C' && x.to === 'WORK-A')); assert.ok(rows.some(x => x.from === 'WORK-A' && x.to === 'doc.project')); });
check('index export roundtrip is exact input', () => { assert.equal(logic.exportIndex(snapshot), snapshot.input); assert.deepEqual(JSON.parse(JSON.stringify(logic.exportIndex(snapshot))), snapshot.input); });
const h = createHarness(snapshot, {now: NOW});
const {elements, button, byId, all, context, clock, timers, downloads} = h;
const workCard = id => all().find(e => e.dataset.workId === id);
check('starts on works with seven sections', () => { assert.equal(button('tab', 'works').attrs['aria-pressed'], 'true'); assert.equal(elements.tabs.children.length, 7); assert.match(elements.summary.textContent, /6 work items/); });
check('project title and snapshot time visible', () => { assert.equal(elements.title.textContent, 'Atlas synthetic project'); assert.match(elements.release.textContent, /2026-01-01T10:00:00Z/); assert.match(elements.release.textContent, /not refreshed/); });
check('coverage is not falsely complete', () => { assert.match(elements.list.textContent, /Project coverage: PARTIAL/); assert.match(elements.list.textContent, /MISSING-CORE-METHOD/); });
check('record state and activity separate', () => { assert.match(workCard('WORK-B').textContent, /Recorded state: DOING/); assert.match(workCard('WORK-B').textContent, /Activity: EXPIRED/); assert.equal(descendants(workCard('WORK-B')).some(e => e.className.includes('activity-current')), false); });
check('unknown activity is never colored current', () => { assert.match(workCard('WORK-C').textContent, /Activity: UNKNOWN/); assert.equal(descendants(workCard('WORK-C')).some(e => e.className.includes('activity-current')), false); });
check('child work is distinguishable and parent accessible', () => { assert.match(workCard('WORK-A').className, /child-work/); assert.match(workCard('WORK-A').textContent, /Child work of/); assert.ok(descendants(workCard('WORK-A')).some(e => e.dataset.work === 'WORK-ROOT')); });
check('owner result blocker next action visible', () => { assert.match(workCard('WORK-A').textContent, /Exact links and evidence/); assert.match(workCard('WORK-A').textContent, /coordinator/); assert.match(workCard('WORK-A').textContent, /Provide an application receipt/); assert.match(workCard('WORK-C').textContent, /Required input missing/); assert.match(workCard('WORK-C').textContent, /Receipt obtained/); });
check('unknown acceptance remains unknown', () => assert.match(workCard('WORK-U').textContent, /Accepted criteria UNKNOWN/));
check('hostile title is plain text', () => { assert.match(workCard('WORK-A').textContent, /<img src=x/); assert.equal(descendants(elements.list).some(e => ['img', 'script'].includes(e.tagName)), false); assert.equal(context.INJECTED, undefined); });
check('DOM state filter', () => { byId('work-state').value = 'DOING'; byId('work-state').dispatch('change'); assert.match(elements.summary.textContent, /2 work items/); });
check('DOM actor plus state filter', () => { byId('work-actor').value = 'actor-b'; byId('work-actor').dispatch('change'); assert.match(elements.summary.textContent, /1 work items/); assert.ok(workCard('WORK-B')); });
check('reset clears both new filters', () => { elements.reset.click(); assert.equal(byId('work-state').value, 'all'); assert.equal(byId('work-actor').value, ''); assert.match(elements.summary.textContent, /6 work items/); });
check('search path', () => { elements.search.value = 'docs/patch.md'; elements.search.dispatch('input'); assert.match(elements.summary.textContent, /1 work items/); assert.ok(workCard('WORK-A')); });
check('details show acceptance evidence and patch basis', () => { button('work', 'WORK-A').click(); assert.match(elements.detail.textContent, /Bind the contract to its source/); assert.match(elements.detail.textContent, /EV-SOURCE · SOURCE · PASS/); assert.match(elements.detail.textContent, /Criteria and acceptance decisions/); assert.match(elements.detail.textContent, /Decision basis SHA256/); assert.match(elements.detail.textContent, /Patch · ACCEPTED_UNAPPLIED/); assert.match(elements.detail.textContent, /Base version SHA256/); assert.match(elements.detail.textContent, new RegExp(SHA_A)); assert.match(elements.detail.textContent, /Complete work record/); });
check('work artifact links to document', () => { button('entity', 'doc.project').click(); assert.equal(button('tab', 'documents').attrs['aria-pressed'], 'true'); assert.match(elements.detail.textContent, /Linked work items/); assert.match(elements.detail.textContent, /Readback UTC/); });
check('document has return work link', () => { const back = descendants(elements.detail).find(e => e.dataset.work === 'WORK-A'); assert.ok(back); back.click(); assert.equal(button('tab', 'works').attrs['aria-pressed'], 'true'); });
check('contract has return work link', () => { button('entity', 'contract.demo').click(); assert.equal(button('tab', 'contracts').attrs['aria-pressed'], 'true'); assert.ok(descendants(elements.detail).some(e => e.dataset.work === 'WORK-A')); });
check('Atlas history shows all pinned data with limits', () => { button('tab', 'history').click(); assert.match(elements.list.textContent, /WORK-E1/); assert.match(elements.list.textContent, /DOC-E1/); assert.match(elements.list.textContent, /matrix-revision-0/); assert.match(elements.list.textContent, /Complete immutable release history is stored separately/); });
check('relation cards preserve patch state and base SHA', () => { button('tab', 'relations').click(); assert.match(elements.list.textContent, /ACCEPTED_UNAPPLIED/); assert.match(elements.list.textContent, /Base version SHA256/); });
check('work controls hide outside works', () => { assert.equal(byId('work-state').closest('.work-filters').hidden, true); button('tab', 'works').click(); assert.equal(byId('work-state').closest('.work-filters').hidden, false); });
check('download label distinguishes document projection', () => { assert.equal(elements.download.textContent, 'Download document index'); assert.match(elements.download.title, /projection/); elements.download.click(); assert.equal(downloads.at(-1).filename, 'DOCS_INDEX.json'); assert.deepEqual(JSON.parse(downloads.at(-1).blob.parts.join('')), snapshot.input); });
check('full snapshot export includes Atlas and provenance', () => { elements.reset.click(); button('snapshotDownload', 'true').click(); const last = downloads.at(-1); assert.equal(last.filename, 'snapshot.json'); assert.deepEqual(JSON.parse(last.blob.parts.join('')).atlas.source_pins, snapshot.atlas.source_pins); });
check('clock ages visible activity without changing historic state', () => { clock.now = Date.parse('2026-01-01T12:00:00Z'); timers.forEach(f => f()); assert.match(workCard('WORK-A').textContent, /Activity: EXPIRED/); assert.match(workCard('WORK-A').textContent, /Recorded state: DOING/); });
check('clock reversal does not revive active appearance', () => { clock.now = NOW; timers.forEach(f => f()); elements.reset.click(); assert.match(workCard('WORK-A').textContent, /Activity: EXPIRED/); });
check('absent coverage and revisions are UNKNOWN', () => { const s = JSON.parse(JSON.stringify(snapshot)); delete s.atlas.coverage; delete s.atlas.revisions; const u = createHarness(s, {now: NOW}); assert.match(u.elements.list.textContent, /Project coverage: UNKNOWN/); u.button('tab', 'history').click(); assert.match(u.elements.list.textContent, /History completeness: UNKNOWN/); });
check('matrix history references from core are visible', () => { const s = JSON.parse(JSON.stringify(snapshot)); delete s.atlas.revisions; s.atlas.matrix_history = [{id: 'OLD-MATRIX-1', at: '2025-12-31T12:00:00Z', file: {path: 'history/old.json', sha256: SHA_A, bytes: 10}}]; const u = createHarness(s, {now: NOW}); u.button('tab', 'history').click(); assert.match(u.elements.list.textContent, /OLD-MATRIX-1/); assert.match(u.elements.list.textContent, /history\/old.json/); });
check('UI and pure helpers do not mutate source', () => assert.equal(JSON.stringify(snapshot), original));
console.log(JSON.stringify({status: 'PASS', checks, level: 'PURE_LOGIC_AND_MINIMAL_DOM_NOT_VISUAL', network: false, browser_visual_acceptance: 'NOT_RUN'}));
