#!/usr/bin/env python3
"""Build the small, versioned Polaris independent catalogue.

Input CSV columns: source_id,ra_deg,dec_deg[,phot_g_mean_mag].
Output is a fixed little-endian binary file plus a JSON provenance manifest.
The catalogue is intentionally position/brightness only; no Astrometry.net or
SkySolver index format is accepted.
"""
import argparse, csv, hashlib, json, math, struct, sys
from pathlib import Path

MAGIC=b'POLCAT01'; VERSION=1; REC=struct.Struct('<Qddd')
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('input'); ap.add_argument('output');
    ap.add_argument('--manifest', required=True); ap.add_argument('--max-mag',type=float,default=10.0)
    ap.add_argument('--source',default='Gaia DR3'); ap.add_argument('--release',default='DR3')
    ap.add_argument('--epoch',default='2016.0')
    ap.add_argument('--licence-notice',default='Gaia acknowledgement required; see project provenance.')
    ap.add_argument('--builder',default='uncommitted'); a=ap.parse_args()
    rows=[]; seen=set()
    with open(a.input, newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            try:
                sid=int(r['source_id']); ra=float(r['ra_deg'] if 'ra_deg' in r else r['ra']); dec=float(r['dec_deg'] if 'dec_deg' in r else r['dec'])
                mag=float(r.get('phot_g_mean_mag','nan'))
            except (KeyError,TypeError,ValueError): continue
            if sid in seen or not (0<=ra<360 and -90<=dec<=90): continue
            if math.isfinite(mag) and mag>a.max_mag: continue
            seen.add(sid); rows.append((sid,ra,dec,mag if math.isfinite(mag) else 99.0))
    rows.sort(key=lambda x:x[0]); out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('wb') as f:
        f.write(MAGIC+struct.pack('<II',VERSION,len(rows)))
        for sid,ra,dec,mag in rows: f.write(REC.pack(sid,ra,dec,mag))
    digest=hashlib.sha256(out.read_bytes()).hexdigest()
    manifest={'format':'polaris-independent-catalogue-1','source':a.source,'release':a.release,
      'epoch':a.epoch,'selection':f'phot_g_mean_mag <= {a.max_mag}', 'record_count':len(rows),
      'record_size':REC.size,'sha256':digest,'builder':a.builder,
      'licence_notice':a.licence_notice}
    Path(a.manifest).write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest)); return 0
if __name__=='__main__': raise SystemExit(main())
