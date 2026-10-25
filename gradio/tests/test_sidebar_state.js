// Execute production hydration, value watcher and sidebar handlers without a browser.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(path.join(__dirname, '../ui/assets/editor.js'), 'utf8');
const extract = (start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));
const hydration = extract('const hydrateLocalState =', 'const fitCanvas =');
const watcher = extract("watch('value', () =>", 'const resizeObserver =');
const sidebar = source.slice(source.indexOf('// Sidebar collapse and expand management'));

function surface() {
  const classes = new Set();
  const listeners = {click: new Set(), keydown: new Set()};
  const memory = new Map();
  const workspace = {classList: {
    contains: name => classes.has(name),
    add: name => classes.add(name),
    remove: name => classes.delete(name),
    toggle: (name, enabled) => enabled ? classes.add(name) : classes.delete(name),
  }};
  return {
    workspace, listeners, memory, storageBlocked: false, workspaceMissing: false,
    window: {dispatchEvent() {}},
    emit(type, target, key = '[', options = {}) {
      const event = {target, key, ...options, prevented: false, preventDefault() { this.prevented = true; }};
      for (const handler of [...listeners[type]]) handler(event);
      return event;
    },
  };
}
function mount(ui, step = 4) {
  const noop = () => {};
  const context = {
    props: {value: {step, image: 'test.jpg', width: 200, height: 200, boxes: {}}},
    window: ui.window, Event: class {constructor(type) {this.type = type;}},
    document: {
      getElementById: id => id === 'workspace' && !ui.workspaceMissing ? ui.workspace : null,
      addEventListener: (type, handler) => ui.listeners[type].add(handler),
      removeEventListener: (type, handler) => ui.listeners[type].delete(handler),
    },
    sessionStorage: {
      getItem(key) {if (ui.storageBlocked) throw Error('Storage blocked'); return ui.memory.get(key) || null;},
      setItem(key, value) {if (ui.storageBlocked) throw Error('Storage blocked'); ui.memory.set(key, value);},
    },
    watchers: {}, watch(name, callback) {context.watchers[name] = callback;},
    requestAnimationFrame: callback => callback(), applyZoom: noop,
    element: {querySelectorAll: () => [], setAttribute: noop},
    root: {querySelector: () => null},
    localContext: '', localBoxes: {}, localTextSequence: [], localTokenOrder: [],
    selectedIds: new Set(), activeBoxId: null, activeTokenId: null,
    image: 'test.jpg', imageTransform: {}, orderDrag: null, moving: null,
    pending: false, pendingAction: null, pendingSortSelectedRange: null,
    mismatchConfirmationInvalidated: false, boxNumbersVisible: true, isDirty: false,
    cloneBoxes: boxes => JSON.parse(JSON.stringify(boxes)),
    updateCanvasLabels: noop, arrangeOrder: noop, updateExcludedChips: noop,
    initializeAlignmentStateFromDOM: noop, renderLocalStatus: noop,
    renderSelection: noop, assertUniqueBoxIds: noop, readAnnotationColor: noop,
    applyAnnotationColor: noop, applyImageOnlyMode: noop, applyBoxNumbersMode: noop,
    cleanupOrderDrag: noop, hideSortingOverlay: noop,
  };
  vm.createContext(context);
  vm.runInContext(hydration + watcher + sidebar, context);
  vm.runInContext('hydrateLocalState()', context);
  return {
    context,
    transition(next) {
      context.props.value = {...context.props.value, step: next};
      context.watchers.value();
    },
  };
}
const button = selector => ({tagName: 'BUTTON', closest: query => query === selector});
const keyTarget = (tagName = 'DIV', extra = {}) => ({tagName, ...extra});
const collapsed = ui => ui.workspace.classList.contains('sidebar-collapsed');
const collapse = ui => ui.emit('click', button('#sidebar-collapse-btn'));
const expand = ui => ui.emit('click', button('.sidebar-expand-tab'));

// The reported regression: Back updates props through watch, without remounting.
{
  const ui = surface(), editor = mount(ui);
  collapse(ui);
  assert.equal(collapsed(ui), true);
  editor.transition(3);
  assert.equal(collapsed(ui), false, 'Step 4 -> 3 must restore Inspector');
  assert.equal(ui.memory.get('sidebar_collapsed_step4'), '1');
  editor.transition(4);
  assert.equal(collapsed(ui), true, 'Returning to Step 4 restores its preference');
  expand(ui);
  assert.equal(collapsed(ui), false);
  assert.equal(ui.memory.get('sidebar_collapsed_step4'), '0');
  editor.transition(3); editor.transition(4);
  assert.equal(collapsed(ui), false, 'Expanded preference survives navigation');
}
// Every other workflow step stays expanded, even if the old class is present.
for (const step of [1, 2, 3, 5, 6, 7]) {
  const ui = surface(), editor = mount(ui);
  collapse(ui);
  editor.transition(step);
  assert.equal(collapsed(ui), false, `Inspector must be available in Step ${step}`);
  collapse(ui);
  assert.equal(collapsed(ui), false, 'Collapse controls cannot affect other steps');
}
// Recreating the editor must replace handlers that captured the previous props.
{
  const ui = surface(), oldEditor = mount(ui);
  collapse(ui);
  const currentEditor = mount(ui, 3);
  assert.equal(ui.listeners.click.size, 1);
  assert.equal(ui.listeners.keydown.size, 1);
  collapse(ui);
  assert.equal(collapsed(ui), false, 'Old Step 4 handler must not hide Step 3');
  currentEditor.transition(4);
  expand(ui);
  oldEditor.context.props.value.step = 3;
  collapse(ui);
  assert.equal(collapsed(ui), true, 'Controls use the current editor after remount');
}
// Storage denial must not prevent leaving Step 4 or manually opening Inspector.
{
  const ui = surface(), editor = mount(ui);
  collapse(ui);
  ui.storageBlocked = true;
  editor.transition(3);
  assert.equal(collapsed(ui), false);
  editor.transition(4);
  collapse(ui); expand(ui);
  assert.equal(collapsed(ui), false);
}
// The shortcut acts only in Step 4, outside editable controls and IME composition.
{
  const ui = surface(), editor = mount(ui);
  assert.equal(ui.emit('keydown', keyTarget()).prevented, true);
  assert.equal(collapsed(ui), true);
  for (const target of [keyTarget('INPUT'), keyTarget('TEXTAREA'), keyTarget('SELECT'), keyTarget('DIV', {isContentEditable: true})]) {
    assert.equal(ui.emit('keydown', target).prevented, false);
    assert.equal(collapsed(ui), true);
  }
  for (const options of [{ctrlKey: true}, {altKey: true}, {metaKey: true}, {isComposing: true}]) {
    assert.equal(ui.emit('keydown', keyTarget(), '[', options).prevented, false);
    assert.equal(collapsed(ui), true);
  }
  editor.transition(3);
  assert.equal(ui.emit('keydown', keyTarget()).prevented, false);
  assert.equal(collapsed(ui), false);
}
// Missing workspace during mount/navigation is harmless.
{
  const ui = surface();
  ui.workspaceMissing = true;
  const editor = mount(ui);
  collapse(ui);
  editor.transition(3);
}
console.log('PASS: sidebar navigation, Step 4 preference, remounts, blocked storage, keyboard and missing workspace');
