# Stock firmware source

## What was used

- File: `firmware/FwPkt.zip` (the user-supplied stock FwPkt)
- MD5: `90bdad511f556f25a2904ae9d2980102`
- SHA-256: `f980fe5245a1f85b58d0c2db523402d1af72ddfff782acba99a4eadfdca54d2f`
- Size: 68,599,228 bytes
- Benro firmware version: not decoded from the ZIP; recorded in
  `builds/2026-08-23/build-source-provenance.txt` under
  `firmware_md5=90bdad511f556f25a2904ae9d2980102`.

## Where it came from

- Source: user-supplied (Ian Morgan). The original Benro Polaris stock
  firmware ZIP was provided by the equipment owner for the purpose of
  producing a patched build with Pentax camera compatibility and HDMI
  geometry changes. We do not record a vendor download URL because the
  firmware was not retrieved from a public Benro download endpoint in
  this session; it was supplied locally.
- Downloaded: pre-existing on the build host on or before 2026-08-22.
- Verified against: no second known-good copy is available. The stock
  firmware is treated as a one-shot user-supplied input.

## Hash disagreement with the issue body

The vetting agent's issue body (GitHub issue #9) recorded the MD5
(`90bdad511f556f25a2904ae9d2980102`) but no SHA-256. The SHA-256 above
was computed in this commit on the same file path. If the upstream
reviewer has a different SHA-256 for a Benro Polaris stock ZIP with
the same MD5, that indicates a hash collision or a different physical
file with the same MD5, neither of which is expected for a 68 MB ZIP.

## License note

This firmware is a Benro / Benro Polaris proprietary work. We do not
redistribute it. The stock `firmware/FwPkt.zip` is gitignored at the
`.gitignore` level (see `FwPkt*.zip` and `*.ubifs` patterns). The
patched output (`builds/2026-08-27-combined-720p60/FwPkt.zip`) is
also gitignored and is not published to GitHub.

## How a reviewer can re-verify the stock firmware

```bash
cd firmware/
md5sum FwPkt.zip
# Expected: 90bdad511f556f25a2904ae9d2980102
sha256sum FwPkt.zip
# Expected: f980fe5245a1f85b58d0c2db523402d1af72ddfff782acba99a4eadfdca54d2f
```

The pentax-only patched build at
`builds/2026-08-23/FwPkt.zip` (md5 `25403283e6f4353a88188ff1aca1837e`)
and the combined Pentax+HDMI patched build at
`builds/2026-08-27-combined-720p60/FwPkt.zip` (md5
`fd8147c91df44757d8a41c8bacc39519`) are both derived from this stock
file. The provenance of those outputs is recorded in their respective
`build-source-provenance.txt` files.

## Gap status

This file closes Gap 7 (issue #9) by recording the stock firmware
provenance in-tree. The license/IP review remains the responsibility
of the upstream reviewer; nothing in this file is a license grant.
