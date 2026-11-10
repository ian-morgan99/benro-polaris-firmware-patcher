/* Shutter reporting tests (issue #279).

   The bug: fire() painted "shot" as soon as the POST to /api/link/send resolved.
   That POST only queues the command. The head answers asynchronously on opcode 264,
   and in #279 it answered `state:-110` with PHOTO_RECORD Fail -- no file was written,
   yet the screen said "shot". This is the same false-success class as the exposure
   writes in #276.

   These tests drive the REAL reconcileShot() out of container/astro/webui/app.js
   against payloads copied verbatim from the device and from the issue log, so a
   regression that reverts to optimistic reporting fails here rather than on hardware.

   Run: container/test_webui_shutter_reporting.sh  (or node container/test_webui_shutter_reporting.js)
*/

'use strict';

const fs = require('fs');
const path = require('path');

const APP = path.join(__dirname, 'astro', 'webui', 'app.js');
const SHUTTER = path.join(__dirname, 'astro', 'webui', 'shutter.js');
const src = fs.readFileSync(APP, 'utf8');
/* #309 moved the phase decision into shutter.js so it could be asserted without
   a browser. This file still tests what app.js PAINTS for each phase, which is a
   different question and worth keeping, so the module is loaded in as a dependency
   rather than the assertions being dropped. */
const shutterSrc = fs.readFileSync(SHUTTER, 'utf8');

/* Pull the shutter-reporting block out of the real file. Anchoring on the function
   declarations means this fails loudly if they are renamed or removed, instead of
   silently testing nothing. */
function slice(from, to) {
  const a = src.indexOf(from);
  const b = src.indexOf(to, a);
  if (a < 0) throw new Error('missing anchor: ' + from);
  if (b < 0) throw new Error('missing anchor after ' + from);
  return src.slice(a, b);
}

const block = slice('var SHOT_PROGRESS', 'function wireShutter');
if (!/function reconcileShot/.test(block)) throw new Error('reconcileShot not in extracted block');
/* shotStateOf now lives in shutter.js, not app.js. Assert it is reachable from
   the module instead of asserting a location that #309 deliberately changed --
   silently deleting the check would have hidden a real regression. */
if (!/function shotStateOf/.test(shutterSrc)) {
  throw new Error('shotStateOf missing from shutter.js');
}
if (!/SHUTTER\.reconcile\(/.test(block)) {
  throw new Error('reconcileShot no longer delegates to SHUTTER.reconcile, so the '
    + 'tested painting may not be the code that ships');
}

/* ── harness ─────────────────────────────────────────────────────────────── */

let painted = null, hint = null, reverted = false;

const btnStub = {
  classList: {
    add() {}, remove() {}, contains() { return false; }
  }
};

function $(sel, ctx) {
  if (sel === '.label') return { set textContent(v) { painted = v; }, get textContent() { return painted; } };
  return btnStub;
}

function setHint(html) { hint = html || ''; }

/* Paint is synchronous here; only the revert timer is deferred, so capture it
   rather than actually waiting on it. */
function setTimeout(fn, ms) { if (ms > 0) reverted = true; return 0; }

const S = { ops: {}, shotPending: null };

const sandbox = { $, setHint, setTimeout, S, SHOT_TIMEOUT_MS_OVERRIDE: null };
/* shutter.js first so SHUTTER exists when reconcileShot runs. Its module.exports
   tail is inert here because `module` is undefined in this sandbox, exactly as it
   is in the browser. */
const factory = new Function('$', 'setHint', 'setTimeout', 'S',
  shutterSrc + '\n' + block +
  '\nreturn { reconcileShot, paintShot, SHOT_TIMEOUT_MS, SHOT_PROGRESS, SHUTTER };');
const api = factory($, setHint, setTimeout, S);
/* shotStateOf is now reached through the module. */
api.shotStateOf = api.SHUTTER.shotStateOf;

/* ── assertions ──────────────────────────────────────────────────────────── */

let pass = 0, fail = 0;
function check(name, got, want) {
  if (got === want) { pass++; console.log('  ok   ' + name); }
  else { fail++; console.log('  FAIL ' + name + '\n         got:  ' + JSON.stringify(got) +
                             '\n         want: ' + JSON.stringify(want)); }
}

function press(countBefore) {
  painted = null; hint = null; reverted = false;
  S.shotPending = { sentAt: Date.now(), countBefore: countBefore, state: null };
}

console.log('shotStateOf parses the head\'s lifecycle field');
check('initiation', api.shotStateOf('state:1;bulb:0;c:0;path:/app/sd/normal/SP_0567.jpg;c:0'), 1);
check('refused (#279)', api.shotStateOf('state:-110;/app/sd/normal/SP_0567.jpg'), -110);
check('refused (live probe)', api.shotStateOf('state:-1002;'), -1002);
check('complete', api.shotStateOf('state:0;'), 0);
check('absent', api.shotStateOf('ret:0;'), null);

console.log('\nthe #279 failure is reported as a failure, not "shot"');
S.ops = { '264': { args: 'state:-110;/app/sd/normal/SP_0567.jpg', count: 6, age_ms: 100 } };
press(5);
api.reconcileShot();
check('label is not "shot"', painted !== 'shot', true);
check('label names the code', /-110/.test(painted || ''), true);
check('hint explains it', /refused the shot/.test(hint), true);
check('pending cleared', S.shotPending, null);

console.log('\nthe live probe reply (state:-1002) is also reported as a failure');
S.ops = { '264': { args: 'state:-1002;', count: 9, age_ms: 100 } };
press(8);
api.reconcileShot();
check('label is not "shot"', painted !== 'shot', true);
check('label names the code', /-1002/.test(painted || ''), true);

console.log('\na successful capture still reports success');
S.ops = { '264': { args: 'state:0;', count: 3, age_ms: 50 } };
press(2);
api.reconcileShot();
check('label is "shot"', painted, 'shot');
check('hint cleared', hint, '');
check('pending cleared', S.shotPending, null);

console.log('\nmid-lifecycle states keep waiting instead of claiming success');
S.ops = { '264': { args: 'state:1;bulb:0;c:0;', count: 3, age_ms: 50 } };
press(2);
api.reconcileShot();
check('label shows progress', painted, 'exposing…');
check('still pending', S.shotPending !== null, true);

S.ops = { '264': { args: 'state:4;', count: 4, age_ms: 50 } };
press(3);
api.reconcileShot();
check('writing card shown', painted, 'writing card…');
check('still pending after state:4', S.shotPending !== null, true);

console.log('\na stale cached reply cannot brand a new press');
/* count has not advanced since the press, so this answer predates it. */
S.ops = { '264': { args: 'state:-110;/app/sd/normal/SP_0567.jpg', count: 5, age_ms: 9e5 } };
press(5);
api.reconcileShot();
check('not painted failed from stale reply', /-110/.test(painted || ''), false);
check('still pending', S.shotPending !== null, true);

console.log('\nsilence reports "no confirmation", never a failure verdict');
S.ops = { '264': { args: 'state:1;', count: 5, age_ms: 9e5 } };
press(5);
/* sentAt must be in the PAST for the deadline to have elapsed. */
S.shotPending.sentAt = Date.now() - (api.SHOT_TIMEOUT_MS + 1000);
api.reconcileShot();
check('label is no-confirmation', /no confirmation/i.test(painted || ''), true);
check('hint says check the gallery', /Gallery/.test(hint), true);
check('pending cleared on timeout', S.shotPending, null);

console.log('\nthe optimistic-report regression is still caught');
/* Structural, not a regex over one historical spelling. An earlier guard here
   matched only the original `textContent = r && r.ok === false ? ... : 'shot'`
   line and passed green while a mutated fire() painted 'shot' directly -- a guard
   that cannot see the bug is worse than no guard, because it reads as coverage.
   So: extract fire()'s body and assert it never paints the success label and always
   arms shotPending, and that reconcileShot is the only thing that declares success. */
const fireBody = (src.match(/function fire\(\) \{[\s\S]*?\n  \}/) || [''])[0];
if (!fireBody) {
  console.log('  FAIL could not locate fire() to check it');
  fail++;
} else {
  if (/['"]shot['"]/.test(fireBody)) {
    console.log('  FAIL fire() paints "shot" itself -- the POST only queues the command, '
                + 'so a refused capture would still look like success');
    fail++;
  } else {
    console.log('  ok   fire() does not paint the success label');
    pass++;
  }
  if (/S\.shotPending *= *\{/.test(fireBody)) {
    console.log('  ok   fire() arms shotPending so the head\'s reply is awaited');
    pass++;
  } else {
    console.log('  FAIL fire() does not arm shotPending; nothing awaits the lifecycle reply');
    fail++;
  }
  const recBody = (src.match(/function reconcileShot\(\) \{[\s\S]*?\n\}/) || [''])[0];
  /* #309 moved the label text into shutter.js's SHOT_PHASES, so grepping app.js
     for a literal paintShot('shot') no longer describes how the label is produced.
     Assert the two facts that actually matter instead: the module still maps
     completion to 'shot', and reconcileShot paints from that table rather than
     hardcoding a success string of its own. The behavioural assertion above (a
     state:0 reply must paint 'shot') is what proves it end to end. */
  if (/complete:\s*'shot'/.test(shutterSrc) &&
      /SHUTTER\.SHOT_PHASES\[r\.phase\]/.test(recBody)) {
    console.log('  ok   reconcileShot owns the success label, keyed on state:0');
    pass++;
  } else {
    console.log('  FAIL reconcileShot no longer paints the success label');
    fail++;
  }
}

/* iOS hold hardening. These are wiring facts a unit test cannot observe without a
   DOM, so they are asserted against the source. Reverting any of them makes a
   deliberate hold silently do nothing on iPhone/iPad, which is undetectable from
   a browserless test run and only shows up as "the shutter does not work". */
console.log('\niOS hold-to-fire hardening is present');
const CSS = fs.readFileSync(path.join(__dirname, 'astro', 'webui', 'app.css'), 'utf8');
const shutterRule = (CSS.match(/\.shutter \{[\s\S]*?\n\}/) || [''])[0];

if (/addEventListener\('pointerleave', *leave\)/.test(src)) {
  console.log('  ok   pointerleave routes to leave(), not cancel()');
  pass++;
} else if (/\['pointerup', *'pointercancel', *'pointerleave'\]/.test(src)) {
  console.log('  FAIL pointerleave is back in the unconditional cancel list');
  fail++;
} else {
  console.log('  FAIL pointerleave wiring not found');
  fail++;
}

if (/captured *= *true/.test(src) && /function leave\(\) \{ if \(!captured\)/.test(src)) {
  console.log('  ok   capture success is tracked and consulted by leave()');
  pass++;
} else {
  console.log('  FAIL leave() does not consult whether pointer capture took effect');
  fail++;
}

if (/-webkit-touch-callout: *none/.test(shutterRule)) {
  console.log('  ok   .shutter suppresses the iOS long-press callout');
  pass++;
} else {
  console.log('  FAIL .shutter does not suppress -webkit-touch-callout; a long press '
              + 'raises the callout, fires pointercancel, and aborts the hold');
  fail++;
}

if (/user-select: *none/.test(shutterRule) && /-webkit-user-select: *none/.test(shutterRule)) {
  console.log('  ok   .shutter suppresses text selection during a hold');
  pass++;
} else {
  console.log('  FAIL .shutter does not suppress user-select');
  fail++;
}

console.log('\n' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
