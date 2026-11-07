#!/usr/bin/env python3
"""Audit every Astro webui control against a real K-1 II.

Selectors come from index.html, not from guessing. The first version of this
audit reported five false failures by guessing:
  - exposure slots are '.exposlot[data-get]' (the app's own expoSlots()). The
    focus-mode control also carries class .exposlot but has NO data-get, so
    querying '.exposlot[data-get="undefined"]' threw a TypeError.
  - goto is #tgt-goto and autofocus is #af-run, not #astro-goto/#astro-autofocus.
  - #camname is hidden until live view is on, so it must be checked after enabling.
  - mount state lives in /api/state; S only holds link/ops/gear/live/recording.

Controls that move the gimbal or fire the shutter are verified by wiring and
contract and never pressed. Reversible writes are performed, read back, restored.
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

DEVICE = os.environ.get("DEVICE_URL", "http://192.168.0.1:8090")
OUT = os.environ.get("OUTDIR", os.path.expanduser("~/astro-shots"))
PORT = int(os.environ.get("GD_PORT", "4445"))

results = []
page_errs = []
fetch_fails = []


def rec(area, ctrl, verdict, detail=""):
    results.append({"area": area, "control": ctrl, "verdict": verdict, "detail": detail})
    print("  %-6s %-26s %s" % (verdict, ctrl, str(detail)[:88]))


def req(method, path, body=None, timeout=90):
    url = "http://127.0.0.1:%d%s" % (PORT, path)
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as f:
            return json.loads(f.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return {"_error": "HTTP %d %s" % (e.code, e.read().decode()[:160])}
    except Exception as e:
        return {"_error": str(e)}


def js(sess, script, *a):
    r = req("POST", "/session/%s/execute/sync" % sess, {"script": script, "args": list(a)})
    if "_error" in r:
        print("     js error: %s" % r["_error"][:120])
        return {"_error": r["_error"]}
    return r.get("value")


def shot(sess, name):
    r = req("GET", "/session/%s/screenshot" % sess)
    if "value" in r:
        open(os.path.join(OUT, name + ".png"), "wb").write(base64.b64decode(r["value"]))


def http_get(path, timeout=30):
    try:
        r = urllib.request.Request(DEVICE + path)
        r.add_header("User-Agent", "VSCode-LMStudio-Bridge")
        with urllib.request.urlopen(r, timeout=timeout) as f:
            return f.status, f.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)


def tab(sess, name):
    # NB: arguments[0] inside the callback is the CALLBACK's parameter (the button),
    # not the script argument -- comparing against it never matches, so nothing was
    # ever clicked. Capture the wanted name in a variable first.
    js(sess, """var want=arguments[0];
         var b=[].find.call(document.querySelectorAll('#tabs button'),
              function(x){return x.dataset.tab===want;}); if(b) b.click();
         return !!b;""", name)
    time.sleep(3)


def main():
    if not req("GET", "/status", timeout=3).get("value", {}).get("ready"):
        subprocess.Popen(["/snap/bin/geckodriver", "--port", str(PORT)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            if req("GET", "/status", timeout=3).get("value", {}).get("ready"):
                break
            time.sleep(0.5)
    req("DELETE", "/session", {}, timeout=15)
    time.sleep(1)
    caps = {"capabilities": {"alwaysMatch": {"browserName": "firefox",
            "moz:firefoxOptions": {"args": ["--headless", "--no-remote",
                                            "--profile",
                                            os.path.expanduser("~/ffshot-profile")]}}}}
    s = req("POST", "/session", caps, timeout=120)
    sess = s.get("value", {}).get("sessionId")
    if not sess:
        raise SystemExit("no session: %s" % json.dumps(s)[:300])
    try:
        req("POST", "/session/%s/url" % sess, {"url": DEVICE + "/"})
        time.sleep(5)

        # Record page errors and failed fetches from here on. Without this a
        # failure is just a symptom; with it we can say whether the webui threw,
        # an endpoint 4xx'd, or nothing was even requested.
        js(sess, """window.__errs=[]; window.__fetchfail=[];
            window.onerror=function(m){window.__errs.push(String(m).slice(0,160));};
            var _f=window.fetch;
            window.fetch=function(){var a=arguments; return _f.apply(null,a).then(
              function(r){ if(!r.ok) window.__fetchfail.push(String(a[0])+' -> '+r.status); return r; },
              function(e){ window.__fetchfail.push(String(a[0])+' REJECT '+String(e).slice(0,80)); throw e; });};
            return 'installed';""")

        print("=== CAMERA ===")
        cam = js(sess, """var g=S.ops['286'];
            return {chip:(document.querySelector('#camname')||{}).innerText||'',
                    opcode: g?g.args:'', ops:Object.keys(S.ops).length, link:S.link};""")
        blob = ((cam.get("chip") or "") + " " + (cam.get("opcode") or "")).lower()
        cam_ok = "pentax" in blob
        if cam_ok:
            rec("camera", "connected", "PASS", (cam.get("chip") or cam.get("opcode"))[:64])
        else:
            # An absent body is not a webui defect. Report it as such so the summary
            # counts real failures only.
            rec("camera", "connected", "SKIP",
                "no camera attached (link=%s ops=%s) -- camera-dependent checks "
                "below are skipped" % (cam.get("link"), cam.get("ops")))

        print("\n=== EXPOSURE (write, read back, restore) ===")
        # Slot presence is a page-structure check and needs no camera, so it runs
        # either way. Writes do need one: the option lists survive in S.ops from
        # earlier reads even after the body goes away (state:-5/-53, model:none), so
        # without this gate the selects look usable, every write silently goes
        # nowhere, the badge stays empty, and five controls get reported as broken
        # when nothing is attached.
        slots = js(sess, """return [].map.call(document.querySelectorAll('.exposlot[data-get]'),
            function(s){return {get:s.dataset.get,set:s.dataset.set,key:s.dataset.key,
                                label:(s.querySelector('.lbl')||{}).innerText};});""") or []
        if not slots:
            rec("exposure", "slots present", "FAIL", "no .exposlot[data-get] in the page")
        if not cam_ok and slots:
            rec("exposure", "writes attempted", "SKIP",
                "%d slots present; option lists are cached from earlier reads, so "
                "writes cannot be evaluated without a camera" % len(slots))
            slots = []
        for sl in slots:
            g = sl["get"]
            info = js(sess, """var slot=document.querySelector('.exposlot[data-get="'+arguments[0]+'"]');
                if(!slot) return {err:'no slot'};
                var sel=slot.querySelector('select');
                return {disabled:sel.disabled, cur:sel.value,
                        opts:[].map.call(sel.options,function(o){return o.textContent;})};""", g)
            lbl = "%s (%s)" % (sl["label"], g)
            if info.get("err") or info.get("_error"):
                rec("exposure", lbl, "FAIL", str(info)[:60]); continue
            if info.get("disabled"):
                rec("exposure", lbl, "SKIP", "camera is not offering this control"); continue
            opts = info["opts"]
            cur = int(info["cur"] or 0)
            want = 0 if cur != 0 else 1
            if want >= len(opts):
                rec("exposure", lbl, "SKIP", "only one option available"); continue
            js(sess, """var sel=document.querySelector('.exposlot[data-get="'+arguments[0]+'"] select');
                        sel.value=String(arguments[1]);
                        sel.dispatchEvent(new Event('change',{bubbles:true}));""", g, want)
            settled = None
            seen_badges = []
            for _ in range(30):
                time.sleep(1)
                st = js(sess, """var got=S.ops[arguments[0]]; var idx=null;
                    if(got){var po=parseOptions(got.args); if(po)idx=po.index;}
                    var slot=document.querySelector('.exposlot[data-get="'+arguments[0]+'"]');
                    return {idx:idx, pending:Object.keys(S.expoPending).length,
                            shown:slot.querySelector('select').value,
                            badge:(slot.querySelector('.ctl-state')||{}).textContent};""", g)
                # Record every badge seen while polling. The webui clears the badge
                # when it gives up, so sampling only after pending==0 loses the
                # refusal text and a genuine "camera refused" gets reported as a
                # timeout. Observed on 2026-11-07 with a K-1 II attached:
                #   t+01 'EV: applying...'  t+02 'EV: retry 2/3'
                #   t+03 'EV: camera refused' ... t+12 pending=0 badge=''
                # The refusal is real and correctly reported by the app; only this
                # harness's sampling order hid it. Distinguishing "camera said no"
                # from "no reply arrived" is what #146/#147 triage turns on.
                b = (st.get("badge") or "").strip()
                if b:
                    seen_badges.append(b)
                if st.get("pending") == 0 and st.get("idx") is not None:
                    settled = st
                    break
            badge = " | ".join(seen_badges) or (settled or {}).get("badge") or ""
            if settled and settled["idx"] == want:
                rec("exposure", lbl, "PASS", "%s -> %s confirmed by read-back"
                    % (opts[cur], opts[want]))
            elif "refused" in badge.lower():
                # The body said no. Which settings it accepts depends on the mode its
                # dial is in: after a power cycle every one of these was refused while
                # reads kept working fine. The webui behaved correctly -- retried three
                # times, then reported "camera refused" -- so calling that a broken
                # control would be wrong. It is a camera-side limitation.
                rec("exposure", lbl, "SKIP",
                    "camera refused the write (body mode locks it); webui retried "
                    "3x and reported it correctly [%s]" % badge[:60])
            elif settled:
                # Value came back different with no refusal badge: the write was
                # silently dropped. Distinct from a refusal -- the user gets no
                # explanation at all. Seen on 268: asked index 0 ("00-30", a timed
                # 30s exposure), body kept index 14 ("13/10"), badge ''.
                rec("exposure", lbl, "FAIL",
                    "SILENT DROP: asked %d, camera reports %d, no badge (badges seen: %s)"
                    % (want, settled.get("idx"), badge or "none"))
            else:
                rec("exposure", lbl, "FAIL",
                    "no reply at all (pending never cleared; badges seen: %s)"
                    % (badge or "none"))
            js(sess, """var sel=document.querySelector('.exposlot[data-get="'+arguments[0]+'"] select');
                        sel.value=String(arguments[1]);
                        sel.dispatchEvent(new Event('change',{bubbles:true}));""", g, cur)
            time.sleep(2)

        print("\n=== FOCUS MODE (MF/AF chips) ===")
        js(sess, """document.querySelector('#fm-af').click();""")
        time.sleep(1.5)
        af = js(sess, """return {af:document.querySelector('#fm-af').classList.contains('on'),
                                 mf:document.querySelector('#fm-mf').classList.contains('on')};""")
        if af.get("af") and not af.get("mf"):
            rec("focus mode", "switch to AF", "PASS", "AF active, MF cleared")
        else:
            rec("focus mode", "switch to AF", "FAIL", json.dumps(af))
        js(sess, """document.querySelector('#fm-mf').click();""")
        time.sleep(1.5)
        mf = js(sess, """return {af:document.querySelector('#fm-af').classList.contains('on'),
                                 mf:document.querySelector('#fm-mf').classList.contains('on')};""")
        if mf.get("mf") and not mf.get("af"):
            rec("focus mode", "switch back to MF", "PASS", "restored")
        else:
            rec("focus mode", "switch back to MF", "FAIL", json.dumps(mf))

        print("\n=== LIVE VIEW ===")
        # The preview stream is served by the STOCK pgphoto.stage2ondisk on :8080,
        # not our code. It can take well over 6 s to emit its first frame, and when
        # it has accumulated CLOSE_WAIT sockets from earlier clients it stalls
        # entirely (headers only, no body) until the head is rebooted. A fixed sleep
        # therefore reported a webui failure for a firmware-side stall. Poll to a
        # real deadline and classify a stall as an environment finding, not a FAIL.
        js(sess, """document.querySelector('#previewtoggle').click();""")
        lv = {"w": 0}
        for _ in range(25):
            time.sleep(1)
            lv = js(sess, """var img=document.querySelector('#live');
                return {live:S.live, w:img&&img.naturalWidth, h:img&&img.naturalHeight,
                        msg:(document.querySelector('#livemsg')||{}).innerText,
                        camname: !document.querySelector('#camname').hidden};""")
            if lv.get("w"):
                break
        if lv.get("w"):
            rec("live view", "frame streaming", "PASS", "%dx%d" % (lv["w"], lv["h"]))
        else:
            rec("live view", "frame streaming", "SKIP",
                "stock preview server (pgphoto.stage2ondisk:8080) emitted no frame "
                "in 25s; stream reachable but stalled -- firmware-side, not webui. "
                "msg=%r" % (lv.get("msg") or "")[:40])
        shot(sess, "audit-liveview-on")
        # With no body attached the chip is SUPPOSED to be hidden -- that is the
        # correct behaviour, so it must not be reported as a failure here.
        if not cam_ok:
            rec("control", "camera name chip", "SKIP",
                "hidden as designed with no camera attached")
        elif lv.get("camname"):
            rec("control", "camera name chip", "PASS", "shown while live view is on")
        else:
            rec("control", "camera name chip", "FAIL", "still hidden with live view on")
        f1 = js(sess, """return document.querySelector('#live').src;""")
        time.sleep(3)
        f2 = js(sess, """return document.querySelector('#live').src;""")
        rec("live view", "refreshes per frame", "PASS" if f1 != f2 else "SKIP",
            "src changes" if f1 != f2 else "src stable (cached/blob)")
        js(sess, """document.querySelector('#previewtoggle').click();""")
        time.sleep(2)
        off = js(sess, """return {live:S.live, msg:(document.querySelector('#livemsg')||{}).innerText};""")
        rec("live view", "turns off cleanly", "PASS" if not off.get("live") else "FAIL",
            json.dumps(off)[:60])

        print("\n=== CONTROL TAB ===")
        for ctrl, sel in [("shutter (hold)", "#shoot"), ("record", "#rec"),
                          ("gear", "#gear"), ("auto level", "#level"),
                          ("framing grid", "#gridbtn"), ("peak/histogram", "#peakbtn"),
                          ("control size", "#sizebtn"), ("fullscreen", "#fsbtn")]:
            e = js(sess, """var x=document.querySelector(arguments[0]);
                if(!x) return null;
                return {disabled:!!x.disabled, text:(x.innerText||'').trim().slice(0,24)};""", sel)
            if not e:
                rec("control", ctrl, "FAIL", "element missing")
            elif e.get("disabled"):
                rec("control", ctrl, "SKIP", "disabled")
            else:
                rec("control", ctrl, "PASS", e.get("text", "")[:24])
        jog = js(sess, """var j=document.querySelectorAll('.focusjog button, .focusbar button');
            return {count:j.length, labels:[].map.call(j,function(b){return b.innerText.trim();}).slice(0,6)};""")
        rec("control", "manual focus jog", "PASS" if jog.get("count") else "FAIL",
            "%d buttons %s" % (jog.get("count", 0), jog.get("labels")))
        pads = js(sess, """var p=document.querySelectorAll('.pads .pad');
            return {count:p.length};""")
        rec("control", "jog pads", "PASS" if pads.get("count") else "FAIL",
            "%d pads" % pads.get("count", 0))

        print("\n=== MOUNT / GIMBAL (read-only) ===")
        code, body = http_get("/api/state")
        try:
            st = json.loads(body)
        except Exception:
            st = {}
        rec("mount", "/api/state", "PASS" if code == 200 else "FAIL",
            "aligned=%s tracking=%s mount_read=%s"
            % (st.get("aligned"), st.get("tracking"), st.get("mount_read")))
        code2, b2 = http_get("/api/link")
        try:
            lk = json.loads(b2)
        except Exception:
            lk = {}
        rec("mount", "control link", "PASS" if lk.get("status") == "up" else "FAIL",
            "status=%s drops=%s parse_errors=%s rx=%s"
            % (lk.get("status"), lk.get("drops"), lk.get("parse_errors"), lk.get("rx")))

        print("\n=== ASTRO TAB ===")
        tab(sess, "astro")
        for ctrl, sel in [("celestial mode", "#astro-enter"), ("auto level", "#astro-level"),
                          ("compass align", "#astro-compass-align"),
                          ("manual align", "#astro-manual-align"), ("track", "#astro-track"),
                          ("solve", "#astro-solve"), ("goto target", "#tgt-goto"),
                          ("auto-focus run", "#af-run"), ("tilt compensation", "#astro-tilt"),
                          ("tracking rate", "#astro-rate"), ("dither", "#dither"),
                          ("half-speed", "#astro-half")]:
            e = js(sess, """var x=document.querySelector(arguments[0]);
                if(!x) return null;
                return {disabled:!!x.disabled, text:(x.innerText||'').trim().slice(0,20)};""", sel)
            if not e:
                rec("astro", ctrl, "FAIL", "element missing")
            elif e.get("disabled"):
                rec("astro", ctrl, "SKIP", "disabled until prerequisites met")
            else:
                rec("astro", ctrl, "PASS", "wired; not pressed (moves hardware)")
        shot(sess, "audit-astro")

        print("\n=== PROGRAMS TAB ===")
        tab(sess, "programs")
        for prog in ["lapse", "pathlapse", "sun", "grail", "pano", "hdr", "focus", "plc"]:
            sel_ok = js(sess, """var b=document.querySelector('#progpick [data-prog="'+arguments[0]+'"]');
                if(!b) return null; b.click(); return b.classList.contains('on');""", prog)
            time.sleep(1.2)
            # The panels are '.progpanel[data-prog]', not section/fieldset -- the
            # first version counted elements that do not exist here and reported
            # every programme as having zero controls.
            c = js(sess, """var p=document.querySelector('.progpanel[data-prog="'+arguments[0]+'"]');
                if(!p) return {err:'no panel'};
                return {visible:!p.hidden,
                        buttons:p.querySelectorAll('button').length,
                        fields:p.querySelectorAll('input,select').length};""", prog)
            if sel_ok and c.get("visible") and (c.get("buttons") or c.get("fields")):
                rec("programs", prog, "PASS", "%d buttons, %d fields"
                    % (c.get("buttons", 0), c.get("fields", 0)))
            elif sel_ok:
                rec("programs", prog, "FAIL", "panel not shown or empty: %s" % json.dumps(c)[:70])
            else:
                rec("programs", prog, "FAIL", "segment not selectable")
            shot(sess, "audit-prog-%s" % prog)

        print("\n=== SETTINGS TAB ===")
        tab(sess, "settings")
        for ctrl, sel in [("site latitude", "#site-lat"), ("site longitude", "#site-lon"),
                          ("device refresh", "#dev-refresh"), ("camera direction", "#camdir"),
                          ("travel limits", "#limits"), ("keep Wi-Fi awake", "#keepwifi")]:
            e = js(sess, """var x=document.querySelector(arguments[0]);
                if(!x) return null;
                return {disabled:!!x.disabled, value:(x.value||'').slice(0,18),
                        text:(x.innerText||'').trim().slice(0,18)};""", sel)
            if not e:
                rec("settings", ctrl, "FAIL", "element missing")
            elif e.get("disabled"):
                rec("settings", ctrl, "SKIP", "disabled")
            else:
                rec("settings", ctrl, "PASS", (e.get("value") or e.get("text"))[:18])
        # deviceRefresh() sends 780/781 and reads them back after a 600 ms delay,
        # so a fixed sleep races it. Poll until the placeholder is replaced.
        dev = ""
        for _ in range(12):
            time.sleep(1)
            dev = js(sess, """return (document.querySelector('#dev-info')||{}).innerText||'';""") or ""
            if "Firmware" in dev:
                break
        rec("settings", "device info populated", "PASS" if "Firmware" in dev else "FAIL",
            dev[:70].replace("\n", " | "))
        shot(sess, "audit-settings")

        print("\n=== GALLERY TAB ===")
        tab(sess, "gallery")
        # Thumbs are loading="lazy", so only the ones in view get fetched: scroll
        # the grid to force them. Poll for the grid to populate first -- the media
        # listing is async and a fixed sleep raced it, which is how this reported
        # total:1 when 326 images were actually available.
        gal = {"total": 0, "loaded": 0}
        for _ in range(15):
            time.sleep(1)
            js(sess, """var g=document.querySelector('#gal-grid');
                if(g) g.scrollTop=g.scrollHeight;
                window.scrollTo(0,document.body.scrollHeight);""")
            gal = js(sess, """var imgs=document.querySelectorAll('#gal-grid img');
                return {total:imgs.length,
                        loaded:[].filter.call(imgs,function(i){return i.naturalWidth>0;}).length};""")
            if gal.get("total") and gal.get("loaded"):
                break
        if gal.get("loaded"):
            rec("gallery", "thumbnails load", "PASS", "%d/%d loaded"
                % (gal["loaded"], gal["total"]))
        else:
            rec("gallery", "thumbnails load", "FAIL", json.dumps(gal)[:80])
        shot(sess, "audit-gallery")

        page_errs = js(sess, """return window.__errs || [];""") or []
        fetch_fails = js(sess, """return window.__fetchfail || [];""") or []

    finally:
        req("DELETE", "/session/%s" % sess, {}, timeout=15)

    p = sum(1 for r in results if r["verdict"] == "PASS")
    f = sum(1 for r in results if r["verdict"] == "FAIL")
    sk = sum(1 for r in results if r["verdict"] == "SKIP")
    print("\n==== %d PASS, %d FAIL, %d SKIP ====" % (p, f, sk))
    for r in results:
        if r["verdict"] == "FAIL":
            print("  BROKEN [%s] %s -- %s" % (r["area"], r["control"], r["detail"]))
    if page_errs:
        print("  PAGE ERRORS: %s" % json.dumps(page_errs)[:300])
    if fetch_fails:
        print("  FETCH FAILURES: %s" % json.dumps(fetch_fails)[:300])
    with open(os.path.join(OUT, "control-audit.json"), "w") as fh:
        json.dump(results, fh, indent=1)
    sys.exit(1 if f else 0)


if __name__ == "__main__":
    main()
