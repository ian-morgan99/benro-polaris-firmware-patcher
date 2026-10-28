#!/usr/bin/env python3
"""Dependency-free host prototype for the independent Polaris solver.

This is the Phase-2 star-list solver.  It deliberately uses a small, openly
generated catalogue (CSV: id,ra_deg,dec_deg) and a bounded hint.  It does not
read Astrometry.net indexes or SkySolver data.  The native implementation can
replace this executable once the algorithm and catalogue format are frozen.
"""
import argparse, itertools, json, math, struct, time

def vlen(a): return math.hypot(a[0], a[1])
def sep(a, b):
    d = math.sin(a[1])*math.sin(b[1]) + math.cos(a[1])*math.cos(b[1])*math.cos(a[0]-b[0])
    return math.acos(max(-1.0, min(1.0, d)))
def tangent(ra, dec, cra, cdec):
    dra = ra-cra; sd=math.sin(dec); cd=math.cos(dec); sc=math.sin(cdec); cc=math.cos(cdec)
    den = sd*sc + cd*cc*math.cos(dra)
    return (cd*math.sin(dra)/den, (sd*cc-cd*sc*math.cos(dra))/den)
def read_stars(path):
    out=[]
    for line in open(path, encoding='utf-8'):
        if not line.strip() or line.lstrip().startswith('#'): continue
        p=line.split();
        if len(p)>=2: out.append((float(p[0]), float(p[1]), float(p[2]) if len(p)>2 else 0.0))
    return sorted(out, key=lambda x:x[2], reverse=True)
def read_cat(path):
    # POLCAT01 is the independent catalogue format.  CSV remains supported
    # only as a host-side interchange format for fixtures and catalogue QA.
    with open(path, 'rb') as raw:
        head=raw.read(16)
    if head[:8] == b'POLCAT01':
        rec=struct.Struct('<Qddd'); version,count=struct.unpack_from('<II',head,8)
        if version != 1 or len(open(path,'rb').read()) != 16 + count*rec.size:
            raise ValueError('invalid independent catalogue')
        out=[]
        with open(path,'rb') as f:
            f.seek(16)
            for _ in range(count):
                sid,ra,dec,mag=rec.unpack(f.read(rec.size)); out.append((ra*math.pi/180,dec*math.pi/180,str(sid)))
        return out
    out=[]
    for line in open(path, encoding='utf-8'):
        if not line.strip() or line.lstrip().startswith('#'): continue
        p=line.replace(',', ' ').split()
        if len(p)>=3: out.append((float(p[-2])*math.pi/180, float(p[-1])*math.pi/180, p[0]))
    return out
def affine(src, dst):
    # dst = A*src + t; solve the six coefficients from three points.
    m=[]; y=[]
    for (x,z),(u,v) in zip(src,dst):
        m += [[x,z,0,0,1,0],[0,0,x,z,0,1]]; y += [u,v]
    for k in range(6):
        q=max(range(k,6), key=lambda i:abs(m[i][k]))
        if abs(m[q][k])<1e-12: return None
        m[k],m[q]=m[q],m[k]; y[k],y[q]=y[q],y[k]
        d=m[k][k]; m[k]=[x/d for x in m[k]]; y[k]/=d
        for i in range(6):
            if i==k: continue
            d=m[i][k]
            m[i]=[a-d*b for a,b in zip(m[i],m[k])]; y[i]-=d*y[k]
    return y
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--catalog', required=True); ap.add_argument('--stars', required=True)
    ap.add_argument('--width', type=float, required=True); ap.add_argument('--height', type=float, required=True)
    ap.add_argument('--ra', type=float); ap.add_argument('--dec', type=float)
    ap.add_argument('--radius', type=float, default=15); ap.add_argument('--focal-mm', type=float, default=0)
    ap.add_argument('--sensor-mm', type=float, default=36); ap.add_argument('--min-matches', type=int, default=4)
    ap.add_argument('--max-stars', type=int, default=24); ap.add_argument('--max-catalog', type=int, default=120); ap.add_argument('--scale-tol', type=float, default=.35); ap.add_argument('--residual-px', type=float, default=5)
    a=ap.parse_args(); t0=time.monotonic()
    if (a.ra is None) != (a.dec is None):
        print(json.dumps({'solved':False,'failure_reason':'incomplete_pointing_hint'})); return 2
    if a.ra is None:
        print(json.dumps({'solved':False,'failure_reason':'blind_search_index_required','focal_length_mm':a.focal_mm,'elapsed_ms':0})); return 6
    cra=a.ra*math.pi/180; cdec=a.dec*math.pi/180
    obs=read_stars(a.stars)[:a.max_stars]; cat=[]
    for ra,dec,i in read_cat(a.catalog):
        if sep((ra,dec),(cra,cdec)) <= a.radius*math.pi/180: cat.append((ra,dec,i))
    cat=sorted(cat, key=lambda x: x[2])[:a.max_catalog]
    if len(obs)<3: print(json.dumps({'solved':False,'failure_reason':'too_few_stars'})); return 3
    if len(cat)<3: print(json.dumps({'solved':False,'failure_reason':'no_index_coverage'})); return 3
    scale=206264.806*math.atan((a.sensor_mm/a.width)/a.focal_mm) if a.focal_mm>0 else 1.0
    # Coordinates are arcsec in a tangent plane.  Candidate triangles are
    # compared by side ratios, making the lookup independent of rotation/mirror.
    op=[((x-a.width/2)/scale,(y-a.height/2)/scale,f) for x,y,f in obs]
    cp=[(tangent(r,d,cra,cdec)[0]*180/math.pi*3600,tangent(r,d,cra,cdec)[1]*180/math.pi*3600,i) for r,d,i in cat]
    best=None
    for oi in itertools.combinations(range(min(len(op),15)),3):
      od=sorted([vlen((op[oi[0]][0]-op[oi[1]][0],op[oi[0]][1]-op[oi[1]][1])),vlen((op[oi[0]][0]-op[oi[2]][0],op[oi[0]][1]-op[oi[2]][1])),vlen((op[oi[1]][0]-op[oi[2]][0],op[oi[1]][1]-op[oi[2]][1]))])
      if od[0]<1e-9: continue
      for ci in itertools.combinations(range(len(cp)),3):
       cd=sorted([vlen((cp[ci[0]][0]-cp[ci[1]][0],cp[ci[0]][1]-cp[ci[1]][1])),vlen((cp[ci[0]][0]-cp[ci[2]][0],cp[ci[0]][1]-cp[ci[2]][1])),vlen((cp[ci[1]][0]-cp[ci[2]][0],cp[ci[1]][1]-cp[ci[2]][1]))])
       if cd[0]<1 or max(abs(od[j]/od[0]-cd[j]/cd[0]) for j in range(3))>.08: continue
       for perm in itertools.permutations(ci):
        ab=affine([(cp[k][0],cp[k][1]) for k in perm],[(op[k][0],op[k][1]) for k in oi])
        if not ab: continue
        A,B,C,D,tx,ty=ab; pred=[]
        candidate_scale=scale/math.sqrt(A*A+C*C)
        if a.focal_mm>0 and not (scale*(1-a.scale_tol) <= candidate_scale <= scale*(1+a.scale_tol)): continue
        for x,y,f in op:
          pred.append(min(math.hypot(A*u+B*v+tx-x,C*u+D*v+ty-y) for u,v,_ in cp))
        matches=sum(e<=a.residual_px/scale for e in pred)
        rms=math.sqrt(sum(e*e for e in pred if e<=a.residual_px/scale)/max(1,matches))
        if best is None or (matches,-rms)>(best[0],-best[1]): best=(matches,rms,ab)
    if not best or best[0]<a.min_matches:
        print(json.dumps({'solved':False,'failure_reason':'no_verified_candidate','nfield':len(obs),'ncatalog':len(cat),'elapsed_ms':round((time.monotonic()-t0)*1000,2)})); return 4
    A,B,C,D,tx,ty=best[2]; rot=math.degrees(math.atan2(C,A)); pix=scale/math.sqrt(A*A+C*C)
    if a.focal_mm>0 and not (scale*(1-a.scale_tol) <= pix <= scale*(1+a.scale_tol)):
        print(json.dumps({'solved':False,'failure_reason':'scale_out_of_bounds','estimated_scale_arcsec_per_px':pix,'expected_scale_arcsec_per_px':scale,'elapsed_ms':round((time.monotonic()-t0)*1000,2)})); return 5
    print(json.dumps({'solved':True,'ra_deg':a.ra,'dec_deg':a.dec,'scale_arcsec_per_px':pix,'rotation_deg':rot,'parity':-1 if A*D-B*C<0 else 1,'matched_count':best[0],'rms_px':best[1]*scale,'catalog':'independent-csv','elapsed_ms':round((time.monotonic()-t0)*1000,2)}))
if __name__=='__main__': raise SystemExit(main() or 0)
