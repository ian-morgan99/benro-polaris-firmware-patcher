# Pentax stability definition of done

A stability family is done only when all are true:

- the initiating trigger is reproducible or bounded statistically;
- the first incorrect transition is identified;
- the owning layer/source is identified with evidence;
- the fix acts at or before that transition where practical;
- candidate/user-data semantics remain safe;
- legitimate long operations remain valid regardless of fixed legacy timeout constants;
- consecutive next capture proves terminal READY;
- a regression test reproduces the pre-fix failure and passes post-fix;
- recovery still handles genuine failures without requiring normal Polaris reboot;
- lower-layer fix is requalified through OpenPolaris/Benro-facing E2E paths as appropriate.

"It recovers now" is not sufficient definition of done.
