#!/usr/bin/env python3
import argparse, hashlib, json, struct, sys
from pathlib import Path
MAGIC=b'POLCAT01'; REC=struct.Struct('<Qddd')
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('catalogue'); ap.add_argument('manifest'); a=ap.parse_args()
    data=Path(a.catalogue).read_bytes(); m=json.loads(Path(a.manifest).read_text())
    if data[:8]!=MAGIC: raise SystemExit('bad catalogue magic')
    version,count=struct.unpack_from('<II',data,8)
    if version!=1: raise SystemExit('unsupported catalogue version')
    if len(data)!=16+count*REC.size: raise SystemExit('catalogue length mismatch')
    if count!=m['record_count'] or hashlib.sha256(data).hexdigest()!=m['sha256']:
        raise SystemExit('manifest does not match catalogue')
    print(json.dumps({'valid':True,'version':version,'records':count,'sha256':m['sha256']})); return 0
if __name__=='__main__': raise SystemExit(main())
