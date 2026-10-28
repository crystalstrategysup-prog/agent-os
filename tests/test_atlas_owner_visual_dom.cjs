'use strict';
// Synthetic checks for the owner's table interactions. CSS pixels need the separate browser receipt.
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const assert = require('node:assert/strict'), {createRequire} = require('node:module');
const repo = path.resolve(__dirname, '..'), previousPath = path.join(__dirname, 'test_atlas_readable_dom.cjs');
const results = [];
const previous = {exports: {}};
// The existing nine groups and all 47 retained assertions execute unchanged.
// Keep their fixtures in Node's realm, matching their normally required logic module.
const runPrevious = new Function('require', 'module', 'exports', '__filename', '__dirname', 'process', 'Buffer', 'console',
  fs.readFileSync(previousPath, 'utf8') + '\nmodule.exports = {snapshot, matrix, NOW, withMatrix};');
runPrevious(createRequire(previousPath), previous, previous.exports, previousPath, __dirname, process, Buffer,
  {log(value) { results.push(JSON.parse(value)); }});
const fixture = previous.exports, clone = value => JSON.parse(JSON.stringify(value));
const harnessPath = path.join(repo, 'modules/atlas/tests/ui_dom.cjs');
const viewerPath = path.join(repo, 'modules/atlas/skills/atlas/scripts/viewer.js');
let harness = fs.readFileSync(harnessPath, 'utf8');
const contextLine = 'const context = {document, console, Date: Clock, Blob, URL, setInterval: f => timers.push(f)};';
assert.ok(harness.includes(contextLine));
harness = harness.replace("const VIEWER = require.resolve('../skills/atlas/scripts/viewer.js');", 'const VIEWER = ' + JSON.stringify(viewerPath) + ';');
// Add browser platform primitives to the frozen minimal DOM; no product assertions are replaced.
harness = harness.replace(contextLine, contextLine + `
  const memory = options.storage || new Map();
  context.reloads = 0;
  context.window = {
    location: {hash: options.hash || '', pathname: options.pathname || '', reload() { context.reloads++; }}, listeners: {},
    sessionStorage: {getItem(k) { return memory.get(k) || null; }, setItem(k, v) { memory.set(k, String(v)); }},
    addEventListener(k, f) { (this.listeners[k] ??= []).push(f); }, scrollX: 0, scrollY: 0,
    scrollTo(pos) { this.scrollX = pos.left; this.scrollY = pos.top; }, getSelection() { return options.selection || ''; }
  };
  Element.prototype.focus = function () { document.activeElement = this; };
  Element.prototype.setSelectionRange = function (a, b) { this.selectionStart = a; this.selectionEnd = b; };
  Element.prototype.scrollIntoView = function () { this.scrolledIntoView = true; };
`);
const box = {require: createRequire(harnessPath), module: {exports: {}}, console};
vm.runInNewContext(harness, box, {filename: harnessPath, timeout: 5000});
const {createHarness, descendants} = box.module.exports;
let checks = 0;
function check(name, run) { try { run(); checks++; } catch (error) { error.message = name + ': ' + error.message; throw error; } }
const create = (data = fixture.snapshot, options = {}) => createHarness(clone(data), {now: fixture.NOW, ...options});
const row = (h, id) => h.all().find(e => e.className.split(' ').includes('step-row') && e.dataset.stepId === id);
const detailButton = (h, id) => h.button('ownerDetail', id);

check('the supplied six-column table and compact controls are the primary Atlas view', () => {
  const h = create();
  assert.equal(h.document.body.attrs['data-owner-matrix'], 'true');
  assert.ok(h.byId('owner-matrix')); assert.ok(h.byId('rows'));
  const headings = h.all().filter(e => e.tagName === 'th').map(e => e.textContent);
  assert.equal(JSON.stringify(headings), JSON.stringify(['Шаг / уровень', 'Статус', 'Исполнители', 'История', 'Время · источник', 'Детали']));
  for (const id of ['matrix-search', 'filter', 'actor-filter', 'active-now', 'expand', 'collapse', 'refresh', 'auto-refresh', 'export', 'count']) assert.ok(h.byId(id), id);
  assert.equal(h.byId('roster').open, false); assert.equal(h.byId('auto-refresh').checked, false);
  assert.match(h.byId('metadata').textContent, /Atlas собран:.*Снимок: SYNTHETIC\.1/);
  assert.equal(h.elements.tabs.children.length, 7);
  assert.equal(h.all().some(e => ['img', 'iframe'].includes(e.tagName)), false);
});

check('one-level row and keyboard actions retain rails through inline details', () => {
  const h = create(); h.byId('collapse').click(); row(h, 'STAGE').click();
  assert.ok(row(h, 'TASK')); assert.equal(row(h, 'LEAF'), undefined);
  row(h, 'TASK').click(); assert.ok(row(h, 'LEAF'));
  const rails = descendants(row(h, 'LEAF')).filter(e => e.className.includes('tree-segment'));
  assert.ok(rails.length > 0); assert.ok(rails.some(e => e.className.includes('terminal')));
  row(h, 'LEAF').click(); assert.ok(h.all().some(e => e.dataset.detailFor === 'LEAF'));
  const panelRow = h.all().find(e => e.dataset.detailFor === 'LEAF');
  assert.equal(panelRow.children[0].colSpan, 6); assert.match(panelRow.textContent, /Exact current source result/);
  assert.match(panelRow.textContent, /Earlier scoped acceptance remains retained/);
  assert.ok(descendants(panelRow).some(e => e.className === 'panel-body'));
  assert.ok(descendants(panelRow).some(e => e.className === 'tree-rails'));
  detailButton(h, 'LEAF').click(); assert.equal(h.all().some(e => e.dataset.detailFor === 'LEAF'), false);
  const task = row(h, 'TASK'); task.listeners.keydown.forEach(f => f({target: task, key: 'Enter', preventDefault() {}}));
  assert.equal(row(h, 'LEAF'), undefined);
});

check('filter editing preserves focus and matched ancestry; source activity still expires', () => {
  const source = clone(fixture.matrix); source.events.find(e => e.id === 'E-TIE').status = 'doing';
  const h = create(fixture.withMatrix(source)), search = h.byId('matrix-search'); search.focus(); search.value = 'Earlier scoped'; search.setSelectionRange(6, 6); search.dispatch('input');
  assert.equal(h.document.activeElement, h.byId('matrix-search')); assert.equal(h.document.activeElement.selectionStart, 6);
  assert.ok(row(h, 'STAGE')); assert.ok(row(h, 'TASK')); assert.ok(row(h, 'LEAF')); assert.equal(row(h, 'NEXT'), undefined);
  h.byId('active-now').click(); assert.equal(h.byId('matrix-search').value, ''); assert.equal(h.byId('filter').value, 'active');
  assert.ok(row(h, 'LEAF')); assert.equal(row(h, 'STAGE').dataset.sourceActivity, 'UNKNOWN');
  h.clock.now = Date.parse('2026-01-01T10:30:00Z'); h.timers.forEach(f => f()); assert.equal(row(h, 'LEAF'), undefined);
  h.byId('active-now').click(); h.byId('expand').click(); assert.equal(row(h, 'LEAF').dataset.sourceActivity, 'EXPIRED');
  assert.equal(descendants(row(h, 'LEAF')).find(e => e.className === 'badge-label').textContent, 'В работе');
  assert.equal(row(h, 'LEAF').className.split(' ').includes('current'), false);
  h.clock.now = fixture.NOW; h.timers.forEach(f => f()); assert.equal(row(h, 'LEAF').dataset.sourceActivity, 'EXPIRED');
});

check('participant chips open the source roster and preserve contract return routes', () => {
  const h = create(); h.byId('expand').click();
  const chip = descendants(row(h, 'LEAF')).find(e => e.dataset.ownerActor === 'A'); assert.ok(chip); chip.click();
  assert.equal(h.byId('roster').open, true); assert.equal(h.byId('actor-A').scrolledIntoView, true);
  detailButton(h, 'LEAF').click(); assert.equal(h.elements.detail.closest('tr').className, 'details-row');
  const link = descendants(h.elements.detail).find(e => e.dataset.entity === 'contract'); assert.ok(link); link.click();
  assert.equal(h.context.window.location.hash, '#contract/contract'); assert.match(h.elements.detail.textContent, /Parameters/);
  h.button('work', 'LEAF').click(); assert.equal(h.context.window.location.hash, '#work/LEAF');
  assert.equal(h.elements.detail.closest('tr').dataset.detailFor, 'LEAF');
  assert.match(h.elements.detail.textContent, /Complete work record/);
});

check('native Atlas and unavailable source use the same table without inventing an imported matrix', () => {
  const data = clone(fixture.snapshot); data.atlas.presentation.source_matrix_status = 'UNAVAILABLE'; data.atlas.presentation.source_matrix_doc_id = null; data.atlas.presentation.source_matrix_sha256 = null;
  const before = JSON.stringify(data), h = create(data); assert.equal(h.document.body.attrs['data-owner-matrix'], 'true'); assert.ok(h.byId('rows'));
  assert.equal(row(h, 'LEAF').dataset.sourceActivity, 'UNKNOWN'); assert.match(h.byId('metadata').textContent, /SYNTHETIC.1/);
  detailButton(h, 'LEAF').click(); assert.match(h.elements.detail.textContent, /Synthetic objective/);
  h.byId('export').click(); assert.deepEqual(JSON.parse(h.downloads.at(-1).blob.parts.join('')), data); assert.equal(JSON.stringify(data), before);
  const activeData = clone(data), parent = activeData.atlas.works.find(w => w.id === 'TASK');
  parent.state = 'DOING'; parent.derived.activity_state = 'CURRENT';
  parent.activity = {actor: 'OWNER', observed_at: '2026-01-01T09:59:00Z', valid_until: '2026-01-01T10:20:00Z', evidence_id: 'SYNTHETIC-PARENT-OBSERVATION'};
  const current = create(activeData); current.byId('active-now').click();
  assert.deepEqual({caption: current.byId('active-now').textContent, parent: row(current, 'TASK').className.includes('active-parent'),
    leaf: row(current, 'TASK').className.includes('active-leaf'), activity: row(current, 'TASK').dataset.nativeActivity,
    source: row(current, 'TASK').dataset.sourceActivity},
  {caption: 'Подтверждённая активность (1)', parent: true, leaf: false, activity: 'CURRENT', source: 'UNKNOWN'});
  assert.match(current.byId('actor-OWNER').textContent, /Активность: TASK/);
  current.clock.now = Date.parse('2026-01-01T10:30:00Z'); current.timers.forEach(f => f());
  assert.equal(row(current, 'TASK'), undefined); current.byId('active-now').click();
  assert.equal(row(current, 'TASK').dataset.nativeActivity, 'EXPIRED');
  assert.equal(descendants(row(current, 'TASK')).find(e => e.className === 'badge-label').textContent, 'В работе');
});

check('time shows only an explicit recorded value or start, with no inferred elapsed duration', () => {
  const data = clone(fixture.matrix), event = data.events.find(e => e.id === 'E-TIE');
  event.reported_duration_minutes = 125; event.duration_evidence = {source: 'chatgpt_ui', actor_id: 'A', step_id: 'LEAF', observed_at: '2026-01-01T09:59:30Z', ref: 'evidence/visible-time.json'};
  let h = create(fixture.withMatrix(data)); h.byId('expand').click();
  const time = () => descendants(row(h, 'LEAF')).find(e => e.dataset.durationStep === 'LEAF');
  assert.equal(time().textContent, '2h 5m'); assert.match(time().title, /записанная источником/);
  event.duration_evidence.observed_at = '2026-01-01T11:00:00Z'; h = create(fixture.withMatrix(data)); h.byId('expand').click(); assert.equal(time().textContent, '—');
  delete event.reported_duration_minutes; delete event.duration_evidence;
  event.observed_started_at = '2026-01-01T09:50:00Z'; event.observed_start_evidence = [{ref: 'evidence/start.json'}];
  h = create(fixture.withMatrix(data)); h.byId('expand').click(); assert.match(time().textContent, /^с /); assert.match(time().title, /длительность не вычисляется/);
  h = create(); h.byId('expand').click(); assert.equal(time().textContent, '—');
});

check('reload is opt-in, pauses for editing, and restores only project-scoped view state', () => {
  const storage = new Map(), h = create(fixture.snapshot, {storage, hash: '#roadmap'});
  h.timers.forEach(f => f()); assert.equal(h.context.reloads, 0);
  h.byId('expand').click(); detailButton(h, 'LEAF').click();
  const panel = h.elements.detail; panel.scrollTop = 87;
  h.context.window.scrollY = 250; const auto = h.byId('auto-refresh'); auto.checked = true; auto.dispatch('change');
  h.byId('matrix-search').focus(); h.timers.forEach(f => f()); assert.equal(h.context.reloads, 0);
  h.byId('refresh').click(); assert.equal(h.context.reloads, 1);
  const restored = create(fixture.snapshot, {storage, hash: '#roadmap'});
  assert.equal(restored.byId('auto-refresh').checked, true); assert.ok(row(restored, 'LEAF'));
  assert.ok(restored.all().some(e => e.dataset.detailFor === 'LEAF'));
  assert.equal(restored.all().find(e => e.dataset.ownerPanel === 'LEAF').scrollTop, 87); assert.equal(restored.context.window.scrollY, 250);
  const other = clone(fixture.snapshot); other.atlas.project.id = 'OTHER';
  const isolated = create(other, {storage, hash: '#roadmap'}); assert.equal(isolated.byId('auto-refresh').checked, false);
  assert.equal(isolated.all().some(e => e.dataset.detailFor === 'LEAF'), false);
  restored.byId('filter').value = 'active'; restored.byId('filter').dispatch('change');
  restored.byId('matrix-search').value = 'Saved filter with no matches'; restored.byId('matrix-search').dispatch('input');
  restored.byId('refresh').click();
  const same = create(fixture.snapshot, {storage, hash: '#roadmap'});
  assert.equal(same.byId('filter').value, 'active'); assert.equal(same.byId('matrix-search').value, 'Saved filter with no matches');
  const next = clone(fixture.snapshot); next.input.release.id = 'SYNTHETIC.2'; next.input_sha256 = 'b'.repeat(64);
  const advanced = create(next, {storage, hash: '#roadmap'});
  assert.equal(advanced.byId('filter').value, 'all'); assert.equal(advanced.byId('matrix-search').value, '');
  assert.ok(row(advanced, 'LEAF')); assert.equal(advanced.byId('auto-refresh').checked, true);
  assert.match(advanced.byId('refresh-status').textContent, /Новый снимок/);
});

check('history links resolve from the stable entry and immutable release without guessing a download location', () => {
  const data = clone(fixture.snapshot);
  data.atlas.projection_archive = {previous_release: 'SYNTHETIC.0', previous_manifest_sha256: 'a'.repeat(64)};
  for (const [pathname, expected] of [
    ['/project/.atlas/output/index.html', 'releases/SYNTHETIC.0/index.html#history'],
    ['/project/.atlas/output/releases/SYNTHETIC.1/index.html', '../SYNTHETIC.0/index.html#history'],
    ['/downloads/Atlas_Project.html', null]
  ]) {
    const h = create(data, {pathname}); h.button('tab', 'history').click();
    const link = h.all().find(e => e.textContent === 'Previous immutable release · SYNTHETIC.0');
    assert.ok(link);
    if (expected === null) { assert.equal(link.tagName, 'span'); assert.equal(link.href, undefined); }
    else { assert.equal(link.tagName, 'a'); assert.equal(link.href, expected); }
  }
});

assert.equal(results.at(-1).checks, 9); assert.equal(results.at(-1).retained_atlas_regressions, 47);
console.log(JSON.stringify({status: 'PASS', owner_visual_groups: checks, retained_readable_groups: 9, retained_atlas_regressions: 47,
  level: 'PURE_LOGIC_AND_MINIMAL_DOM_NOT_VISUAL', network: false, product_data_changed: false, browser_visual_acceptance: 'SEPARATE_RECEIPT_REQUIRED'}));
