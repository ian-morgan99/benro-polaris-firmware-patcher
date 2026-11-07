import base64, json, os, time, urllib.request, urllib.error
PORT=4445; DEVICE="http://192.168.0.1:8090"; OUT="/home/ian/astro-shots/camera-on"
os.makedirs(OUT, exist_ok=True)
def req(m,p,b=None,t=120):
    d=None if b is None else json.dumps(b).encode()
    r=urllib.request.Request("http://127.0.0.1:%d%s"%(PORT,p),data=d,method=m)
    r.add_header("Content-Type","application/json")
    try:
        with urllib.request.urlopen(r,timeout=t) as f: return json.loads(f.read().decode() or "{}")
    except urllib.error.HTTPError as e: return {"_error":"HTTP %d %s"%(e.code,e.read().decode()[:200])}
    except Exception as e: return {"_error":str(e)}
def js(s,scr,*a):
    r=req("POST","/session/%s/execute/sync"%s,{"script":scr,"args":list(a)})
    if "_error" in r: print("   js:",r["_error"][:120]); return None
    return r.get("value")
def shot(s,n):
    r=req("GET","/session/%s/screenshot"%s)
    if "value" in r:
        open(os.path.join(OUT,n+".png"),"wb").write(base64.b64decode(r["value"])); print("  shot",n)
    else: print("  FAIL",n,r.get("_error","")[:80])
s=req("POST","/session",{"capabilities":{"alwaysMatch":{"moz:firefoxOptions":{"args":["-headless"]}}}})["value"]["sessionId"]
req("POST","/session/%s/url"%s,{"url":DEVICE+"/"}); time.sleep(7)
shot(s,"01-stage-camera-on")
js(s,"[...document.querySelectorAll('*')].find(e=>/^control$/i.test((e.textContent||'').trim()))?.click()"); time.sleep(3)
shot(s,"02-control-camera-on")
js(s,"document.querySelector('.exposlot[data-get=\"268\"]')?.scrollIntoView({block:'center'})"); time.sleep(2)
shot(s,"03-exposure-controls")
js(s,"document.querySelector('#live')?.click() || [...document.querySelectorAll('button')].find(e=>/live/i.test(e.textContent))?.click()"); time.sleep(9)
shot(s,"04-liveview-camera-name")
print("camname:", js(s,"var c=document.getElementById('camname'); return c?{text:c.textContent,hidden:c.hasAttribute('hidden')}:null"))
js(s,"[...document.querySelectorAll('*')].find(e=>/^settings$/i.test((e.textContent||'').trim()))?.click()"); time.sleep(3)
shot(s,"05-settings-identity")
req("DELETE","/session/%s"%s); print("done")
