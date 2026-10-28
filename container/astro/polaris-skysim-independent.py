#!/usr/bin/env python3
"""Render a deterministic JPEG from a POLCAT01 catalogue."""
import argparse, math, random, struct
from PIL import Image, ImageFilter

REC=struct.Struct('<Qddd')
def catalogue(path):
    with open(path,'rb') as f:
        if f.read(8)!=b'POLCAT01': raise ValueError('not POLCAT01')
        version,count=struct.unpack('<II',f.read(8))
        if version!=1: raise ValueError('unsupported catalogue')
        return [REC.unpack(f.read(REC.size)) for _ in range(count)]
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--catalog',required=True); ap.add_argument('--ra',type=float,required=True); ap.add_argument('--dec',type=float,required=True); ap.add_argument('--roll',type=float,default=0); ap.add_argument('--focal-mm',type=float,default=100); ap.add_argument('--sensor-mm',type=float,default=36); ap.add_argument('--width',type=int,default=1920); ap.add_argument('--height',type=int,default=1280); ap.add_argument('--background',type=int,default=12); ap.add_argument('--noise',type=float,default=1); ap.add_argument('--flux',type=float,default=230); ap.add_argument('--fwhm',type=float,default=3); ap.add_argument('--seed',type=int,default=1); ap.add_argument('--out',required=True); a=ap.parse_args()
    rng=random.Random(a.seed); img=Image.new('L',(a.width,a.height),max(0,min(255,a.background))); px=img.load(); cra=math.radians(a.ra); cdec=math.radians(a.dec); roll=math.radians(a.roll); scale=206264.806*math.atan((a.sensor_mm/a.width)/a.focal_mm); drawn=0
    for sid,ra0,dec0,mag in catalogue(a.catalog):
        ra=math.radians(ra0); dec=math.radians(dec0); dra=ra-cra; den=math.sin(dec)*math.sin(cdec)+math.cos(dec)*math.cos(cdec)*math.cos(dra)
        if den<=0: continue
        tx=math.cos(dec)*math.sin(dra)/den; ty=(math.sin(dec)*math.cos(cdec)-math.cos(dec)*math.sin(cdec)*math.cos(dra))/den
        x=(tx*math.cos(roll)+ty*math.sin(roll))*180/math.pi*3600/scale+a.width/2; y=(-tx*math.sin(roll)+ty*math.cos(roll))*180/math.pi*3600/scale+a.height/2
        if x<2 or y<2 or x>=a.width-2 or y>=a.height-2: continue
        amp=a.flux*max(.15,min(1.0,10**(-.4*(mag-5)))); sig=a.fwhm/2.355; radius=max(2,int(sig*4))
        for yy in range(max(0,int(y)-radius),min(a.height,int(y)+radius+1)):
            for xx in range(max(0,int(x)-radius),min(a.width,int(x)+radius+1)):
                q=((xx-x)**2+(yy-y)**2)/(2*sig*sig); px[xx,yy]=min(255,int(px[xx,yy]+amp*math.exp(-q)))
        drawn+=1
    if a.noise:
        for y in range(a.height):
            for x in range(a.width): px[x,y]=max(0,min(255,int(px[x,y]+rng.gauss(0,a.noise))))
    img.save(a.out,quality=92); print('{"stars":%d,"scale_arcsec_per_px":%.6f,"out":"%s"}'%(drawn,scale,a.out)); return 0
if __name__=='__main__': raise SystemExit(main())
