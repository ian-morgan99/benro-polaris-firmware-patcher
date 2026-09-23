# Pixel shift RAW+JPEG candidate experiment

The K-3 III reported `photoFormat:2` (RAW+JPEG), USB `25fb:0189`, state 1.
Exactly one code-264 capture request was sent with preview off. The user heard
four physical shutter actuations, consistent with pixel-shift sub-exposures.
The operation completed in about seven seconds and published one JPEG event:
`SP_0072.jpg`, 413577 bytes. No additional file event arrived during the next
60 seconds.

A subsequent request was used only as the installed fail-closed recovery probe;
it did not initiate another exposure. It reported successful 576-byte conditions,
idle activity (+104=0), and one pending candidate (+32=1, +36=1). Therefore
four physical sub-exposures do not imply four published files here. Current
evidence is consistent with a composite pixel-shift JPEG already published plus
one delayed composite RAW candidate, i.e. two output candidates total. The
remaining candidate must be transferred and its filename/type observed before
that count is treated as proven.
