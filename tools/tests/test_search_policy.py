import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_search_without_hint_fails_classified_when_fixture_has_no_tiles(tmp_path):
    m=tmp_path/'m.json'; m.write_text(json.dumps({'tiles':[],'tile_count':0,'record_count':0}))
    p=subprocess.run([sys.executable,str(ROOT.parent/'container/astro/polaris-solve-independent-search.py'),'--catalog-dir',str(tmp_path),'--manifest',str(m),'--stars','/dev/null','--width','10','--height','10','--focal-mm','400'],capture_output=True,text=True)
    assert p.returncode==7; assert json.loads(p.stdout)['failure_reason']=='search_exhausted'
