# K-01 direct-PC harness gate — 2026-11-22 ~22:50 GMT

Run WITHOUT the Polaris mount (AP not broadcasting). Exercises the real fix on
real hardware through the harness, so it is accurate, not simulated.

Harness test: benro-polaris-test-harness tests/test_k01_pc_transport.py
  (added at harness HEAD 3ad4197 "Gate K-01 MSC discovery and reads on an
   opt-in physical PC session"). Opt-in via POLARIS_K01_DRIVER_PREFIX.

Driver under test: built from the EXACT v115 pin, not a stale prefix.
  source /home/ian/polaris-v101/out/.libgphoto2-v115 @ 0f2f34e0004011136fa75bf43e215acc0c8b9fdb
  contains dd676defb (K-01 25fb:0130 MSC/06/50 -> usbscsi) and ed958942f (PR#169).
  host x86 meson build, camlibs=ptp2,pentax iolibs=libusb1,usbscsi,ptpip,disk
  prefix /home/ian/polaris-v101/out/v115-host-driver-prefix
  pentax.so   sha256 771b1097506f33329f594fd104d3f6089e4121dbb8beefebe9e321919d097175
  usbscsi.so  sha256 5107b166f263e86eb8cc5c82d9bdc965adcbb7d5d97e13bb9da7e411c1f0d5cd
  Sonames match /usr/bin/gphoto2 (libgphoto2.so.6, libgphoto2_port.so.12), so
  LD_LIBRARY_PATH=prefix/lib makes the built core load, not system libs.

Hardware precondition met: sg1 vendor=PENTAX model=DSC_K-01 (K-01 in MSC mode).

Result: 1 passed. The test asserts auto-detect lists "Pentax K01" on
usbscsi:/dev/sg1 AND does NOT list it on usb:BBB,DDD, then reads shutter/aperture/
ISO over SCSI and confirms both pentax.so and usbscsi.so appear in the debug trace.

## What this does NOT cover
- K-1 II native shutter admission on v115. The harness fixture
  test_v114_shutter_admission.py is hash-pinned to the v114 install binary
  (assert binary_sha256 == V114_INSTALL_SHA256) and cannot run against v115 by
  design. v115's admission change is covered offline by the patcher gate's
  test_stage2_native_admission.sh (green). Physical K-1 II shutter write/restore
  still requires the mount.
