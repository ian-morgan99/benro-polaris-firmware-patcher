# K-1 II preview corruption validation

Date: 2026-09-15
Camera: Pentax K-1 Mark II, USB `25fb:0183`

## Result

A preview-on capture produced valid camera output (`SP_0034.jpg` and `SP_0035.jpg`)
with Polaris runtime healthy. The raw 8080 MJPEG stream was then captured directly,
without using Benro Connect:

- Stream bytes: 30,979
- JPEG SOI: present at byte 409
- JPEG EOI: present at byte 30,953
- Extracted frame: valid JPEG, `720x480`, 3 components
- Polaris log: preview stage `0x2001`, frame sizes around 30 KB

Therefore the K-1 II capture path and Polaris preview server are producing valid data.
The reported corrupted preview is downstream in the Benro Connect client display,
transport handling, or decode/render path. This is consistent with the older iPad
being overloaded while the newer iPhone remains usable.

## A/B conclusion

Preview disabled: captures complete normally.
Preview enabled: raw server frame remains valid, but the client display is corrupted.
The next client-side experiment is to compare the same valid 8080 stream on iPad and
iPhone, without changing the camera or Polaris runtime.
