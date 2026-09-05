#!/usr/bin/env python3
"""
Build the full Benro Polaris diagnostic test-card matrix.

Each test zip is constructed from either the stock reference (verified MD5s
known) or the 2026-08-30 padded-appfs build, and the only difference from
the baseline is the *one* thing that test card is meant to probe.

Run:  python3 build_test_cards.py
"""

import hashlib
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
STOCK_ZIP   = Path("/home/ian/Downloads/FwPkt.zip")
PADDED_ZIP  = Path("/home/ian/Documents/VSCodeProjects/BenroPolarisPatcher/builds/2026-08-30-padded-appfs/FwPkt.zip")
SMB_DEST    = Path("/run/user/1000/gvfs/smb-share:server=morganbackup.local,share=home/Projects/Pentax/BenroPolaris/diagnostics/2026-08-30_test-cards")
LOCAL_OUT   = Path("/tmp/test-cards")
TODAY       = "2026-08-30"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def md5_of(p: Path) -> str:
    h = hashlib.md5()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def size_of(p: Path) -> int:
    return p.stat().st_size

def parse_firmwareinfo(text: str) -> dict:
    """Parse the 'KEY size:N;KEY MD5:HASH;' lines into a dict."""
    out = {}
    for m in re.finditer(r"(\w+)\s+size:(\d+);(\w+)\s+MD5:([0-9a-f]{32});", text):
        label, size, _label2, md5 = m.groups()
        out[label] = {"size": int(size), "md5": md5}
    if len(out) != 6:
        raise ValueError(f"expected 6 entries, got {len(out)}: {out}")
    return out

def serialise_firmwareinfo(d: dict) -> str:
    """Re-emit a firmwareInfo string in the same order as the on-device script."""
    order = ["config", "uImage", "rootfs", "appfs", "polaris403", "polaris413"]
    return "".join(f"{k} size:{d[k]['size']};{k} MD5:{d[k]['md5']};" for k in order)

def extract(src: Path, dest: Path):
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    with zipfile.ZipFile(src) as zf:
        zf.extractall(dest)

def repack(staging_dir: Path, out_zip: Path, label: str):
    """Zip staging_dir/FwPkt/ as out_zip."""
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    if out_zip.exists():
        out_zip.unlink()
    fwpkt = staging_dir / "FwPkt"
    if not fwpkt.is_dir():
        raise ValueError(f"{fwpkt} missing")
    subprocess.run(
        ["zip", "-qr", "-X", str(out_zip), "FwPkt"],
        cwd=staging_dir, check=True,
    )
    sz = size_of(out_zip)
    md5 = md5_of(out_zip)
    print(f"  [{label}] built {out_zip.name}  size={sz:,}  md5={md5}")

# ---------------------------------------------------------------------------
# Test-card builders
# Each returns a label and an output path.
# A "test card" is a complete FwPkt.zip ready to copy to SD.
# ---------------------------------------------------------------------------

def card_A_stock_baseline():
    """STOCK_ORIGINAL — should succeed, proves device is functional + SD read works."""
    out = LOCAL_OUT / f"FwPkt_TEST_A_STOCK_BASELINE_{TODAY}.zip"
    shutil.copyfile(STOCK_ZIP, out)
    return "A: STOCK baseline (revert to known-good)", out

def card_B_negctrl_bad_appfs_md5():
    """NEG_CTRL_BAD_APPFS_MD5 — only appfs MD5 flipped to 0000..."""
    stage = LOCAL_OUT / "_stage_B"
    extract(STOCK_ZIP, stage)
    fi_path = stage / "FwPkt" / "firmwareInfo"
    d = parse_firmwareinfo(fi_path.read_text())
    d["appfs"]["md5"] = "0" * 32
    fi_path.write_text(serialise_firmwareinfo(d))
    out = LOCAL_OUT / f"FwPkt_TEST_B_NEGCTRL_BAD_APPFS_MD5_{TODAY}.zip"
    repack(stage, out, "B")
    return "B: NEG CTRL — only appfs MD5 forced to 0000..", out

def card_C_negctrl_bad_config_md5():
    """NEG_CTRL_BAD_CONFIG_MD5 — only config MD5 flipped."""
    stage = LOCAL_OUT / "_stage_C"
    extract(STOCK_ZIP, stage)
    fi_path = stage / "FwPkt" / "firmwareInfo"
    d = parse_firmwareinfo(fi_path.read_text())
    d["config"]["md5"] = "0" * 32
    fi_path.write_text(serialise_firmwareinfo(d))
    out = LOCAL_OUT / f"FwPkt_TEST_C_NEGCTRL_BAD_CONFIG_MD5_{TODAY}.zip"
    repack(stage, out, "C")
    return "C: NEG CTRL — only config MD5 forced to 0000..", out

def card_D_negctrl_truncated_zip():
    """NEG_CTRL_TRUNCATED_ZIP — stock zip truncated at ~10 MB.
       If on-device unzip errors out, MD5 check never runs.
       If the disassembly is right: silent reboot."""
    out = LOCAL_OUT / f"FwPkt_TEST_D_NEGCTRL_TRUNCATED_10MB_{TODAY}.zip"
    with open(STOCK_ZIP, "rb") as fin, open(out, "wb") as fout:
        fout.write(fin.read(10 * 1024 * 1024))
    return "D: NEG CTRL — zip truncated at 10 MB (unzip should fail)", out

def card_E_lowercase_zipname():
    """RENAME FwPkt.zip to fwPkt.zip — tests case-sensitivity of FwPkt.zip lookup."""
    stage = LOCAL_OUT / "_stage_E"
    extract(STOCK_ZIP, stage)
    out = LOCAL_OUT / f"fwPkt_TEST_E_LOWERCASE_NAME_{TODAY}.zip"  # lowercase 'w'
    repack(stage, out, "E")
    return "E: NEG CTRL — file renamed to fwPkt.zip (case probe)", out

def card_F_renamed_firmwareinfo():
    """Rename firmwareInfo -> firmware_info inside zip. Probes fopen path."""
    stage = LOCAL_OUT / "_stage_F"
    extract(STOCK_ZIP, stage)
    fwpkt = stage / "FwPkt"
    (fwpkt / "firmwareInfo").rename(fwpkt / "firmware_info")
    out = LOCAL_OUT / f"FwPkt_TEST_F_RENAMED_FWINFO_{TODAY}.zip"
    repack(stage, out, "F")
    return "F: NEG CTRL — firmwareInfo renamed to firmware_info", out

def card_G_fwpkt_nested_in_subdir():
    """Wrap FwPkt/ inside MyFirmware/ — tests whether device looks recursively.
       Zip layout: MyFirmware/FwPkt/...  (so /app/sd/MyFirmware/FwPkt/... after unzip)
       The device looks at /app/sd/FwPkt/, so this MUST be ignored."""
    stage = LOCAL_OUT / "_stage_G"
    extract(STOCK_ZIP, stage)
    nested = stage / "MyFirmware"
    nested.mkdir()
    (stage / "FwPkt").rename(nested / "FwPkt")
    out = LOCAL_OUT / f"FwPkt_TEST_G_NESTED_FWPKT_{TODAY}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    subprocess.run(
        ["zip", "-qr", "-X", str(out), "MyFirmware"],
        cwd=stage, check=True,
    )
    print(f"  [G] built {out.name}  size={size_of(out):,}  md5={md5_of(out)}")
    return "G: NEG CTRL — FwPkt/ nested in MyFirmware/ (recursive-lookup probe)", out

def card_H_fwinfo_recomputed():
    """Stock zip with firmwareInfo re-serialised using actual on-disk MD5s.
       If host MD5s match device MD5s, this should install fine.
       This is the 'host vs device MD5 equivalence' test."""
    stage = LOCAL_OUT / "_stage_H"
    extract(STOCK_ZIP, stage)
    fwpkt = stage / "FwPkt"
    fi_path = fwpkt / "firmwareInfo"
    d = parse_firmwareinfo(fi_path.read_text())

    # The MD5 targets in the on-device CrcMd5 function are:
    #   config       -> FwPkt/camera/config
    #   uImage       -> FwPkt/camera/uImage
    #   rootfs       -> FwPkt/camera/rootfs.ubifs
    #   appfs        -> FwPkt/camera/appfs.ubifs
    #   polaris403   -> FwPkt/gimbal/polaris403_*.bin   (glob)
    #   polaris413   -> FwPkt/gimbal/polaris413_*.bin   (glob)
    mapping = {
        "config":     fwpkt / "camera" / "config",
        "uImage":     fwpkt / "camera" / "uImage",
        "rootfs":     fwpkt / "camera" / "rootfs.ubifs",
        "appfs":      fwpkt / "camera" / "appfs.ubifs",
        "polaris403": sorted((fwpkt / "gimbal").glob("polaris403_*.bin"))[0],
        "polaris413": sorted((fwpkt / "gimbal").glob("polaris413_*.bin"))[0],
    }
    for k, p in mapping.items():
        actual = md5_of(p)
        sz = size_of(p)
        if d[k]["md5"] != actual:
            print(f"  [H] NOTE: {k} MD5 in firmwareInfo was {d[k]['md5']}, "
                  f"recomputed {actual} (size {sz})")
        d[k]["md5"] = actual
        d[k]["size"] = sz
    fi_path.write_text(serialise_firmwareinfo(d))
    out = LOCAL_OUT / f"FwPkt_TEST_H_FWINFO_RECOMPUTED_MD5S_{TODAY}.zip"
    repack(stage, out, "H")
    return "H: STOCK with re-computed MD5s in firmwareInfo", out

def card_I_padded_with_recomputed_md5s():
    """The smoking gun: padded-appfs build but with all 6 MD5s in firmwareInfo
       correctly re-computed from the actual on-disk files. If the device
       installs this, our padded appfs is fine and the previous failures
       were solely an MD5-mismatch on the appfs. If this fails the same way,
       the bug is in something other than just MD5."""
    stage = LOCAL_OUT / "_stage_I"
    extract(PADDED_ZIP, stage)
    fwpkt = stage / "FwPkt"
    fi_path = fwpkt / "firmwareInfo"
    d = parse_firmwareinfo(fi_path.read_text())

    mapping = {
        "config":     fwpkt / "camera" / "config",
        "uImage":     fwpkt / "camera" / "uImage",
        "rootfs":     fwpkt / "camera" / "rootfs.ubifs",
        "appfs":      fwpkt / "camera" / "appfs.ubifs",
        "polaris403": sorted((fwpkt / "gimbal").glob("polaris403_*.bin"))[0],
        "polaris413": sorted((fwpkt / "gimbal").glob("polaris413_*.bin"))[0],
    }
    for k, p in mapping.items():
        d[k]["md5"] = md5_of(p)
        d[k]["size"] = size_of(p)
    fi_path.write_text(serialise_firmwareinfo(d))
    out = LOCAL_OUT / f"FwPkt_TEST_I_PADDED_RECOMPUTED_MD5S_{TODAY}.zip"
    repack(stage, out, "I")
    return "I: PADDED build with re-computed MD5s (smoking gun)", out

def card_J_padded_asis():
    """The 'as we have it now' padded build — i.e. reproduce the user's symptom.
       firmwareInfo says appfs MD5 = 4bd9131b… but if getFwInfo.sh on-device
       computes a different MD5, this is the exact failure we keep seeing."""
    out = LOCAL_OUT / f"FwPkt_TEST_J_PADDED_ASIS_{TODAY}.zip"
    shutil.copyfile(PADDED_ZIP, out)
    return "J: PADDED build, as-is (reproduces current silent-fail symptom)", out

# ---------------------------------------------------------------------------
# Verifier — for each test card, confirm MD5s in firmwareInfo match the
# actual file content (where the test intends them to match) and do NOT
# match (where the test intends a forced mismatch).
# ---------------------------------------------------------------------------

def verify_cards(cards):
    print("\n" + "=" * 78)
    print("VERIFICATION TABLE")
    print("=" * 78)
    print(f"{'Card':<4} {'Description':<35} {'Outcome'}")
    print("-" * 78)
    for label, zip_path in cards:
        card_id = label.split(":")[0]
        try:
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
            if "FwPkt/firmwareInfo" not in names:
                print(f"{card_id:<4} {label[3:]:<35} no FwPkt/firmwareInfo (truncated or nested) -- OK by design")
                continue
            with zipfile.ZipFile(zip_path) as zf:
                with zf.open("FwPkt/firmwareInfo") as f:
                    fi_text = f.read().decode()
            d = parse_firmwareinfo(fi_text)
            with zipfile.ZipFile(zip_path) as zf:
                appfs_bytes = zf.read("FwPkt/camera/appfs.ubifs")
            actual_appfs = hashlib.md5(appfs_bytes).hexdigest()
            claimed_appfs = d["appfs"]["md5"]
            with zipfile.ZipFile(zip_path) as zf:
                cfg_bytes = zf.read("FwPkt/camera/config")
            actual_cfg = hashlib.md5(cfg_bytes).hexdigest()
            claimed_cfg = d["config"]["md5"]
            appfs_match = (actual_appfs == claimed_appfs)
            cfg_match = (actual_cfg == claimed_cfg)
            v = f"appfs={'OK' if appfs_match else 'X'} cfg={'OK' if cfg_match else 'X'}"
            print(f"{card_id:<4} {label[3:]:<35} claim_appfs={claimed_appfs[:8]}.. actual={actual_appfs[:8]}.. {v}")
        except Exception as e:
            print(f"{card_id:<4} {label[3:]:<35} ERROR: {e}")

# ---------------------------------------------------------------------------
def main():
    LOCAL_OUT.mkdir(parents=True, exist_ok=True)

    # Build cards
    cards = [
        card_A_stock_baseline(),
        card_B_negctrl_bad_appfs_md5(),
        card_C_negctrl_bad_config_md5(),
        card_D_negctrl_truncated_zip(),
        card_E_lowercase_zipname(),
        card_F_renamed_firmwareinfo(),
        card_G_fwpkt_nested_in_subdir(),
        card_H_fwinfo_recomputed(),
        card_I_padded_with_recomputed_md5s(),
        card_J_padded_asis(),
    ]

    # Verify
    verify_cards(cards)

    # Copy to SMB only if the share is currently mounted; otherwise skip
    # gracefully so the script still produces local output and prints a hint.
    if SMB_DEST.parent.is_dir():
        SMB_DEST.mkdir(parents=True, exist_ok=True)
        for label, zip_path in cards:
            target = SMB_DEST / zip_path.name
            shutil.copyfile(zip_path, target)
            print(f"[smb] {target}")
        print("\nDone. Test cards at:")
        print(f"  local: {LOCAL_OUT}")
        print(f"  smb:   {SMB_DEST}")
    else:
        print("\nDone. Test cards at:")
        print(f"  local: {LOCAL_OUT}")
        print(f"  smb:   SKIPPED (share not mounted at {SMB_DEST})")
        print("         remount with: gio mount smb://morganbackup.local/Projects/Pentax/BenroPolaris/")
        print("         then re-run with --copy-to-smb")

if __name__ == "__main__":
    main()
