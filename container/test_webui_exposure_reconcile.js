/* Offline behavioural test for the webui's exposure write reconciliation.
 *
 * Runs container/astro/webui/app.js inside a minimal DOM stub and drives it with
 * the exact reply shapes the head produces, including the ones that used to be
 * silently swallowed:
 *
 *   'iso:1;ret:-2110;'  camera was not idle -> write DROPPED after ok:true
 *   'iso:1;ret:0;'      accepted
 *   'RD:0;V:1;R:...'    the option list proving the settled value
 *
 * Measured on a K-1 II: 62% of exposure writes come back -2110 and settle takes
 * ~12 s, so the page must show "applying", retry a rejection, and admit defeat.
 * On a K-3 III it settles fast and this test's happy path is what the user sees.
 *
 * No network, no rig: /api/link replies are injected directly into S.ops.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const APP = path.resolve(__dirname, '../container/astro/webui/app.js');
const src = fs.readFileSync(APP, 'utf8');

/* ───────────────────────────── DOM stub ───────────────────────────── */

let failures = 0;
function check(name, cond, detail) {
  if (cond) { console.log('  ok   ' + name); }
  else { failures++; console.log('  FAIL ' + name + (detail ? '  <- ' + detail : '')); }
}

function makeEl(tag, attrs) {
  const el = {
    tagName: tag.toUpperCase(),
    dataset: Object.assign({}, attrs || {}),
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); },
      remove(c) { this._s.delete(c); },
      toggle(c, on) { if (on === undefined) { this._s.has(c) ? this._s.delete(c) : this._s.add(c); } else { on ? this._s.add(c) : this._s.delete(c); } },
      contains(c) { return this._s.has(c); }
    },
    style: {},
    listeners: {},
    children: [],
    /* app.js assigns el.className directly, so className must keep classList in
       sync or assertions on the marker's state are meaningless. */
    get className() { return Array.from(this.classList._s).join(' '); },
    set className(v) {
      this.classList._s = new Set(String(v || '').split(/\s+/).filter(Boolean));
    },
    textContent: '',
    innerHTML: '',
    value: '',
    hidden: false,
    disabled: false,
    checked: false,
    selectedIndex: -1,
    appendChild(c) { this.children.push(c); c.parentNode = this; return c; },
    insertBefore(c) { this.children.unshift(c); c.parentNode = this; return c; },
    removeChild(c) { this.children = this.children.filter(x => x !== c); return c; },
    remove() { if (this.parentNode) this.parentNode.removeChild(this); },
    setAttribute(k, v) { this['_attr_' + k] = String(v); },
    getAttribute(k) { const v = this['_attr_' + k]; return v === undefined ? null : v; },
    hasAttribute(k) { return this['_attr_' + k] !== undefined; },
    removeAttribute(k) { delete this['_attr_' + k]; },
    focus() { documentStub.activeElement = this; },
    blur() { if (documentStub.activeElement === this) documentStub.activeElement = null; },
    click() { this.fire('click'); },
    scrollIntoView() {},
    cloneNode() { return makeEl(this.tagName, this.dataset); },
    getBoundingClientRect() { return { top: 0, left: 0, right: 0, bottom: 0, width: 100, height: 40 }; },
    _children_find(sel) {
      const want = sel.replace(/^\./, '');
      return this.children.filter(c => c.classList.contains(want))[0] || { textContent: '', className: '' };
    },
    addEventListener(ev, fn) { (this.listeners[ev] = this.listeners[ev] || []).push(fn); },
    fire(ev, arg) { (this.listeners[ev] || []).forEach(fn => fn(arg || { target: this })); },
    closest(sel) {
      const want = sel.replace(/^\./, '');
      let n = this;
      while (n) { if (n.classList.contains(want)) return n; n = n.parentNode; }
      return null;
    },
    querySelector(sel) {
      /* Enough matching for this page: '#id', '.class' and bare tag names,
         searched among direct children (how app.js uses $('x', slot)). */
      const want = sel.replace(/^[#.]/, '');
      return this.children.filter(c =>
        c.id === want || c.tagName === want.toUpperCase() || c.classList.contains(want))[0] || null;
    },
    querySelectorAll() { return []; }
  };
  return el;
}

/* The five exposure slots exactly as index.html declares them. */
const SLOTS = [
  { get: '268', set: '261', key: 's', label: 'shutter' },
  { get: '275', set: '276', key: 'fNum', label: 'aperture' },
  { get: '265', set: '258', key: 'iso', label: 'ISO' },
  { get: '267', set: '260', key: 'ev', label: 'EV' },
  { get: '266', set: '259', key: 'wb', label: 'WB' }
];

const slots = SLOTS.map(s => {
  const slot = makeEl('div', s);
  slot.classList.add('exposlot');
  const lbl = makeEl('span'); lbl.classList.add('lbl'); lbl.textContent = s.label;
  const sel = makeEl('select');
  slot.appendChild(lbl); slot.appendChild(sel);
  slot._sel = sel; slot._lbl = lbl;
  return slot;
});

const fmMf = makeEl('button'); fmMf.id = 'fm-mf'; fmMf.classList.add('afmf-btn');
const fmAf = makeEl('button'); fmAf.id = 'fm-af'; fmAf.classList.add('afmf-btn');
const focusSlot = makeEl('div'); focusSlot.classList.add('exposlot');
focusSlot.appendChild(fmMf); focusSlot.appendChild(fmAf);

/* The change handler chains .then(send(get)), so the read-back lands on a
   microtask. Await one tick before asserting on what was sent. */
function tick() { return new Promise(r => setImmediate(r)); }

/* Any '#id' the boot block touches gets a stub element, so wire*() functions
   all have something to attach to without enumerating the whole page here. */
const byId = {};
function find(sel) {
  if (sel === '#fm-mf') return fmMf;
  if (sel === '#fm-af') return fmAf;
  if (sel.charAt(0) === '#') {
    const id = sel.slice(1);
    if (!byId[id]) { byId[id] = makeEl('div'); byId[id].id = id; }
    return byId[id];
  }
  return null;
}

const documentStub = {
  activeElement: null,
  documentElement: makeEl('html'),
  body: makeEl('body'),
  fullscreenElement: null,
  webkitFullscreenElement: null,
  visibilityState: 'visible',
  createElement: t => makeEl(t),
  querySelector: find,
  querySelectorAll: sel => {
    if (sel === '.exposlot[data-get]') return slots.slice();
    return [];
  },
  addEventListener() {},
  exitFullscreen: () => Promise.resolve(),
  webkitExitFullscreen: () => Promise.resolve()
};

/* ───────────────────── capture what the page sends ───────────────────── */

const sent = [];
let linkReplies = {};

function run() {
  const sandbox = {
    console,
    document: documentStub,
    localStorage: { _d: {}, getItem(k) { return this._d[k] || null; }, setItem(k, v) { this._d[k] = String(v); } },
    fetch: (url, opts) => {
      if (String(url).indexOf('/api/link/send') === 0) {
        const body = (opts && opts.body) || '';
        const cmd = /cmd=(\d+)/.exec(body), args = /args=([^&]*)/.exec(body);
        sent.push({ cmd: cmd ? parseInt(cmd[1], 10) : null,
                    args: args ? decodeURIComponent(args[1]) : '' });
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) });
      }
      if (String(url).indexOf('/api/link') === 0) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: 'up', opcodes: linkReplies, gear: 3 })
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    },
    setTimeout: (fn, ms) => { pendingTimers.push({ fn, ms }); return pendingTimers.length; },
    setInterval: () => 0,
    clearInterval: () => {},
    clearTimeout: () => {},
    requestAnimationFrame: fn => { pendingTimers.push({ fn, ms: 16 }); return 1; },
    Date, Math, JSON, Object, Array, String, Number, parseInt, parseFloat, isNaN,
    encodeURIComponent, decodeURIComponent, RegExp, Error, Promise,
    navigator: {
      userAgent: 'test',
      geolocation: { getCurrentPosition(ok, err) { if (err) err({ code: 1 }); } },
      vibrate: () => true
    },
    location: { href: 'http://test/', reload() {} }
  };
  sandbox.window = {
    addEventListener() {}, removeEventListener() {},
    chrome: undefined, DeviceOrientationEvent: undefined,
    localStorage: sandbox.localStorage,
    navigator: sandbox.navigator, location: sandbox.location,
    matchMedia: () => ({ matches: false, addListener() {}, addEventListener() {} }),
    setTimeout: sandbox.setTimeout, setInterval: sandbox.setInterval,
    clearInterval: sandbox.clearInterval, clearTimeout: sandbox.clearTimeout,
    requestAnimationFrame: sandbox.requestAnimationFrame,
    innerWidth: 1024, innerHeight: 768
  };
  sandbox.matchMedia = sandbox.window.matchMedia;
  sandbox.addEventListener = () => {};
  return sandbox;
}

const pendingTimers = [];

/* app.js runs its boot block immediately; every wire*() must survive the stub. */
const ctx = vm.createContext(run());
let loadError = null;
try {
  vm.runInContext(src, ctx, { filename: 'app.js' });
} catch (e) { loadError = e; }

console.log('--- load ---');
check('app.js runs under a DOM stub without throwing', !loadError, loadError && loadError.message);
if (loadError) {
  console.log('\nFATAL: cannot exercise logic');
  console.log(String(loadError.stack).split('\n').slice(0, 8).join('\n'));
  process.exit(1);
}

const S = ctx.S;
const opts = (idx, n) => 'RD:0;V:' + idx + ';R:' + Array.from({ length: n }, (_, i) => 'o' + i).join(',');

/* ───────────────────────── scenarios ───────────────────────── */

function reset() {
  sent.length = 0;
  S.expoPending = {};
  S.focusPending = null;
  linkReplies = {};
}

/* render() is what copies /api/link replies into S.ops, so every scenario drives
   the page through it -- exactly as the 500 ms poll does in the browser. */
function head(opcodes) {
  linkReplies = Object.assign({}, linkReplies, opcodes);
  ctx.render({ status: 'up', opcodes: linkReplies, gear: 3 });
}

async function main() {
console.log('\n--- 1. accepted write settles and the marker clears ---');
reset();
const iso = slots[2];                      /* data-get=265 data-set=258 */
head({ '265': { args: opts(0, 4), count: 1 } });
await tick();
sent.length = 0;                 /* discard the first-load bootstrap fetch */
iso._sel.fire('change', { target: { value: '2' } });
await tick();

check('write sent with the chosen index', sent.some(s => s.cmd === 258 && s.args === 'iso:2;'), JSON.stringify(sent));
check('ONLY that property re-read, not all five',
      sent.filter(s => [265, 266, 267, 268, 275].indexOf(s.cmd) >= 0).map(s => s.cmd).join(',') === '265',
      JSON.stringify(sent));
check('intent tracked as pending', !!S.expoPending['265']);
ctx.paintExposure();
check('shows the user\'s choice, not the stale camera value', iso._sel.value === '2', iso._sel.value);
check('marked applying', /applying/.test(iso._children_find('.ctl-state').textContent), iso._children_find('.ctl-state').textContent);

/* head confirms */
head({ '265': { args: opts(2, 4), count: 2 } });
check('settled -> pending cleared', !S.expoPending['265'], JSON.stringify(S.expoPending));
check('settled -> marker empty', iso._children_find('.ctl-state').textContent === '', iso._children_find('.ctl-state').textContent);

console.log('\n--- 2. -2110 rejection is retried, not reported as success ---');
reset();
head({ '265': { args: opts(0, 4), count: 1 } });
iso._sel.fire('change', { target: { value: '3' } });
await tick();
sent.length = 0;

head({ '258': { args: 'iso:3;ret:-2110;', count: 1 } });   /* DROPPED */
check('rejection triggers a retry send', sent.some(s => s.cmd === 258 && s.args === 'iso:3;'), JSON.stringify(sent));
check('retry counted', S.expoPending['265'] && S.expoPending['265'].tries === 1, JSON.stringify(S.expoPending['265']));

console.log('\n--- 3. repeated rejection gives up and says so ---');
reset();
head({ '265': { args: opts(0, 4), count: 1 } });
iso._sel.fire('change', { target: { value: '3' } });
for (let i = 0; i < 5; i++) {
  head({ '258': { args: 'iso:3;ret:-2110;', count: i + 2 } });
}
check('stops retrying at the cap', S.expoPending['265'] && S.expoPending['265'].tries <= 3, JSON.stringify(S.expoPending['265']));
check('state is terminal "rejected"', S.expoPending['265'] && S.expoPending['265'].state === 'rejected', JSON.stringify(S.expoPending['265']));
ctx.paintExposure();
check('user is told the camera refused', /refused/.test(iso._children_find('.ctl-state').textContent), iso._children_find('.ctl-state').textContent);

console.log('\n--- 4. a reply for a DIFFERENT index must not settle this intent ---');
reset();
head({ '265': { args: opts(0, 4), count: 1 } });
iso._sel.fire('change', { target: { value: '3' } });
await tick();
sent.length = 0;
head({ '258': { args: 'iso:1;ret:-2110;', count: 9 } });   /* an older write */
check('stale rejection does not consume our retry budget',
      S.expoPending['265'] && S.expoPending['265'].tries === 0, JSON.stringify(S.expoPending['265']));

console.log('\n--- 5. deadline passes without confirmation -> admits it ---');
reset();
head({ '265': { args: opts(0, 4), count: 1 } });
iso._sel.fire('change', { target: { value: '3' } });
S.expoPending['265'].sentAt = Date.now() - 99999;
head({});
check('state becomes timeout', S.expoPending['265'] && S.expoPending['265'].state === 'timeout', JSON.stringify(S.expoPending['265']));
ctx.paintExposure();
check('user is told it was not applied', /not applied/.test(iso._children_find('.ctl-state').textContent), iso._children_find('.ctl-state').textContent);

console.log('\n--- 6. focus mode reports the head\'s ret: instead of assuming ---');
reset();
fmMf.fire('click');
await tick();
check('262 sent', sent.some(s => s.cmd === 262), JSON.stringify(sent));
sent.length = 0;
head({ '262': { args: 'mod:1;f:0;ret:-1;', count: 1 } });
check('head rejection surfaced', /refused/.test(focusSlot._children_find('.ctl-state').textContent), focusSlot._children_find('.ctl-state').textContent);
head({ '262': { args: 'mod:1;f:0;ret:0;', count: 2 } });
check('head acceptance clears the marker', !S.focusPending && focusSlot._children_find('.ctl-state').textContent === '',
      JSON.stringify(S.focusPending) + ' / ' + focusSlot._children_find('.ctl-state').textContent);

console.log('\n--- 7. no fixed 400/700 ms cascade left on the change path ---');
const changeSrc = /function wireExposure\(\)[\s\S]*?\n}\n/.exec(src);
check('change handler no longer chains setTimeout(fetchExposure, 400)',
      !!changeSrc && !/setTimeout\(fetchExposure, 400\)/.test(changeSrc[0]), changeSrc && changeSrc[0].slice(0, 200));

}

main().then(function () {
  console.log('\n' + (failures ? 'FAILED: ' + failures : 'ALL PASS'));
  process.exit(failures ? 1 : 0);
}).catch(function (e) {
  console.log('\nHARNESS ERROR: ' + e.stack);
  process.exit(1);
});
