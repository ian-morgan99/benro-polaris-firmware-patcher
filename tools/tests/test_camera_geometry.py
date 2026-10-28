import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_k3_profile_is_apsc():
    p=subprocess.run([sys.executable,str(ROOT/'resolve_camera_geometry.py'),'--model','Pentax K-3 III','--focal-mm','400'],capture_output=True,text=True,check=True)
    o=json.loads(p.stdout); assert o['sensor_class']=='APS-C'; assert o['sensor_width_mm']==23.3; assert o['sensor_source']=='camera-model-profile'
def test_override_wins():
    p=subprocess.run([sys.executable,str(ROOT/'resolve_camera_geometry.py'),'--model','Pentax K-3 III','--sensor-mm','36'],capture_output=True,text=True,check=True)
    o=json.loads(p.stdout); assert o['sensor_width_mm']==36; assert o['sensor_source']=='override'
def test_unknown_camera_uses_generic_fallback():
    p=subprocess.run([sys.executable,str(ROOT/'resolve_camera_geometry.py'),'--model','Some Other Camera'],capture_output=True,text=True,check=True)
    o=json.loads(p.stdout); assert o['sensor_width_mm']==36.0; assert o['sensor_source']=='generic-default'
