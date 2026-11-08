#!/usr/bin/env python3
"""Read-only probe of the two failing exposure controls on a live K-1 II.

Why read-only for shutter: issue #251 reports that on this body an untimed-B
shutter value starts an exposure that the cancel control does NOT physically
terminate. The first run captured the real list, and index 0 is "00-30" -- a
timed 30-second exposure, not bulb as this script originally assumed. Either way
index 0 fires a real shutter release, so it is still not pressed here; only EV
(267), which has no shutter-release semantics, is written.

The assumption being wrong matters: index 0 is a timed 30 s exposure, so "asked 0,
camera reports 14" means the body kept its previous value ("13/10"). An earlier
version of this file called that a silent drop with no badge shown -- that was wrong,
and was caused by the audit sampling the badge only after it had been cleared. The
fixed harness shows 268 does report "camera refused".

It answers three questions the audit left open:
  1. What are the real option strings for 268 and 267, and is index 0 bulb?
  2. Does 268 report a different index because the body clamps the write, or
     because the webui mis-parses the reply?
  3. Does 267's write ever produce a `ret:` reply at all? The audit saw it time
     out to "not applied" rather than get refused, which means no reply arrived
     within EXPO_SET_TIMEOUT_MS. (Note: pending DOES clear, at ~33 s -- see the
     README. An earlier version of this file said "pending never cleared", which
     was wrong: the audit polled for 30 s and stopped 3 s before the delete.)
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

PORT = int(os.environ.get("GD_PORT", "4445"))
DEVICE = os.environ.get("DEVICE_URL", "http://192.168.0.1:8090")


def req(method, path, body=None, timeout=120):
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path),
                               data=data, method=method)
    r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as f:
            return json.loads(f.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return {"_error": "HTTP %d %s" % (e.code, e.read().decode()[:200])}
    except Exception as e:
        return {"_error": str(e)}


def js(sess, script, *a):
    r = req("POST", "/session/%s/execute/sync" % sess,
            {"script": script, "args": list(a)})
    if "_error" in r:
        print("   js error:", r["_error"][:160])
        return {"_error": r["_error"]}
    return r.get("value")


sess = req("POST", "/session",
           {"capabilities": {"alwaysMatch": {
               "moz:firefoxOptions": {"args": ["-headless"]}}}})["value"]["sessionId"]
req("POST", "/session/%s/url" % sess, {"url": DEVICE + "/"})
time.sleep(6)

print("=== raw option lists as the page parsed them ===")
slots = js(sess, """
  var out=[];
  document.querySelectorAll('.exposlot[data-get]').forEach(function(s){
    var g=s.getAttribute('data-get');
    var got=S.ops[g]; var po=null;
    if(got){ try{ po=parseOptions(got.args); }catch(e){ po={err:String(e)}; } }
    out.push({get:g,
              label:(s.querySelector('.expo-label')||{}).textContent,
              raw: got ? got.args : null,
              parsed: po,
              shown: (s.querySelector('select')||{}).value,
              disabled: !!(s.querySelector('select')||{}).disabled,
              badge: ((s.querySelector('.ctl-state'))||{}).textContent});
  });
  return out;""")
for s in (slots or []):
    print("\n-- opcode %s (%s)" % (s.get("get"), s.get("label")))
    print("   raw args :", str(s.get("raw"))[:300])
    print("   parsed   :", json.dumps(s.get("parsed"))[:300])
    print("   shown    :", s.get("shown"), "| disabled:", s.get("disabled"),
          "| badge:", repr(s.get("badge")))

print("\n\n=== EV (267): safe write, watch for a reply at all ===")
ev = js(sess, """
  var g='267'; var slot=document.querySelector('.exposlot[data-get="'+g+'"]');
  if(!slot) return {err:'no 267 slot'};
  var sel=slot.querySelector('select');
  var opts=[]; for(var i=0;i<sel.options.length;i++) opts.push(sel.options[i].text);
  var before=S.ops[g] ? S.ops[g].args : null;
  var orig=sel.value;
  var want = (orig==='0') ? '1' : '0';
  sel.value=want; sel.dispatchEvent(new Event('change',{bubbles:true}));
  return {opts:opts, before:before, orig:orig, want:want,
          pending:Object.keys(S.expoPending).length};""")
print("   opts:", json.dumps(ev.get("opts"))[:200])
print("   before:", str(ev.get("before"))[:160])
print("   asked index:", ev.get("want"), "| pending immediately after:",
      ev.get("pending"))

for i in range(25):
    time.sleep(1)
    st = js(sess, """
      var g='267'; var got=S.ops[g]; var po=null;
      if(got){ try{po=parseOptions(got.args);}catch(e){} }
      var slot=document.querySelector('.exposlot[data-get="'+g+'"]');
      return {pending:Object.keys(S.expoPending).length,
              raw: got?got.args:null, idx: po?po.index:null,
              shown:(slot.querySelector('select')||{}).value,
              badge:((slot.querySelector('.ctl-state'))||{}).textContent};""")
    print("   t+%02ds pending=%s idx=%s shown=%s badge=%r raw=%s" % (
        i + 1, st.get("pending"), st.get("idx"), st.get("shown"),
        st.get("badge"), str(st.get("raw"))[:90]))
    if st.get("pending") == 0:
        break

# restore
print("\n   restoring 267 to index", ev.get("orig"))
js(sess, """var g='267'; var sel=document.querySelector('.exposlot[data-get="'+g+'"] select');
   sel.value=arguments[0]; sel.dispatchEvent(new Event('change',{bubbles:true}));""",
   str(ev.get("orig")))
time.sleep(4)
print("   267 now:", js(sess, """var g='267'; var got=S.ops[g]; var po=null;
   if(got){try{po=parseOptions(got.args);}catch(e){}}
   return {idx:po?po.index:null,
           shown:document.querySelector('.exposlot[data-get="'+g+'"] select').value};"""))

print("\n\n=== SHUTTER (268): READ-ONLY, no write ===")
print("   (index 0 is the bulb end; #251 says an untimed-B exposure cannot be")
print("    cancelled physically, so this probe deliberately does not press it)")
sh = js(sess, """
  var g='268'; var slot=document.querySelector('.exposlot[data-get="'+g+'"]');
  if(!slot) return {err:'no 268 slot'};
  var sel=slot.querySelector('select'); var opts=[];
  for(var i=0;i<sel.options.length;i++) opts.push(sel.options[i].text);
  return {opts:opts, shown:sel.value, raw:S.ops[g]?S.ops[g].args:null,
          badge:((slot.querySelector('.ctl-state'))||{}).textContent};""")
print("   opts:", json.dumps(sh.get("opts"))[:400])
print("   shown index:", sh.get("shown"), "| badge:", repr(sh.get("badge")))
print("   raw:", str(sh.get("raw"))[:250])

req("DELETE", "/session/%s" % sess)
