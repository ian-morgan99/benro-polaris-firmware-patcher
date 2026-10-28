#!/usr/bin/env python3
"""Bounded hinted search wrapper for the independent solver prototype."""
import argparse, json, math, subprocess, sys
from pathlib import Path
def corkscrew(ra,dec,step=5,turns=5):
    yield (ra,dec)
    for ring in range(1,turns+1):
        for n in range(8*ring):
            ang=2*math.pi*n/(8*ring); yield ((ra+step*ring*math.cos(ang))%360,max(-89.9,min(89.9,dec+step*ring*math.sin(ang))))
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--catalog-dir',required=True); ap.add_argument('--manifest',required=True); ap.add_argument('--stars',required=True); ap.add_argument('--width',type=int,required=True); ap.add_argument('--height',type=int,required=True); ap.add_argument('--focal-mm',type=float,required=True); ap.add_argument('--sensor-mm',type=float,default=36); ap.add_argument('--ra',type=float); ap.add_argument('--dec',type=float); ap.add_argument('--step-deg',type=float,default=5); ap.add_argument('--rings',type=int,default=5); ap.add_argument('--attempts',type=int,default=40); ap.add_argument('--max-stars',type=int,default=12); ap.add_argument('--max-catalog',type=int,default=60); ap.add_argument('--solver-timeout',type=int,default=10); ap.add_argument('--solver',default=str(Path(__file__).with_name('polaris-solve-independent.py'))); a=ap.parse_args()
    if (a.ra is None)!=(a.dec is None): print(json.dumps({'solved':False,'failure_reason':'incomplete_pointing_hint'})); return 2
    manifest=json.loads(Path(a.manifest).read_text()); starts=[]
    if a.ra is not None: starts=list(corkscrew(a.ra,a.dec,a.step_deg,a.rings))
    else:
        starts=[((e['ra_min']+e['ra_max'])/2,(e['dec_min']+e['dec_max'])/2) for e in manifest['tiles']]
    tried=0
    for ra,dec in starts:
        if tried>=a.attempts: break
        for e in manifest['tiles']:
            if not (e['ra_min']-15<=ra<=e['ra_max']+15 and e['dec_min']-15<=dec<=e['dec_max']+15): continue
            cmd=[sys.executable,a.solver,'--catalog',str(Path(a.catalog_dir)/(e['tile']+'.pcat')),'--stars',a.stars,'--width',str(a.width),'--height',str(a.height),'--focal-mm',str(a.focal_mm),'--sensor-mm',str(a.sensor_mm),'--max-stars',str(a.max_stars),'--max-catalog',str(a.max_catalog),'--ra',str(ra),'--dec',str(dec),'--radius','15']
            try: p=subprocess.run(cmd,capture_output=True,text=True,timeout=a.solver_timeout)
            except subprocess.TimeoutExpired: tried+=1; continue
            tried+=1
            try: result=json.loads(p.stdout.strip().splitlines()[-1])
            except (ValueError,IndexError): continue
            if result.get('solved') and result.get('matched_count',0)>=4:
                result['search_attempts']=tried; result['search_mode']='hinted-corkscrew' if a.ra is not None else 'all-sky-tile-centres'; print(json.dumps(result)); return 0
    print(json.dumps({'solved':False,'failure_reason':'search_exhausted','attempts':tried,'search_mode':'hinted-corkscrew' if a.ra is not None else 'all-sky-tile-centres'})); return 7
if __name__=='__main__': raise SystemExit(main())
