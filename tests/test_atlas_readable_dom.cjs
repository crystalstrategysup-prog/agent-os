'use strict';
// Synthetic, local-only DOM/logic acceptance. No browser, native session, or network.
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const assert = require('node:assert/strict'), crypto = require('node:crypto'), {createRequire} = require('node:module');
const moduleRoot = process.env.ATLAS_READABLE_MODULE || path.resolve(__dirname, '../modules/atlas');
const viewerPath = process.env.ATLAS_READABLE_VIEWER || path.join(moduleRoot, 'skills/atlas/scripts/viewer.js');
const harnessPath = path.join(moduleRoot, 'tests/ui_dom.cjs');
let harnessCode = fs.readFileSync(harnessPath, 'utf8');
const locator = "const VIEWER = require.resolve('../skills/atlas/scripts/viewer.js');";
assert.ok(harnessCode.includes(locator), 'Known frozen harness viewer locator required');
harnessCode = harnessCode.replace(locator, `const VIEWER = ${JSON.stringify(viewerPath)};`);
const contextLine = 'const context = {document, console, Date: Clock, Blob, URL, setInterval: f => timers.push(f)};';
assert.ok(harnessCode.includes(contextLine), 'Known minimal harness context required');
harnessCode = harnessCode.replace(contextLine, contextLine + `
  context.window = {location: {hash: options.hash || ''}, listeners: {}, addEventListener(kind, f) { (this.listeners[kind] ??= []).push(f); }};
`);
const box = {require: createRequire(harnessPath), module: {exports: {}}, console};
vm.runInNewContext(harnessCode, box, {filename: harnessPath, timeout: 5000});
const {logic, createHarness, descendants} = box.module.exports;
const AT = '2026-01-01T10:00:00Z', NOW = Date.parse(AT), SHA = 'a'.repeat(64);
const matrix = {
  schema: 'synthetic.work-matrix/v1', revision: 7, project: 'Synthetic readable roadmap', updated_at: AT,
  unknown_extension: {preserve: ['unmodified', {value: 3}]},
  steps: [
    {id: 'STAGE', parent_id: null, title: 'Stage', order: 1, source_definition: {scope: 'Recorded source definition'}},
    {id: 'TASK', parent_id: 'STAGE', title: 'Task', order: 2},
    {id: 'LEAF', parent_id: 'TASK', title: 'Leaf <img src=x onerror=globalThis.INJECTED=true>', order: 1},
    {id: 'NEXT', parent_id: 'STAGE', title: 'Next', order: 1},
    {id: 'G', parent_id: null, title: 'Coordination', order: 9}
  ],
  events: [
    {id: 'E-LATER', step_id: 'LEAF', at: '2026-01-01T09:59:00Z', status: 'partial', accepted: false, note: 'Exact current source result', executor_ids: ['A', 'R'], reviewer_ids: ['OWNER'], contributor_ids: [], history_ids: ['OWNER', 'OWNER'], coordinator_id: 'OWNER', evidence: [{ref: 'evidence/result.json', label: 'Source reference, not new acceptance'}]},
    {id: 'E-EARLY', step_id: 'LEAF', at: '2026-01-01T09:00:00Z', status: 'done', accepted: true, note: 'Earlier scoped acceptance remains retained', executor_ids: ['A'], evidence: ['evidence/earlier.json']},
    {id: 'E-TIE', step_id: 'LEAF', at: '2026-01-01T09:59:00Z', status: 'partial', accepted: false, note: 'Same timestamp, later original array position'},
    {id: 'E-FUTURE', step_id: 'LEAF', at: '2026-01-01T11:00:00Z', status: 'done', accepted: true, note: 'Future record is retained, never effective at capture'},
    {id: 'E-NEXT', step_id: 'NEXT', at: '2026-01-01T09:30:00Z', status: 'done', accepted: true, note: 'Child acceptance cannot accept the stage', executor_ids: ['A']},
    {id: 'E-STAGE', step_id: 'STAGE', at: '2026-01-01T08:00:00Z', status: 'planned', accepted: false}
  ],
  actors: [{id: 'OWNER', label: 'Coordinator', role: 'Own the record', session_url: 'codex://threads/00000000-0000-0000-0000-000000000001'}, {id: 'A', label: 'Executor', role: 'Execute', session_url: null}, {id: 'R', label: 'Reviewer', role: 'Initial reviewer role', session_url: null}],
  actor_events: [{id: 'AE-1', actor_id: 'R', at: '2026-01-01T09:55:00Z', state: 'running', evidence: ['evidence/actor.json']}],
  actor_updates: [{id: 'AU-1', actor_id: 'R', at: '2026-01-01T09:56:00Z', role: 'Recorded review role'}, {id: 'AU-FUTURE', actor_id: 'R', at: '2026-01-01T11:00:00Z', role: 'Future role'}],
  activity_events: [{id: 'ACT-1', actor_id: 'A', step_id: 'LEAF', at: '2026-01-01T09:59:00Z', valid_until: '2026-01-01T10:20:00Z', state: 'active', evidence: [{source: 'supported_native_wait', ref: 'evidence/activity.json', actor_id: 'A', step_id: 'LEAF'}]}],
  coverage: {current_stage: 'STAGE', gaps: ['Synthetic explicit gap'], scope: 'Synthetic only'}, policy: {activity: 'Source observations are not new runtime validation'}, snapshot_summary: 'A retained result and its next scoped step.'
};
const content = JSON.stringify(matrix), matrixSHA = crypto.createHash('sha256').update(content).digest('hex');
const sourceDoc = {id: 'matrix.doc', title: 'Owning source matrix', lifecycle: 'current', path: 'imports/matrix.json', sha256: matrixSHA, bytes: Buffer.byteLength(content), content, source_ref: 'CURRENT.json [owning matrix projection source] pointer=/matrix', readback_at: AT};
function nativeWork(step) {
  return {id: step.id, title: step.title, parent_id: step.parent_id, state: 'PLANNED', writer: 'OWNER', assigned_to: 'UNKNOWN', objective: 'Synthetic objective', outcome: 'Synthetic outcome', criteria: [], acceptance: [], activity: null, evidence: [], events: [], depends_on: [], write_scope: [], artifacts: [], next_action: null,
    derived: {accepted_criteria: 0, total_criteria: 0, activity_state: 'UNKNOWN', completed_by: [], issues: []}};
}
const snapshot = {
  template_version: 'SYNTHETIC-READABLE', input_sha256: SHA,
  input: {project: {id: 'DEMO', title: 'Synthetic project'}, release: {id: 'SYNTHETIC.1', created_at: AT, previous: null}, documents: [sourceDoc],
    modules: [{id: 'module', title: 'Synthetic module', docs: ['matrix.doc'], dependencies: []}],
    contracts: [{id: 'contract', title: 'Read contract', contract_key: 'read', lifecycle: 'current', version: '1', module: 'module', state_owner: 'OWNER', input: 'identifier', output: 'record', auth: 'declared owner', usage: 'SOURCE only', parameters: [{name: 'id', type: 'string', required: true, description: 'Exact record'}], errors: [{code: 'NOT_FOUND', meaning: 'No record'}], docs: ['matrix.doc'], dependencies: []}],
    history: [{id: 'DOC-1', at: AT, kind: 'read', summary: 'Document snapshot', entity_ids: ['matrix.doc']}], relations: [], bindings: [], matrix: null},
  documents: [sourceDoc],
  atlas: {project: {id: 'DEMO', title: 'Synthetic project', writer: 'OWNER', objective: 'Readable, pinned project records', source_ref: 'CURRENT.json pointer=/matrix'}, as_of: AT,
    works: [...matrix.steps.map(nativeWork), nativeWork({id: 'ATLAS-GAP', title: 'Atlas metadata only', parent_id: null})],
    presentation: {schema: 'atlas.presentation/v1', renderer: 'ATLAS-READABLE-1.0.0', sections: ['roadmap', 'contracts', 'documents', 'actors', 'history', 'relations', 'coverage'], source_matrix_status: 'PINNED', source_matrix_doc_id: 'matrix.doc', source_matrix_sha256: matrixSHA},
    source_pins: [{path: sourceDoc.path, sha256: matrixSHA, bytes: sourceDoc.bytes}], coverage: {status: 'PARTIAL', domains: []}, matrix_history: [], matrix_history_total: 0, issues: []}
};
snapshot.atlas.works.find(w => w.id === 'LEAF').artifacts.push({id: 'A1', path: 'contract.md', sha256: SHA, bytes: 10, role: 'reference', entity_ids: ['contract', 'matrix.doc']});
const before = JSON.stringify(snapshot); let checks = 0;
function check(name, run) { try { run(); checks++; } catch (error) { error.message = name + ': ' + error.message; throw error; } }
const clone = value => JSON.parse(JSON.stringify(value));
function withMatrix(data) {
  const changed = clone(snapshot), content = JSON.stringify(data), sha256 = crypto.createHash('sha256').update(content).digest('hex'), bytes = Buffer.byteLength(content);
  for (const documents of [changed.documents, changed.input.documents]) Object.assign(documents.find(d => d.id === 'matrix.doc'), {content, sha256, bytes});
  changed.atlas.presentation.source_matrix_sha256 = sha256;
  Object.assign(changed.atlas.source_pins.find(p => p.path === sourceDoc.path), {sha256, bytes});
  return changed;
}
check('exact matrix binding and fail-closed legacy selector', () => {
  assert.equal(logic.matrixSource(snapshot).status, 'PINNED');
  const wrong = clone(snapshot); wrong.atlas.presentation.source_matrix_sha256 = SHA; assert.equal(logic.matrixSource(wrong).data, null);
  const unavailable = clone(snapshot); unavailable.atlas.presentation.source_matrix_status = 'UNAVAILABLE'; assert.equal(logic.matrixSource(unavailable).data, null);
  const legacy = clone(snapshot); delete legacy.atlas.presentation; assert.equal(logic.matrixSource(legacy).status, 'PINNED');
  legacy.atlas.project.source_ref = 'CURRENT.json pointer='; legacy.documents[0].source_ref = 'CURRENT.json [owning matrix projection source]'; assert.equal(logic.matrixSource(legacy).status, 'PINNED');
  legacy.documents[0].source_ref += ' pointer='; assert.equal(logic.matrixSource(legacy).status, 'PINNED', 'Actual importer retains the explicit empty pointer suffix');
  legacy.documents.push({...legacy.documents[0], id: 'duplicate', source_ref: 'CURRENT.json [owning matrix projection source]'}); assert.equal(logic.matrixSource(legacy).status, 'AMBIGUOUS');
});
check('lossless source export and stable source event chronology', () => {
  assert.deepEqual(logic.exportMatrix(snapshot), matrix);
  const model = logic.buildPresentation(snapshot); assert.equal(model.sourceLatest.get('LEAF').id, 'E-TIE');
  assert.deepEqual(logic.exportMatrix(snapshot).events.map(e => e.id), matrix.events.map(e => e.id));
  assert.deepEqual(logic.exportMatrix(snapshot).events[0].history_ids, ['OWNER', 'OWNER']);
  assert.equal(model.participants.get('R').role, 'Recorded review role');
  assert.equal(model.participants.size, 3, 'UNKNOWN is not an invented participant');
  const changed = clone(matrix); changed.actor_updates.push({id: 'AU-LINK', actor_id: 'OWNER', at: '2026-01-01T09:58:00Z', session_url: null});
  assert.equal(logic.buildPresentation(withMatrix(changed)).participants.get('OWNER').session_url, null, 'Explicit session-link withdrawal supersedes older URL');
  const malformed = clone(matrix); malformed.actors.unshift(null, 'retained raw value', {label: 'No declared identity'});
  const degraded = withMatrix(malformed), degradedModel = logic.buildPresentation(degraded);
  assert.equal(degradedModel.byId.size, snapshot.atlas.works.length); assert.equal(degradedModel.participants.size, 3); assert.equal(degradedModel.issues.length, 1);
  assert.deepEqual(logic.exportMatrix(degraded).actors, malformed.actors);
  assert.doesNotThrow(() => { const d = createHarness(degraded, {now: NOW}); d.button('tab', 'actors').click(); d.button('actor', 'A').click(); assert.match(d.elements.detail.textContent, /Executor/); });
});
check('deep hierarchy, source order, actor-role filters and separate metadata item', () => {
  const state = {query: '', workState: 'all', actor: '', expanded: new Set(['STAGE', 'TASK'])};
  const tree = logic.roadmapRows(snapshot, state, NOW); assert.deepEqual(tree.rows.map(r => r.id), ['STAGE', 'NEXT', 'TASK', 'LEAF', 'G', 'ATLAS-GAP']);
  assert.equal(tree.rows.find(r => r.id === 'LEAF').depth, 2); assert.equal(tree.rows.at(-1).metadata_only, true);
  const filtered = logic.roadmapRows(snapshot, {...state, actor: 'R'}, NOW); assert.deepEqual(filtered.rows.map(r => r.id), ['STAGE', 'TASK', 'LEAF']); assert.equal(filtered.rows[0].context_only, true);
  assert.deepEqual(logic.buildPresentation(snapshot).ownership.get('LEAF').executor_ids, ['A', 'R']);
  assert.equal(logic.roadmapRows(snapshot, {...state, expanded: new Set()}, NOW).rows.length, 3);
});
check('source observations cannot alter Atlas acceptance or establish parent/actor-only activity', () => {
  const model = logic.buildPresentation(snapshot);
  assert.equal(logic.sourceActivity(model, 'LEAF', NOW).state, 'CURRENT'); assert.equal(logic.sourceActivity(model, 'STAGE', NOW).state, 'UNKNOWN'); assert.equal(logic.sourceActivity(model, 'G', NOW).state, 'UNKNOWN');
  assert.equal(logic.sourceActivity(model, 'LEAF', Date.parse('2026-01-01T10:21:00Z')).state, 'EXPIRED');
  assert.equal(logic.sourceActivity(model, 'LEAF', NOW, 'EXPIRED').state, 'EXPIRED');
  assert.equal(snapshot.atlas.works.find(w => w.id === 'LEAF').derived.activity_state, 'UNKNOWN');
  assert.equal(snapshot.atlas.works.find(w => w.id === 'STAGE').state, 'PLANNED');
  const later = clone(snapshot); later.atlas.as_of = '2026-01-01T10:30:00Z'; assert.equal(logic.sourceActivity(logic.buildPresentation(later), 'LEAF', NOW).state, 'EXPIRED');
  for (const kind of ['actor_stop', 'work_block']) {
    const data = clone(matrix);
    if (kind === 'actor_stop') data.actor_events.push({id: 'STOP', actor_id: 'A', at: '2026-01-01T09:59:30Z', state: 'stopped'});
    else data.events.push({id: 'BLOCK', step_id: 'LEAF', at: '2026-01-01T09:59:30Z', status: 'blocked'});
    assert.equal(logic.sourceActivity(logic.buildPresentation(withMatrix(data)), 'LEAF', NOW).state, 'UNKNOWN');
    if (kind === 'actor_stop') data.actor_events.push({id: 'RESTART', actor_id: 'A', at: '2026-01-01T09:59:40Z', state: 'running'});
    else data.events.push({id: 'RESUME', step_id: 'LEAF', at: '2026-01-01T09:59:40Z', status: 'doing'});
    assert.equal(logic.sourceActivity(logic.buildPresentation(withMatrix(data)), 'LEAF', NOW).state, 'UNKNOWN', 'A restart cannot revive a superseded observation');
    data.activity_events.push({...data.activity_events[0], id: 'NEW-OBSERVATION', at: '2026-01-01T09:59:50Z'});
    assert.equal(logic.sourceActivity(logic.buildPresentation(withMatrix(data)), 'LEAF', NOW).state, 'CURRENT', 'A new supported exact-step observation can establish its own window');
  }
});
check('seven real routes and direct entity identity', () => {
  for (const section of snapshot.atlas.presentation.sections) assert.equal(logic.parseRoute('#' + section, snapshot).error, undefined);
  assert.equal(logic.parseRoute('#work/LEAF', snapshot).selection, 'LEAF'); assert.equal(logic.parseRoute('#actor/R', snapshot).selectionKind, 'actor');
  assert.equal(logic.parseRoute('#document/matrix.doc', snapshot).selection, 'matrix.doc'); assert.ok(logic.parseRoute('#contract/matrix.doc', snapshot).error);
  assert.ok(logic.parseRoute('#work/%E0%A4%A', snapshot).error); assert.equal(logic.routeFor('works'), '#roadmap');
});
const h = createHarness(snapshot, {now: NOW, hash: '#contracts'});
check('initial section route, selected work ancestor expansion and back navigation', () => {
  assert.equal(h.button('tab', 'contracts').attrs['aria-pressed'], 'true'); h.button('entity', 'contract').click(); assert.equal(h.context.window.location.hash, '#contract/contract');
  h.button('work', 'LEAF').click(); assert.equal(h.context.window.location.hash, '#work/LEAF'); assert.match(h.elements.detail.textContent, /Exact current source result/); assert.match(h.elements.detail.textContent, /Earlier scoped acceptance remains retained/);
  assert.ok(h.all().find(e => e.dataset.workId === 'LEAF')); assert.equal(h.all().some(e => e.tagName === 'img'), false);
  h.context.window.location.hash = '#contracts'; h.context.window.listeners.hashchange.forEach(f => f()); assert.equal(h.button('tab', 'contracts').attrs['aria-pressed'], 'true');
});
check('participants preserve roles, no fabricated session links, and complete source history', () => {
  h.button('tab', 'actors').click(); h.button('actor', 'R').click(); assert.match(h.elements.detail.textContent, /Recorded review role/); assert.match(h.elements.detail.textContent, /UNKNOWN \/ not declared/);
  assert.equal(descendants(h.elements.detail).some(e => e.tagName === 'a' && String(e.href).startsWith('codex:')), false);
  h.button('tab', 'history').click(); for (const e of matrix.events) assert.match(h.elements.list.textContent, new RegExp(e.id));
  assert.match(h.elements.list.textContent, /Source role update/); assert.match(h.elements.list.textContent, /DOC-1/);
});
check('machine exports retain original values and arrays', () => {
  h.button('tab', 'works').click(); h.button('matrixDownload', 'true').click(); const output = h.downloads.at(-1);
  assert.equal(output.filename, 'owning-matrix.json'); assert.deepEqual(JSON.parse(output.blob.parts.join('')), matrix);
  assert.equal(output.blob.parts.join(''), sourceDoc.content); assert.equal(crypto.createHash('sha256').update(output.blob.parts.join('')).digest('hex'), matrixSHA);
  h.button('snapshotDownload', 'true').click(); assert.deepEqual(JSON.parse(h.downloads.at(-1).blob.parts.join('')), snapshot);
  assert.equal(JSON.stringify(snapshot), before);
});
check('visible source activity expires without rollback promotion or native badges', () => {
  h.button('expandAll', 'true').click(); let row = h.all().find(e => e.dataset.workId === 'LEAF'); assert.match(row.textContent, /Source observation: CURRENT/);
  assert.equal(descendants(row).some(e => e.className.includes('activity-current')), false);
  h.clock.now = Date.parse('2026-01-01T10:30:00Z'); h.timers.forEach(f => f()); row = h.all().find(e => e.dataset.workId === 'LEAF'); assert.match(row.textContent, /Source observation: EXPIRED/);
  h.clock.now = NOW; h.timers.forEach(f => f()); h.elements.reset.click(); assert.match(h.all().find(e => e.dataset.workId === 'LEAF').textContent, /Source observation: EXPIRED/);
});
// Reuse all 47 Atlas regressions without rewriting assertions. The source test declares 7 sections.
const legacyPath = process.env.ATLAS_READABLE_LEGACY_TEST || path.join(moduleRoot, 'tests/test_atlas_ui.cjs');
const legacy = fs.readFileSync(legacyPath, 'utf8');
assert.ok(legacy.includes('elements.tabs.children.length, 7'), 'The updated module test must declare seven navigation sections');
let legacyResult;
const legacyRequire = createRequire(legacyPath);
vm.runInNewContext(legacy, {require: name => name === './ui_dom.cjs' ? box.module.exports : legacyRequire(name), console: {log(value) { legacyResult = JSON.parse(value); }}}, {filename: legacyPath, timeout: 10000});
assert.equal(legacyResult.status, 'PASS'); assert.equal(legacyResult.checks, 47);
console.log(JSON.stringify({status: 'PASS', checks, retained_atlas_regressions: legacyResult.checks, approved_expected_change: 'Navigation count 5 -> 7', level: 'PURE_LOGIC_AND_MINIMAL_DOM_NOT_VISUAL', network: false, browser_visual_acceptance: 'NOT_RUN'}));
