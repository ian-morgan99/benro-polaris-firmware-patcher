/* Shutter dispatch and completion reconciliation for #309.
 *
 * This file is deliberately free of DOM and network access so it can be loaded
 * and asserted directly by tests/test_astro_shutter.js under node. app.js loads
 * it first and calls into it; nothing here reaches for document or fetch.
 *
 * WHY IT EXISTS
 *
 * Before this, wireShutter()'s fire() sent one hardcoded payload for every
 * press: 'state:1;bulb:0;c:0;'. Two problems, both confirmed against the
 * device's own traffic log rather than inferred:
 *
 *   - c:0 is Benro Connect's CONTINUATION-shooting stop branch. The ordinary
 *     single capture and the ordinary stop both use c:-1. In /app/sd/system/log/
 *     Mlog_*.log on a live Polaris, 'state:1;bulb:0;c:-1;' appears 27 times and
 *     'state:1;bulb:0;c:0;' only 5 -- the app's normal trigger is c:-1.
 *   - There was no bulb path at all. A timed long exposure could not be started
 *     from the WebUI, so a user who wanted one had to put the phone down and
 *     open Benro Connect. Timed B traffic in the same log reads
 *     'state:1;bulb:5;c:-1;', 'bulb:2', 'bulb:42' -- duration rides in bulb.
 *
 * THE SUBSYSTEM FIELD IS NOT THIS FILE'S PROBLEM, AND THAT IS DELIBERATE.
 *
 * The third wire field (the subsystem selector) is owned by OPCODES[] in
 * polaris-httpd.c, not by the client: /api/link/send calls plink_send(cmd,
 * pol->sub, args) and ignores anything the page sends. 264 is registered as
 * { 264, "photo", 2, 1, ... }, so every shutter command already rides subsystem
 * 2, which is what the decompiled SP_SET_PHOTO_RECORD_STATUS uses and what the
 * captured traffic confirms (type:2 for both M and timed B). A client-side
 * subtype parameter would have been a second source of truth for something the
 * server already decides -- and a wrong selector is not rejected by the head, it
 * is silently ignored. So there is no setSubtype() here on purpose.
 */
'use strict';

/* The distinct outcomes the UI must be able to show separately. Collapsing
 * "queued" into "shot" is the exact bug #279 was about: /api/link/send answers
 * ok:true as soon as the command is written to the socket, which says nothing
 * about whether the camera took the frame. */
var SHOT_PHASES = {
  idle:      'hold to shoot',
  queued:    'queued…',
  started:   'exposing…',
  writing:   'writing card…',
  published: 'file written',
  complete:  'shot',
  failed:    'failed',
  unknown:   'no confirmation',
  refused:   'mode not confirmed'
};

/* Opcode 264 lifecycle states, kept in step with the terminal set in
 * scripts/capture-outcomes.py so the UI and the offline analyser agree. state:1
 * is only "initiated"; a capture is finished when state:0 follows state:4. */
var SHOT_LIFECYCLE = { 1: 'started', 2: 'started', 3: 'started', 4: 'writing' };

/* A long exposure legitimately runs for tens of seconds and silence is not
 * evidence of failure, so the deadline is generous and reports "unknown" rather
 * than "failed" when it expires. */
var SHOT_TIMEOUT_MS = 90000;

/* Benro Connect's own contract, from SP_SET_PHOTO_RECORD_STATUS(state, bulb, c)
 * -> sendOrder(264, 2, "state:"+state+";bulb:"+bulb+";c:"+c+";"). The ordinary
 * trigger and the ordinary stop both pass c:-1; c:0 belongs to the separate
 * continuation-shooting branch and must not be used as a substitute here. */
function startPayload(bulbSeconds) {
  var bulb = 0;
  if (bulbSeconds !== null && bulbSeconds !== undefined) {
    bulb = Number(bulbSeconds);
    /* Reject rather than floor, for the same reason as decideDispatch. This is
     * the last gate before the payload reaches the wire, so it has to be strict
     * on its own and not rely on the caller having checked. */
    if (!isFinite(bulb) || bulb < 1 || Math.floor(bulb) !== bulb) {
      throw new RangeError('bulb seconds must be a whole number at least 1, got ' +
                           String(bulbSeconds));
    }
  }
  return 'state:1;bulb:' + bulb + ';c:-1;';
}

/* The source-aligned stop. Note bulb:0 even when the start carried a duration:
 * the field names the requested exposure on the way in and is cleared on the
 * way out, matching the decompiled stop path. */
function stopPayload() {
  return 'state:0;bulb:0;c:-1;';
}

/* Decide what a press means WITHOUT guessing about the camera.
 *
 * #309 asks for B mode to be verified from the camera's mode information and for
 * an unknown or failed mode read to be rejected rather than guessed. That is the
 * right rule, and it cannot be satisfied as written: no opcode in our documented
 * set reports the camera's exposure mode. 284 is the MOUNT's operating mode
 * (Photo/Sun/Astro/Free program/Video) and 286 is the connected camera's
 * identity -- neither says M or B, and reading either would be guessing, which
 * is what the rule forbids. Inferring it from the shape of 268's shutter list is
 * also forbidden by the same rule, and would be wrong anyway: a body can offer
 * "B" in its list while sitting in M.
 *
 * So the honest implementation is that B is an explicit user intent, never an
 * inference. bulbSeconds === null means "let the camera use its own shutter
 * setting", which is what the app sends for an ordinary capture and is safe in
 * any mode. A positive duration is only ever sent when the user has asked for
 * it by name. The UI says so rather than implying it checked. */
function decideDispatch(bulbSeconds) {
  if (bulbSeconds === null || bulbSeconds === undefined || bulbSeconds === '' ||
      Number(bulbSeconds) === 0) {
    return { mode: 'M', bulbSeconds: null, payload: startPayload(null) };
  }
  var n = Number(bulbSeconds);
  /* Refuse rather than clamp. The markup's step is 0.5, so "2.5" is a value a
   * user can legitimately type, and the wire field is an integer number of
   * seconds -- flooring it would run a two-second exposure when three was asked
   * for, which on a long exposure is a visible, unexplained difference. Garbage
   * must not fall through to an ordinary capture either: that would take a shot
   * the user did not ask for. */
  if (!isFinite(n) || n < 1 || Math.floor(n) !== n) {
    return { mode: 'refused', bulbSeconds: null, payload: null,
             reason: 'bulb duration must be a whole number of seconds at least 1' };
  }
  return { mode: 'B', bulbSeconds: n, payload: startPayload(n) };
}

/* Parse the head's state field. Negative states are refusals -- -110 is the
 * PHOTO_RECORD Fail of #279, -6 is libgphoto2 declining a bulb timer. */
function shotStateOf(args) {
  var m = /(?:^|;)state:(-?\d+)/.exec(args || '');
  return m ? parseInt(m[1], 10) : null;
}

/* Pure completion reconciliation. Given what was sent and the head's current
 * cached 264 reply, return the phase to show. No DOM, no timers: app.js decides
 * when to call this and what to paint with it.
 *
 * pending: { sentAt, countBefore, mode, bulbSeconds, sawWriting }
 * reply:   the cached 264 entry ({ args, count }) or undefined
 * now:     clock reading in ms (injected so tests are deterministic)
 */
function reconcile(pending, reply, now) {
  if (!pending) return { phase: 'idle', terminal: true };

  /* The reply is matched by 264's count increasing since the press, so an older
   * cached answer cannot brand a new shot. */
  if (reply && reply.count > pending.countBefore) {
    var st = shotStateOf(reply.args);

    if (st === 0) {
      /* state:0 is the completion signal, and it is accepted on its own.
       *
       * An earlier version required having first seen an intermediate state
       * before calling this a success. That was wrong, and here is why: /api/link
       * caches ONE entry per opcode, so a capture that runs state:1 -> 4 -> 0
       * inside one 500 ms poll window is observed only as its final value. The
       * intermediate states are not queued, they overwrite each other. Requiring
       * one would turn ordinary fast captures into "no confirmation" -- a false
       * failure, which is the same class of defect as the false success this file
       * exists to remove.
       *
       * Grepping the head's own log for outbound 264 replies returns nothing on
       * this build (only inbound 'rcv msg from App' lines are recorded), so there
       * is no evidence that intermediate states are ever observable at all. Do not
       * invent a precondition that depends on them.
       */
      return { phase: pending.sawWriting ? 'published' : 'complete',
               terminal: true };
    }

    if (st !== null && st < 0) {
      return { phase: 'failed', terminal: true, state: st,
               reason: 'the camera refused the shot (state ' + st + ')' };
    }

    if (SHOT_LIFECYCLE[st]) {
      var next = SHOT_LIFECYCLE[st];
      return { phase: next, terminal: false,
               sawStarted: true,
               sawWriting: pending.sawWriting || next === 'writing' };
    }
  }

  if (typeof now === 'number' && (now - pending.sentAt) > SHOT_TIMEOUT_MS) {
    /* Silence is not failure. The frame may exist on the card; saying "failed"
     * would send the user off to debug a camera that is fine. */
    return { phase: 'unknown', terminal: true,
             reason: 'no capture confirmation from the head' };
  }

  return { phase: pending.phase || 'queued', terminal: false };
}

/* Expose for node (tests) without breaking the browser, where this file is a
 * plain script and these are already globals. Both paths must work: app.js calls
 * SHUTTER.decideDispatch() at boot, so if only module.exports were set the page
 * would throw "SHUTTER is not defined" and the whole UI would be dead -- a
 * failure that no JS unit test can catch, which is why tests/test_astro_shutter_node.py
 * also asserts index.html loads this file.
 */
var SHUTTER = {
  SHOT_PHASES: SHOT_PHASES,
  SHOT_LIFECYCLE: SHOT_LIFECYCLE,
  SHOT_TIMEOUT_MS: SHOT_TIMEOUT_MS,
  startPayload: startPayload,
  stopPayload: stopPayload,
  decideDispatch: decideDispatch,
  shotStateOf: shotStateOf,
  reconcile: reconcile
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = SHUTTER;
}
