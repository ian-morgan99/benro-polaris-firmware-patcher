/* Deterministic tests for the shutter dispatch and completion contract (#309).
 *
 * Run directly:  node tests/test_astro_shutter.js
 * Run via pytest: tests/test_astro_shutter_node.py (invokes this file)
 *
 * These assert against the real module, not a copy of its logic. The point of
 * extracting shutter.js was to make this possible: before it, the payload string
 * lived inside a pointer-event handler in app.js and nothing could assert on it
 * without a browser.
 */
'use strict';

const assert = require('assert');
const path = require('path');

const S = require(path.join(__dirname, '..', 'container', 'astro', 'webui', 'shutter.js'));

let passed = 0;
const failures = [];

function test(name, fn) {
  try {
    fn();
    passed++;
  } catch (e) {
    failures.push({ name: name, message: e && e.message ? e.message : String(e) });
  }
}

/* ── acceptance: M-mode single capture, exact payload ─────────────────────── */

test('M mode sends state:1;bulb:0;c:-1; and nothing else', function () {
  const d = S.decideDispatch(null);
  assert.strictEqual(d.mode, 'M');
  assert.strictEqual(d.payload, 'state:1;bulb:0;c:-1;');
});

test('M mode is chosen for an explicit zero duration', function () {
  // 0 means "the camera's own shutter setting", matching the markup's label.
  const d = S.decideDispatch(0);
  assert.strictEqual(d.mode, 'M');
  assert.strictEqual(d.payload, 'state:1;bulb:0;c:-1;');
});

test('the ordinary trigger never uses c:0', function () {
  // c:0 is Benro Connect's continuation-shooting stop branch. In the device's
  // own Mlog it appears 5 times against 27 for c:-1 -- it is not the normal
  // trigger, and using it here changes which code path the head takes.
  for (const v of [null, 0, '', undefined, 30]) {
    const d = S.decideDispatch(v);
    if (d.payload) {
      assert.ok(/;c:-1;$/.test(d.payload),
        'payload must end c:-1, got ' + d.payload);
      assert.ok(!/;c:0;/.test(d.payload),
        'c:0 must never appear on a single capture, got ' + d.payload);
    }
  }
});

/* ── acceptance: timed B capture carries the selected duration ────────────── */

test('timed B puts the duration in bulb and keeps c:-1', function () {
  const d = S.decideDispatch(40);
  assert.strictEqual(d.mode, 'B');
  assert.strictEqual(d.bulbSeconds, 40);
  // Matches captured app traffic verbatim: state:1;bulb:40;c:-1;
  assert.strictEqual(d.payload, 'state:1;bulb:40;c:-1;');
});

test('B durations of 2 and 5 match the other observed app requests', function () {
  assert.strictEqual(S.decideDispatch(2).payload, 'state:1;bulb:2;c:-1;');
  assert.strictEqual(S.decideDispatch(5).payload, 'state:1;bulb:5;c:-1;');
});

test('startPayload rejects a fractional duration rather than flooring it', function () {
  // The markup allows step 0.5. Flooring 2.5 to 2 would run an exposure shorter
  // than the user asked for, with nothing on screen to say so.
  assert.throws(function () { S.startPayload(2.5); }, RangeError);
  const d = S.decideDispatch(2.5);
  assert.strictEqual(d.mode, 'refused');
  assert.strictEqual(d.payload, null);
});

test('garbage is refused, never silently downgraded to an ordinary shot', function () {
  for (const bad of ['abc', -5, 0.5, Infinity, NaN]) {
    const d = S.decideDispatch(bad);
    assert.strictEqual(d.mode, 'refused',
      'expected refusal for ' + String(bad) + ', got ' + d.mode);
    assert.strictEqual(d.payload, null);
  }
});

/* ── acceptance: B cancelled during exposure ──────────────────────────────── */

test('the stop command is state:0;bulb:0;c:-1;', function () {
  // bulb is cleared on the way out even though the start carried a duration,
  // matching the decompiled stop path.
  assert.strictEqual(S.stopPayload(), 'state:0;bulb:0;c:-1;');
});

test('a cancelled B reports the terminal outcome, not success', function () {
  const pending = { sentAt: 1000, countBefore: 7, mode: 'B', bulbSeconds: 30,
                    sawStarted: true, sawWriting: false };
  // The head answers the stop with state:0 after the exposure was underway.
  const r = S.reconcile(pending, { args: 'state:0;', count: 9 }, 2000);
  assert.strictEqual(r.terminal, true);
  assert.ok(r.phase === 'complete' || r.phase === 'published',
    'a stop after a started exposure must land on a terminal phase, got ' + r.phase);
  // It must NOT be painted as an ordinary "shot" without qualification when the
  // user cancelled: the frame may or may not exist. The caller distinguishes by
  // mode, and the phase is never 'queued'.
  assert.notStrictEqual(r.phase, 'queued');
});

test('a bare state:0 is still a completion, not "unknown"', function () {
  /* /api/link caches one entry per opcode, so a fast capture is observed only at
   * its final value -- the intermediate states overwrite each other between polls.
   * Requiring a sighting of state:1/4 first would report ordinary successful
   * captures as "no confirmation", which is a false failure and worse than the
   * false success this module exists to remove. */
  const pending = { sentAt: 1000, countBefore: 7, mode: 'M', sawStarted: false,
                    sawWriting: false };
  const r = S.reconcile(pending, { args: 'state:0;', count: 9 }, 2000);
  assert.strictEqual(r.phase, 'complete');
  assert.strictEqual(r.terminal, true);
});

/* ── the queued/shot distinction #279 was about ───────────────────────────── */

test('a queued press is never reported as a shot', function () {
  const pending = { sentAt: 1000, countBefore: 7, mode: 'M', sawStarted: false };
  // No reply yet at all -- this is the state right after /api/link/send returns
  // ok:true. Before the #279 fix this painted 'shot'.
  const r = S.reconcile(pending, undefined, 1100);
  assert.notStrictEqual(r.phase, 'complete');
  assert.notStrictEqual(r.phase, 'published');
  assert.strictEqual(r.terminal, false);
});

test('a stale cached reply cannot brand a new shot', function () {
  const pending = { sentAt: 5000, countBefore: 12, mode: 'M', sawStarted: false };
  // count not greater than countBefore means this answer predates the press.
  const r = S.reconcile(pending, { args: 'state:0;', count: 12 }, 5100);
  assert.notStrictEqual(r.phase, 'complete');
});

test('a camera refusal is terminal and names the state', function () {
  const pending = { sentAt: 1000, countBefore: 3, mode: 'M', sawStarted: false };
  const r = S.reconcile(pending, { args: 'state:-110;', count: 4 }, 2000);
  assert.strictEqual(r.phase, 'failed');
  assert.strictEqual(r.terminal, true);
  assert.strictEqual(r.state, -110);   // the #279 PHOTO_RECORD Fail
});

test('the lifecycle walks started then writing before completing', function () {
  const p = { sentAt: 1000, countBefore: 0, mode: 'B', bulbSeconds: 30 };
  const a = S.reconcile(p, { args: 'state:1;', count: 1 }, 1500);
  assert.strictEqual(a.phase, 'started');
  assert.strictEqual(a.terminal, false);

  const p2 = Object.assign({}, p, { sawStarted: true, sawWriting: false });
  const b = S.reconcile(p2, { args: 'state:4;', count: 2 }, 30000);
  assert.strictEqual(b.phase, 'writing');
  assert.strictEqual(b.sawWriting, true);

  const p3 = Object.assign({}, p, { sawStarted: true, sawWriting: true });
  const c = S.reconcile(p3, { args: 'state:0;', count: 3 }, 40000);
  assert.strictEqual(c.phase, 'published');
  assert.strictEqual(c.terminal, true);
});

test('silence past the deadline is unknown, never failed', function () {
  const pending = { sentAt: 0, countBefore: 0, mode: 'B', bulbSeconds: 60 };
  const r = S.reconcile(pending, undefined, S.SHOT_TIMEOUT_MS + 1);
  assert.strictEqual(r.phase, 'unknown');
  assert.strictEqual(r.terminal, true);
  // A long exposure legitimately runs for tens of seconds; the frame may exist.
  assert.notStrictEqual(r.phase, 'failed');
});

/* ── the subsystem field is the server's, not the page's ──────────────────── */

test('shutter.js exposes no subtype setter: OPCODES[] owns the wire selector', function () {
  // 264 is registered { 264, "photo", 2, 1, ... } in polaris-httpd.c and
  // /api/link/send calls plink_send(cmd, pol->sub, args). A client-side override
  // would be a second source of truth for a field the head silently ignores when
  // wrong. If someone adds one, this test should fail and force the question.
  assert.strictEqual(S.setSubtype, undefined);
  assert.strictEqual(S.subtype, undefined);
  const keys = Object.keys(S).filter(function (k) { return /sub/i.test(k); });
  assert.deepStrictEqual(keys, [], 'unexpected subsystem surface: ' + keys.join(','));
});

/* ── every phase the UI must be able to show is defined ───────────────────── */

test('all required UI phases exist and are distinct strings', function () {
  const required = ['queued', 'started', 'writing', 'published', 'complete',
                    'failed', 'unknown'];
  for (const p of required) {
    assert.strictEqual(typeof S.SHOT_PHASES[p], 'string', 'missing phase ' + p);
    assert.ok(S.SHOT_PHASES[p].length > 0, 'empty label for ' + p);
  }
});

/* ── report ───────────────────────────────────────────────────────────────── */

if (failures.length) {
  console.error('FAIL ' + failures.length + ' of ' +
                (failures.length + passed));
  for (const f of failures) {
    console.error('  ✗ ' + f.name + '\n    ' + f.message);
  }
  process.exit(1);
}
console.log('ok ' + passed + ' shutter dispatch tests');
