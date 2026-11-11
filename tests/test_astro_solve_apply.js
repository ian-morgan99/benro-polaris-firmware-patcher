/* Behavioural tests for the "Apply last solve" contract (#329).
 *
 * Run under node by tests/test_astro_solve_apply_node.py, which is registered in
 * tests/run_prerelease_gate.sh. A test file nothing invokes is the failure mode
 * #292 and #299 both hit, so the wrapper and the gate entry are not optional.
 *
 * These assert on what applyRequest()/applyOutcome() decide, not on whether the
 * strings appear in app.js. A pattern assertion would pass while the handler
 * still posted an empty body.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const REPO = path.resolve(__dirname, '..');
const MOD = path.join(REPO, 'container/astro/webui/solve-apply.js');
const SA = require(MOD);

let passed = 0;
function t(name, fn) {
  try { fn(); passed++; console.log('  ok   ' + name); }
  catch (e) { console.log('  FAIL ' + name + '\n       ' + e.message); process.exitCode = 1; }
}

const SOLVED = {
  solved: true, ra_deg: 83.6331, dec_deg: -5.2942,
  roll_deg: 12.5, pixscale_arcsec: 1.872, nmatch: 41, nfield: 300
};

console.log('#329 apply-last contract');

/* ---- the shipped module is the one under test -------------------------- */
t('module file exists at the path app.js will load', function () {
  assert.ok(fs.existsSync(MOD), 'missing ' + MOD);
});

t('index.html loads solve-apply.js before app.js', function () {
  const html = fs.readFileSync(path.join(REPO, 'container/astro/webui/index.html'), 'utf8');
  const a = html.indexOf('/solve-apply.js');
  const b = html.indexOf('/app.js');
  assert.ok(a >= 0, 'index.html does not reference solve-apply.js');
  assert.ok(b >= 0, 'index.html does not reference app.js');
  assert.ok(a < b, 'solve-apply.js must load before app.js, which calls into it');
});

t('app.js actually calls the module (not decorative)', function () {
  const js = fs.readFileSync(path.join(REPO, 'container/astro/webui/app.js'), 'utf8');
  assert.ok(/SOLVE_APPLY\.(applyRequest|applyOutcome|describeSolution)/.test(js),
    'app.js never calls into SOLVE_APPLY - the module would be dead code');
});

/* ---- describeSolution: what is about to be written --------------------- */
t('describeSolution shows RA/Dec, roll and scale', function () {
  const d = SA.describeSolution(SOLVED);
  assert.ok(/RA \d+h\d+m\d+s/.test(d), 'no RA in: ' + d);
  assert.ok(/Dec -5°/.test(d), 'no Dec in: ' + d);
  assert.ok(d.indexOf('12.50') >= 0, 'no roll in: ' + d);
  assert.ok(d.indexOf('1.872') >= 0, 'no pixel scale in: ' + d);
});

t('describeSolution returns null for an unsolved or absent solution', function () {
  assert.strictEqual(SA.describeSolution(null), null);
  assert.strictEqual(SA.describeSolution({ solved: false }), null);
  assert.strictEqual(SA.describeSolution({}), null);
});

t('missing numerics degrade to ? rather than NaN', function () {
  const d = SA.describeSolution({ solved: true, ra_deg: 10.5, dec_deg: 20.25 });
  assert.ok(d.indexOf('NaN') < 0, 'NaN leaked into: ' + d);
  assert.ok(d.indexOf('roll ?') >= 0, 'missing roll should render ?: ' + d);
});

t('zero-valued fields are shown, not treated as missing', function () {
  const d = SA.describeSolution({ solved: true, ra_deg: 0, dec_deg: 0,
    roll_deg: 0, pixscale_arcsec: 0 });
  assert.ok(d.indexOf('roll 0.00') >= 0, 'a real zero must print: ' + d);
  assert.ok(d.indexOf('NaN') < 0, 'NaN in: ' + d);
});

/* ---- applyRequest: what gets sent -------------------------------------- */
t('applyRequest sends nothing when there is no solution', function () {
  const r = SA.applyRequest({ solution: null });
  assert.strictEqual(r.send, false);
  assert.ok(r.reason.length > 0, 'must explain why nothing was sent');
});

t('applyRequest sends for a solved frame', function () {
  const r = SA.applyRequest({ solution: SOLVED });
  assert.strictEqual(r.send, true);
  assert.strictEqual(r.query, '', 'no force requested');
});

t('force=1 goes on the query string, not the body', function () {
  /* polaris-httpd.c reads it with param(qs, "force"), so a body field is ignored. */
  const r = SA.applyRequest({ solution: SOLVED }, { force: true });
  assert.strictEqual(r.query, '?force=1');
});

t('applyRequest tolerates a missing state object', function () {
  assert.strictEqual(SA.applyRequest().send, false);
  assert.strictEqual(SA.applyRequest(null).send, false);
});

/* ---- applyOutcome: what the user is told afterwards -------------------- */
t('success reports that the alignment was written, with the frame age', function () {
  const o = SA.applyOutcome({ ok: true, age_sec: 42 });
  assert.strictEqual(o.ok, true);
  assert.ok(/written/i.test(o.text), o.text);
  assert.ok(o.text.indexOf('42') >= 0, 'age_sec must be surfaced: ' + o.text);
});

t('failure surfaces the server error verbatim', function () {
  const o = SA.applyOutcome({ ok: false, error: 'mount is not aligned' });
  assert.strictEqual(o.ok, false);
  assert.ok(o.text.indexOf('mount is not aligned') >= 0, o.text);
});

t('a stale-solution refusal is passed through, not swallowed', function () {
  const o = SA.applyOutcome({ ok: false, age_sec: 900,
    error: 'that solution is 900 s old -- the mount has probably moved since' });
  assert.strictEqual(o.ok, false);
  assert.ok(o.text.indexOf('900 s old') >= 0, o.text);
});

/* THE CENTRAL GUARD: an absent or malformed reply must never read as success. */
t('no reply is reported as NOT confirmed, never as success', function () {
  [undefined, null, 'not json', 0, '', [], true].forEach(function (bad) {
    const o = SA.applyOutcome(bad);
    assert.strictEqual(o.ok, false, 'treated ' + JSON.stringify(bad) + ' as success');
    assert.ok(/not confirmed|no usable reply/i.test(o.text), o.text);
  });
});

t('ok:undefined is not treated as success', function () {
  /* A truncated body that parses but carries no ok field must not claim a write. */
  const o = SA.applyOutcome({ result: 'some text' });
  assert.strictEqual(o.ok, false, 'missing ok field read as success');
});

/* ---- the age budget cannot silently drift from the server -------------- */
t('APPLY_MAX_AGE_SEC matches maxage in polaris-httpd.c', function () {
  const c = fs.readFileSync(path.join(REPO, 'container/astro/polaris-httpd.c'), 'utf8');
  const m = c.match(/long fep = 0, age = 0, maxage = (\d+)/);
  assert.ok(m, 'could not find the /api/apply age budget in polaris-httpd.c');
  assert.strictEqual(SA.APPLY_MAX_AGE_SEC, parseInt(m[1], 10),
    'UI budget ' + SA.APPLY_MAX_AGE_SEC + ' != server budget ' + m[1]);
});

console.log(passed + ' assertion group(s) passed' +
  (process.exitCode ? ' -- WITH FAILURES' : ''));
