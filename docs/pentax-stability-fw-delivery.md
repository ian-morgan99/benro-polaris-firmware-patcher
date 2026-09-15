# Firmware delivery requirement for Pentax stability fixes

Diagnostic instrumentation may use the existing development/test mechanisms appropriate to the connected Polaris environment, but any product/runtime fix must end in the repository's reproducible firmware/FwPkt delivery path.

Do not close a stability defect because a direct SSH mutation happened to work on one device. The regression evidence must identify the exact source/patcher/libgphoto2 provenance that produces the tested firmware artifact.
