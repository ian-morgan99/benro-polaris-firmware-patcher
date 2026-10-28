from pathlib import Path
import json, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
def test_focal_only_requires_blind_index_not_pointing_hint():
    p=subprocess.run([sys.executable,str(ROOT/'polaris-solve-independent.py'),
      '--catalog',str(ROOT/'tests/catalog-fixture.csv'),'--stars',str(ROOT/'tests/stars-fixture.txt'),
      '--width','1000','--height','800','--focal-mm','400'],capture_output=True,text=True)
    assert p.returncode != 0
    assert json.loads(p.stdout)['failure_reason']=='blind_search_index_required'
