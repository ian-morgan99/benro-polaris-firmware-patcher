# Minimum first physical-camera run

Before running the full campaign, get one clean instrumented baseline and one high-value stressor.

1. K-3 III, preview OFF, no OpenPolaris/Benro Connect consumer.
2. Record exact patcher/libgphoto2 SHAs and camera settings.
3. Normal DNG+JPEG, 1 s, two consecutive captures.
4. Enumerate candidate descriptors and prove terminal reconciliation before second shutter.
5. Repeat five times.
6. Then run the same case with zero deliberate inter-shot delay.
7. If failure occurs, stop broad testing and reduce that failure to the smallest E4/E5 reproducer first.
8. If clean, proceed to the 95/99/100/101/105 s E1 sweep.

This gives the quickest path to useful causal evidence without immediately spending hours on long exposures.
