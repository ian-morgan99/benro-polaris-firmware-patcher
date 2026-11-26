#!/usr/bin/env python3
"""Read EXIF from a delivered SP_*.jpg to learn what exposure the camera actually used.

Why: every timed capture takes ~24 s to reach state:4 regardless of the requested shutter,
and pgphoto's own file read is 1 ms. If the delivered image reports a long exposure, the
shutter really is being held open and the time is the camera's; if it reports the requested
short value, the delay is entirely on our side of the wire.
"""
import sys
from PIL import Image
from PIL.ExifTags import TAGS

WANT = ("ExposureTime", "ShutterSpeedValue", "FNumber", "ExposureProgram",
        "DateTimeOriginal", "ISOSpeedRatings", "Make", "Model", "MeteringMode",
        "WhiteBalance", "Flash")

for path in sys.argv[1:]:
    print(f"== {path}")
    im = Image.open(path)
    ex = im._getexif() or {}
    named = {TAGS.get(k, k): v for k, v in ex.items()}
    if not named:
        print("   no EXIF")
        continue
    for k in WANT:
        if k in named:
            print(f"   {k:20} {named[k]}")
