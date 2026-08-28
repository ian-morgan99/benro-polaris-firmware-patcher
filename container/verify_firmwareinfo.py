#!/usr/bin/env python3
"""Fail-closed verifier for Benro Polaris FwPkt package integrity.

The on-board updater (polestar_app -> getFwInfo.sh -> crcInfo) recomputes
the MD5 and size of every component in the FwPkt and string-compares each
'X MD5:' and 'X size:' field against firmwareInfo. Any mismatch -> no NAND
write, silent reboot, no notification. A bad firmwareInfo is therefore
indistinguishable from a corrupt upload to the user.

This script re-runs the on-board check offline, exactly the way the device
will. It reads <stock_firmwareInfo> as the reference line format, walks
every directory entry (camera/, gimbal/), recomputes the MD5 and size of
each file, and compares against the values carried by firmwareInfo in
<FwPkt_dir>. Exits 0 iff every line matches, 1 with a per-line diff
otherwise.

Usage:
    verify_firmwareinfo.py <stock_firmwareInfo> <FwPkt_dir>

This is intended to be run by container/patch.sh immediately after the
manifest regenerator, and to be runnable on any existing build (stock,
Pentax-only, combined, custom) as a sanity check before the user puts the
FwPkt on an SD card. The 2026-08-27-combined-720p60 build, for example,
fails this verifier because its firmwareInfo was not regenerated after
the HDMI geometry repack: firmwareInfo claims appfs MD5
1775c7bc4eee7d549a36fa28bb13f367 but the shipped appfs.ubifs has MD5
91629acf0494b7f43298f6821913124f -- the device's on-board check rejects
that silently.
"""
import hashlib, os, re, sys

CHUNK = 1 << 20

def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(CHUNK), b""):
            h.update(b)
    return h.hexdigest()

# Same resolution as gen_firmwareinfo.py: a single key per file in the
# FwPkt, with polaris*/oms found by glob under gimbal/.
def resolve(key, root):
    fixed = {
        "config": "camera/config",
        "uImage": "camera/uImage",
        "rootfs": "camera/rootfs.ubifs",
        "appfs":  "camera/appfs.ubifs",
    }
    if key in fixed:
        return os.path.join(root, fixed[key])
    if key.startswith("polaris") or key == "oms":
        import glob
        hits = glob.glob(os.path.join(root, "gimbal", key + "_*.bin"))
        return hits[0] if hits else None
    return None

LINE_RE = re.compile(r"^(\w+)\s+size:(\d+);\1\s+MD5:([0-9a-fA-F]+);")

def main():
    if len(sys.argv) != 3:
        sys.stderr.write("usage: %s <stock_firmwareInfo> <FwPkt_dir>\n" % sys.argv[0])
        return 2

    stock_info, root = sys.argv[1], sys.argv[2]
    if not os.path.isfile(stock_info):
        sys.stderr.write("error: firmwareInfo not found: %s\n" % stock_info)
        return 2
    if not os.path.isdir(root):
        sys.stderr.write("error: FwPkt dir not found: %s\n" % root)
        return 2

    fwinfo = os.path.join(root, "firmwareInfo")
    if not os.path.isfile(fwinfo):
        sys.stderr.write("error: %s/firmwareInfo not found\n" % root)
        return 2

    # Read stock firmwareInfo to get the canonical key set, then cross-check
    # against the in-pack firmwareInfo so we can spot reorderings/typos.
    stock_lines = [l.rstrip("\n") for l in open(stock_info, "r") if l.strip()]
    inpack_lines = [l.rstrip("\n") for l in open(fwinfo, "r") if l.strip()]

    stock_keys = [LINE_RE.match(l).group(1) for l in stock_lines if LINE_RE.match(l)]
    inpack_keys = [LINE_RE.match(l).group(1) for l in inpack_lines if LINE_RE.match(l)]
    if stock_keys != inpack_keys:
        sys.stderr.write("FAIL: firmwareInfo key set/order differs from stock\n")
        sys.stderr.write("  stock:  %s\n" % stock_keys)
        sys.stderr.write("  inpack: %s\n" % inpack_keys)
        return 1

    mismatches = []
    checked = 0
    for line in inpack_lines:
        m = LINE_RE.match(line)
        if not m:
            continue
        key, claimed_size, claimed_md5 = m.group(1), int(m.group(2)), m.group(3)
        path = resolve(key, root)
        if not path or not os.path.exists(path):
            mismatches.append((key, "MISSING", "-", str(claimed_size), claimed_md5))
            continue
        actual_size = os.path.getsize(path)
        actual_md5  = md5(path)
        checked += 1
        if actual_size != claimed_size or actual_md5 != claimed_md5:
            mismatches.append((
                key,
                "MISMATCH",
                path,
                "%d (claimed %d)" % (actual_size, claimed_size),
                "%s (claimed %s)" % (actual_md5, claimed_md5),
            ))

    if mismatches:
        sys.stderr.write("FAIL: %d mismatch(es) across %d entries\n" % (len(mismatches), checked))
        for key, kind, path, size_info, md5_info in mismatches:
            sys.stderr.write("  %-10s %-9s %s\n" % (key, kind, path or "(no path)"))
            sys.stderr.write("    size: %s\n" % size_info)
            sys.stderr.write("    md5:  %s\n" % md5_info)
        sys.stderr.write("\nThe on-board updater would silently reject this FwPkt.\n")
        sys.stderr.write("Rebuild with gen_firmwareinfo.py (or container/patch.sh) so the\n")
        sys.stderr.write("manifest is regenerated from the actual file contents, then re-run\n")
        sys.stderr.write("this verifier. Do not put this FwPkt on an SD card.\n")
        return 1

    print("OK: %d entries verified, firmwareInfo matches shipped files" % checked)
    return 0

if __name__ == "__main__":
    sys.exit(main())
