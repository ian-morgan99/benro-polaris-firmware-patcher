#!/bin/sh
# ============================================================================
#  Benro Polaris cellular modem unloader (Phase 3, optional)
#
#  Symmetric counterpart of cellular_load.sh.  Safe to run on units that
#  never loaded the modules: rmmod of an absent module just prints
#  "ERROR: Module X is not currently loaded" and exits non-zero, which
#  `set +e` above swallows.
#
#  Order is the STRICT reverse of the loader: qcserial first (it depends
#  on option + usbserial), then option, then cdc_acm, then usbserial
#  (which both option and cdc_acm depend on).
# ============================================================================
set +e

cd /app/komod/

# If qcserial is not loaded, this prints "is not currently loaded" and
# returns 1 -- which is fine.  The remaining rmmods are tried in turn.
for mod in qcserial.ko option.ko cdc_acm.ko usbserial.ko; do
  if [ -f "$mod" ]; then
    rmmod "$mod"
  fi
done

echo "[cellular] modules unloaded"
exit 0
