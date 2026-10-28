#!/usr/bin/env python3
import argparse, json
from pathlib import Path
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--profiles',default='container/astro/camera-profiles.json'); ap.add_argument('--model'); ap.add_argument('--sensor-mm',type=float); ap.add_argument('--focal-mm',type=float); a=ap.parse_args()
    profiles=json.loads(Path(a.profiles).read_text())
    profiles=profiles.get('profiles',profiles)
    if a.sensor_mm:
        sensor=a.sensor_mm; source='override'; cls='configured'
    elif a.model in profiles:
        p=profiles[a.model]; sensor=p['sensor_width_mm']; source='camera-model-profile'; cls=p['sensor_class']
    else:
        default=json.loads(Path(a.profiles).read_text()).get('default',{'sensor_width_mm':36.0,'sensor_class':'generic-assumption'})
        sensor=default['sensor_width_mm']; source='generic-default'; cls=default['sensor_class']
    out={'sensor_width_mm':sensor,'sensor_class':cls,'sensor_source':source}
    if a.focal_mm:
        out['focal_mm']=a.focal_mm; out['horizontal_fov_deg']=2*__import__('math').degrees(__import__('math').atan(sensor/(2*a.focal_mm)))
    print(json.dumps(out)); return 0
if __name__=='__main__': raise SystemExit(main())
