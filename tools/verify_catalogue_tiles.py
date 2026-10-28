#!/usr/bin/env python3
import argparse,hashlib,json,struct
from pathlib import Path
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('directory'); ap.add_argument('manifest'); a=ap.parse_args(); d=Path(a.directory); m=json.loads(Path(a.manifest).read_text()); total=0
    for e in m['tiles']:
        p=d/(e['tile']+'.pcat'); b=p.read_bytes()
        if b[:8]!=b'POLCAT01' or hashlib.sha256(b).hexdigest()!=e['sha256']: raise SystemExit('tile verification failed: '+str(p))
        n=struct.unpack_from('<I',b,12)[0]
        if n!=e['records'] or len(b)!=16+n*32: raise SystemExit('tile length mismatch: '+str(p))
        total+=n
    if total!=m['record_count'] or len(m['tiles'])!=m['tile_count']: raise SystemExit('manifest totals mismatch')
    print(json.dumps({'valid':True,'tile_count':len(m['tiles']),'record_count':total})); return 0
if __name__=='__main__': raise SystemExit(main())
