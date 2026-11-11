/* "Apply last solve" contract for #329.
 *
 * DOM-free and network-free on purpose, exactly like shutter.js (#309), so
 * tests/test_astro_solve_apply.js can assert the whole decision table under
 * node. app.js loads this first and calls into it; nothing here touches
 * document or fetch.
 *
 * WHY IT EXISTS
 *
 * #solve-apply used to be three lines that posted an empty body:
 *
 *   post('/api/apply', {}).then(function (r) {
 *     if (r && r.ok === false) setHint('<b>Apply:</b> ' + (r.error || ''));
 *     solveGet();
 *   });
 *
 * The user therefore wrote an alignment from a solution they could not see.
 * /api/apply refuses stale solutions by comparing the frame epoch to a 600 s
 * budget, and reports age_sec in its reply -- all of it was thrown away by the
 * caller, which showed nothing on success and only a bare error string on
 * failure. This module turns that into an explicit, testable contract: what is
 * about to be applied, and what actually happened afterwards.
 *
 * WHAT THIS DELIBERATELY DOES NOT DO
 *
 * #329 also asks that Apply respect the focal-length field. It does not, and
 * that is not an oversight. Focal length selects the search space at solve time;
 * once a frame is solved, RA/Dec are already resolved and applying them writes no
 * focal anywhere. Worse, polaris-httpd.c runs every solve as --focal auto on
 * purpose: "Forcing g_focal here would reintroduce the bug that cost a whole
 * night -- a stale command-line focal overriding what the frame itself says."
 * Threading a UI focal into apply would recreate that class of defect, so the
 * field is shown for context instead of being sent. The age budget is likewise
 * not duplicated as a client-side gate: /api/apply re-reads the epoch itself and
 * is the authority. Duplicating a hard refusal here would create a second source
 * of truth that can disagree with the server -- the same class of bug #309 hit
 * when the WebUI tried to decide shutter subtype itself.
 */

/* Age budget of /api/apply, in seconds, mirroring maxage in polaris-httpd.c.
 * Advisory only: the server is the authority and always re-checks. The node test
 * asserts this against the C source so drift between the two is caught. */
var APPLY_MAX_AGE_SEC = 600;

/* RA/Dec as hms/dms. Returns null rather than a placeholder so callers can tell
 * "no usable coordinates" apart from "coordinates that happen to be zero". */
function formatRaDec(sol) {
  var ra, dec, h, hh, mm, ss, sign, da, dd, dm;
  if (!sol || sol.solved !== true) return null;
  ra = sol.ra_deg;
  dec = sol.dec_deg;
  if (typeof ra !== 'number' || typeof dec !== 'number') return null;
  h = ra / 15;
  hh = Math.floor(h);
  mm = Math.floor((h - hh) * 60);
  ss = Math.round((((h - hh) * 60) - mm) * 60);
  sign = dec < 0 ? '-' : '+';
  da = Math.abs(dec);
  dd = Math.floor(da);
  dm = Math.round((da - dd) * 60);
  return 'RA ' + hh + 'h' + mm + 'm' + ss + 's · Dec ' + sign + dd + '°' + dm + "'";
}

/* One-line description of what "Apply last" is about to write.
 *
 * Only fields the solver is known to emit are used -- ra_deg, dec_deg, roll_deg,
 * pixscale_arcsec, nmatch/nfield -- which are exactly the ones the built-in
 * fallback page in polaris-httpd.c already reads off s.solution. A missing or
 * non-numeric field degrades to a dash rather than printing NaN, because a NaN in
 * an alignment confirmation line is worse than no line: it invites the user to
 * trust a number that means nothing. */
function describeSolution(sol) {
  var parts, rd, roll, scale, nm, nf;
  if (!sol || sol.solved !== true) return null;
  parts = [];
  rd = formatRaDec(sol);
  if (rd) parts.push(rd);
  roll = Number(sol.roll_deg);
  parts.push('roll ' + (isFinite(roll) ? roll.toFixed(2) + '°' : '?'));
  scale = Number(sol.pixscale_arcsec);
  parts.push('scale ' + (isFinite(scale) ? scale.toFixed(3) + '"px' : '?'));
  nm = Number(sol.nmatch);
  nf = Number(sol.nfield);
  if (isFinite(nm) && isFinite(nf)) parts.push(nm + '/' + nf + ' stars');
  return parts.join(' · ');
}

/* Decide what /api/apply should be asked to do.
 *
 * state: the parsed /api/state reply ({ solution, ... }).
 * opts:  { force: bool }
 *
 * Returns { send: bool, query: string, reason: string }.
 *
 * There is deliberately no age check here. /api/state does not report the frame
 * age -- only /api/apply's reply carries age_sec -- so a client-side staleness
 * gate would be guessing. The server refuses stale solutions with its own precise
 * message and this module surfaces it verbatim through applyOutcome().
 *
 * force=1 is passed through because /api/apply reads it from the query string
 * (param(qs, "force")), not the POST body, so it must go on the URL.
 */
function applyRequest(state, opts) {
  var sol, out;
  state = state || {};
  opts = opts || {};
  sol = state.solution;

  if (!sol || sol.solved !== true) {
    return { send: false, query: '', reason: 'no solved frame to apply' };
  }

  out = { send: true, query: '', reason: '' };
  if (opts.force === true) out.query = '?force=1';
  return out;
}

/* Human-readable outcome of an /api/apply reply.
 *
 * The endpoint answers one of:
 *   {ok:true,  age_sec, result}
 *   {ok:false, error, [age_sec]}
 * Anything else -- a proxy error, a truncated body, a non-JSON page -- is
 * reported as unknown rather than as success. Claiming an alignment was written
 * when the reply never said so is the exact failure this module exists to
 * prevent, and it is the same false-pass class of bug libgphoto2 #143 removed on
 * the driver side.
 */
function applyOutcome(reply) {
  var age;
  /* Array.isArray is not redundant: a JSON array satisfies typeof === 'object',
   * so without it a body like [] falls through to the failure branch and reads
   * back as "Apply: <error>", i.e. as though the head had refused the write. It
   * did not answer at all, which is a different thing and must be said
   * differently. */
  if (!reply || typeof reply !== 'object' || Array.isArray(reply)) {
    return { ok: false, text: 'Apply: no usable reply from the head - alignment not confirmed' };
  }
  if (reply.ok === true) {
    age = Number(reply.age_sec);
    return {
      ok: true,
      text: 'Alignment written' +
        (isFinite(age) ? ' (frame was ' + Math.round(age) + ' s old)' : '')
    };
  }
  return { ok: false, text: 'Apply: ' + (reply.error || 'failed') };
}

var SOLVE_APPLY = {
  APPLY_MAX_AGE_SEC: APPLY_MAX_AGE_SEC,
  formatRaDec: formatRaDec,
  describeSolution: describeSolution,
  applyRequest: applyRequest,
  applyOutcome: applyOutcome
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = SOLVE_APPLY;
}
