# What a successful capture must prove

A capture is not successful merely because an image file appeared.

For stability qualification, success means:

1. shutter request accepted exactly once;
2. camera remains in legitimate operation until terminal camera-side work;
3. no unsafe foreign command corrupts ownership;
4. actual candidates are discovered/classified;
5. intended tether object(s) transfer successfully;
6. all exposure-owned candidate/session state is reconciled according to data-safety policy;
7. camera/session returns to READY;
8. a subsequent shutter request succeeds without reconnect/reset.

This definition is particularly important for DNG+JPEG and Pixel Shift, where physical exposures, files and transfer candidates may not have the same count.
