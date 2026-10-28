#!/usr/bin/env python3
import argparse, csv, hashlib, json, math, struct
from pathlib import Path
REC=struct.Struct('<Qddd'); MAGIC=b'POLCAT01'
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('input'); ap.add_argument('outdir'); ap.add_argument('--manifest',required=True); ap.add_argument('--ra-bin',type=float,default=10); ap.add_argument('--dec-bin',type=float,default=10); ap.add_argument('--max-mag',type=float,default=10); a=ap.parse_args()
    tiles={}; seen=set()
    with open(a.input,newline='',encoding='utf-8') as f:
        for r in csv.DictReader(f):
            try:
                sid=int(r['source_id']); ra=float(r['ra_deg'] if 'ra_deg' in r else r['ra']); dec=float(r['dec_deg'] if 'dec_deg' in r else r['dec']); mag=float(r.get('phot_g_mean_mag','nan'))
            except (KeyError,ValueError,TypeError): continue
            if sid in seen or not (0<=ra<360 and -90<=dec<=90) or (math.isfinite(mag) and mag>a.max_mag): continue
            seen.add(sid); key=(int(ra//a.ra_bin)%int(360/a.ra_bin),int((dec+90)//a.dec_bin)); tiles.setdefault(key,[]).append((sid,ra,dec,mag if math.isfinite(mag) else 99.0))
    out=Path(a.outdir); out.mkdir(parents=True,exist_ok=True); entries=[]
    for (ri,di),rows in sorted(tiles.items()):
        rows.sort(); p=out/f'tile-{ri:03d}-{di:03d}.pcat'
        with p.open('wb') as f:
            f.write(MAGIC+struct.pack('<II',1,len(rows)))
            for row in rows: f.write(REC.pack(*row))
        entries.append({'tile':p.stem,'ra_min':ri*a.ra_bin,'ra_max':(ri+1)*a.ra_bin,'dec_min':di*a.dec_bin-90,'dec_max':(di+1)*a.dec_bin-90,'records':len(rows),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    manifest={'format':'polaris-independent-tile-set-1','catalogue':'Gaia DR3',
              'source':'ESA Gaia Archive TAP / gaiadr3.gaia_source',
              'release':'DR3','epoch':'2016.0',
              'ra_bin_deg':a.ra_bin,'dec_bin_deg':a.dec_bin,
              'selection':f'phot_g_mean_mag <= {a.max_mag}',
              'licence_notice':'ESA Gaia data acknowledgement required; see https://www.cosmos.esa.int/web/gaia/data-access',
              'tile_count':len(entries),'record_count':sum(e['records'] for e in entries),'tiles':entries}
    Path(a.manifest).write_text(json.dumps(manifest,indent=2)+'\n'); print(json.dumps({'tile_count':len(entries),'record_count':manifest['record_count']})); return 0
if __name__=='__main__': raise SystemExit(main())
