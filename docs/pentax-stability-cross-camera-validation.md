# Cross-camera validation

K-3 III is the first hardware characterisation target because it is central to the current stability evidence.

Do not automatically generalise measured K-3 III Pixel Shift, NR, candidate or session semantics to K-1 II.

After a K-3 III causal fix/regression passes, run a reduced equivalent matrix on K-1 II:

- normal JPEG and DNG+JPEG consecutive captures;
- relevant long-exposure NR cases;
- Pixel Shift if supported/configured;
- timeout boundary cases relevant to the fixed code path;
- preview/concurrency case that reproduced on K-3 III;
- session reset/reconnect proof.

Record differences as model-specific behaviour rather than forcing one body's semantics onto the other.
