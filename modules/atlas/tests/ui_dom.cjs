'use strict';
// Minimal DOM contract harness. This does not render CSS or establish browser acceptance.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const VIEWER = require.resolve('../skills/atlas/scripts/viewer.js');
const logic = require(VIEWER);
function descendants(element) { return [element, ...element.children.flatMap(descendants)]; }
function createHarness(snapshot, options = {}) {
  const downloads = [], blobs = new Map(), timers = [], clock = {now: options.now === undefined ? Date.now() : options.now};
  let document;
  class Element {
    constructor(tag = 'div') { this.tagName = tag; this.children = []; this.parentElement = null; this.dataset = {}; this.attrs = {}; this.listeners = {}; this._text = ''; this.value = ''; this.className = ''; this.hidden = false; this.disabled = false; this.id = ''; }
    set textContent(value) { this._text = String(value); this.children.forEach(x => { x.parentElement = null; }); this.children = []; }
    get textContent() { return this._text + this.children.map(x => x.textContent).join(' '); }
    append(...values) { values.forEach(value => { if (value.parentElement) value.parentElement.children = value.parentElement.children.filter(x => x !== value); value.parentElement = this; this.children.push(value); }); }
    replaceChildren(...values) { this.children.forEach(x => { x.parentElement = null; }); this._text = ''; this.children = []; this.append(...values); }
    setAttribute(key, value) { this.attrs[key] = String(value); if (key === 'id') this.id = String(value); if (key === 'class') this.className = String(value); }
    addEventListener(kind, callback) { (this.listeners[kind] ??= []).push(callback); }
    matches(selector) { return selector.startsWith('.') ? this.className.split(' ').includes(selector.slice(1)) : selector.startsWith('#') ? this.id === selector.slice(1) : this.tagName === selector; }
    closest(selector) { for (let current = this; current; current = current.parentElement) if (current.matches(selector)) return current; return null; }
    get previousElementSibling() { return this.parentElement ? this.parentElement.children[this.parentElement.children.indexOf(this) - 1] || null : null; }
    click() {
      if (this.disabled) return;
      if (this.tagName === 'a' && this.download) downloads.push({filename: this.download, blob: blobs.get(this.href)});
      this.dispatch('click');
    }
    dispatch(kind) { for (const f of this.listeners[kind] ?? []) f({target: this}); for (const f of document.listeners[kind] ?? []) f({target: this}); }
  }
  const body = new Element('body'), elements = {};
  function add(parent, tag, id, text) { const e = new Element(tag); if (id) { e.id = id; elements[id] = e; } if (text) e.textContent = text; parent.append(e); return e; }
  const header = add(body, 'header'); add(header, 'div', null, 'DOCUMENTS · CONTRACTS · RELATIONSHIPS'); add(header, 'h1', 'title'); add(header, 'p', 'release'); add(header, 'p', 'scope');
  const toolbar = add(body, 'section'); toolbar.className = 'toolbar';
  add(add(toolbar, 'label'), 'input', 'search'); add(add(toolbar, 'label'), 'select', 'lifecycle');
  add(toolbar, 'button', 'reset'); add(toolbar, 'button', 'download'); add(body, 'nav', 'tabs');
  const workspace = add(body, 'div'); workspace.className = 'workspace';
  const aside = add(workspace, 'aside'); add(aside, 'h2', null, 'Modules'); add(aside, 'div', 'modules');
  const main = add(workspace, 'main'); add(main, 'p', 'summary'); add(main, 'div', 'list'); add(workspace, 'section', 'detail');
  add(body, 'script', 'navigator-data').textContent = JSON.stringify(snapshot);
  document = {body, listeners: {}, getElementById: id => descendants(body).find(e => e.id === id) || null, createElement: tag => new Element(tag), addEventListener(kind, f) { (this.listeners[kind] ??= []).push(f); }};
  class Clock extends Date { static now() { return clock.now; } }
  class Blob { constructor(parts, meta) { this.parts = parts; this.type = meta.type; } }
  const URL = {createObjectURL(blob) { const id = `blob:mock-${blobs.size}`; blobs.set(id, blob); return id; }, revokeObjectURL(id) { blobs.delete(id); }};
  const context = {document, console, Date: Clock, Blob, URL, setInterval: f => timers.push(f)};
  vm.runInNewContext(fs.readFileSync(VIEWER, 'utf8'), context, {timeout: 5000});
  return {elements, document, downloads, timers, clock, context,
    all: () => descendants(body),
    button: (key, value) => descendants(body).find(e => e.tagName === 'button' && e.dataset[key] === value),
    byId: id => document.getElementById(id)};
}
function runGeneric(snapshot) {
  let checks = 0;
  function check(test) { test(); checks++; }
  const state = {tab: 'contracts', query: '', module: '', lifecycle: 'current', selection: null};
  check(() => assert.equal(logic.derive(snapshot, state).length, 2));
  state.lifecycle = 'archived'; check(() => assert.equal(logic.derive(snapshot, state)[0].id, 'contract.plan.v1'));
  state.query = 'NO MATCH'; check(() => assert.equal(logic.derive(snapshot, state).length, 0));
  check(() => { logic.reset(state); assert.equal(logic.derive(snapshot, state).length, 2); assert.equal(state.module, ''); });
  check(() => { assert.ok(logic.openEntity(snapshot, state, 'doc.old')); assert.equal(state.tab, 'documents'); assert.equal(state.lifecycle, 'archived'); assert.equal(logic.derive(snapshot, state).length, 1); });
  check(() => assert.equal(logic.openEntity(snapshot, state, 'missing'), false));
  check(() => { state.tab = 'contracts'; state.lifecycle = 'current'; state.query = 'INVALID_PERIOD'; assert.equal(logic.derive(snapshot, state).length, 1); });
  check(() => { state.query = ''; state.module = 'module.journal'; assert.equal(logic.derive(snapshot, state)[0].id, 'contract.journal.v1'); });
  check(() => { state.tab = 'history'; state.lifecycle = 'archived'; assert.equal(logic.derive(snapshot, state).length, snapshot.input.history.length); });
  check(() => { assert.equal(logic.exportIndex(snapshot), snapshot.input); assert.deepEqual(JSON.parse(JSON.stringify(logic.exportIndex(snapshot))), snapshot.input); assert.equal(logic.exportIndex(snapshot).input, undefined); });
  const {elements, button, all, context, downloads} = createHarness(snapshot);
  check(() => assert.match(elements.title.textContent, /Synthetic/));
  check(() => { button('tab', 'contracts').click(); assert.match(elements.summary.textContent, /2 items/); });
  check(() => { elements.search.value = 'NO MATCH'; elements.search.dispatch('input'); assert.match(elements.list.textContent, /Nothing found/); });
  check(() => { elements.reset.click(); assert.match(elements.summary.textContent, /2 items/); });
  check(() => { button('entity', 'contract.plan.v2').click(); assert.match(elements.detail.textContent, /Input.*locality, period/); assert.match(elements.detail.textContent, /Authorization/); assert.match(elements.detail.textContent, /INVALID_PERIOD/); });
  check(() => { button('matrix', 'step:DEMO-STEP-01').click(); assert.match(elements.detail.textContent, /Declare a synthetic contract/); assert.match(elements.detail.textContent, /SYNTHETIC_ONLY/); });
  check(() => { button('entity', 'doc.matrix').click(); assert.match(elements.detail.textContent, /SHA256/); assert.match(elements.detail.textContent, /Readback UTC/); });
  check(() => { button('tab', 'documents').click(); button('entity', 'doc.project').click(); assert.match(elements.detail.textContent, /<script>globalThis.INJECTED=true/); assert.equal(context.INJECTED, undefined); assert.equal(descendants(elements.detail).some(e => e.tagName === 'script' || e.tagName === 'img'), false); });
  check(() => { elements.lifecycle.value = 'archived'; elements.lifecycle.dispatch('change'); assert.match(elements.summary.textContent, /1 items/); button('entity', 'doc.old').click(); assert.match(elements.detail.textContent, /Archive/); });
  check(() => { elements.reset.click(); assert.match(elements.summary.textContent, /4 items/); });
  check(() => { button('tab', 'relations').click(); assert.match(elements.summary.textContent, /3 items/); });
  check(() => { button('tab', 'history').click(); assert.match(elements.list.textContent, /DEMO-HISTORY-01/); assert.match(elements.list.textContent, /DEMO-HISTORY-02/); });
  check(() => { button('tab', 'matrix').click(); assert.match(elements.summary.textContent, /3 items/); assert.match(elements.list.textContent, /Historical event/); });
  check(() => { button('matrix', 'event:DEMO-EVENT-01').click(); assert.match(elements.detail.textContent, /contract.plan.v2/); assert.ok(button('matrix', 'step:DEMO-STEP-01')); });
  check(() => { elements.download.click(); assert.equal(downloads[0].filename, 'DOCS_INDEX.json'); assert.deepEqual(JSON.parse(downloads[0].blob.parts.join('')), snapshot.input); assert.equal(all().filter(e => e.tagName === 'script').length, 1); });
  return {status: 'PASS', checks, level: 'PURE_LOGIC_AND_MINIMAL_DOM_NOT_VISUAL', network: false};
}
module.exports = {logic, createHarness, descendants, runGeneric};
if (require.main === module) console.log(JSON.stringify(runGeneric(JSON.parse(fs.readFileSync(process.argv[2], 'utf8')))));
