import csv,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_tile_build_and_verify(tmp_path):
    src=tmp_path/'gaia.csv'; out=tmp_path/'tiles'; man=tmp_path/'tiles.json'
    with src.open('w',newline='') as f:
        w=csv.writer(f); w.writerow(['source_id','ra_deg','dec_deg','phot_g_mean_mag']); w.writerow([1,1,2,5]); w.writerow([2,21,12,6])
    subprocess.run([sys.executable,str(ROOT/'build_catalogue_tiles.py'),str(src),str(out),'--manifest',str(man)],check=True)
    p=subprocess.run([sys.executable,str(ROOT/'verify_catalogue_tiles.py'),str(out),str(man)],capture_output=True,text=True,check=True)
    assert json.loads(p.stdout)['record_count']==2
