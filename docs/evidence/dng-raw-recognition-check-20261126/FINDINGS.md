# DNG-as-RAW recognition: has it recurred? — NO at driver level, unchanged gap in the Astro UI

Asked on 2026-11-26. Checked each layer rather than recalling the old fix.

## Driver layer: intact, not regressed

`camlibs/ptp2/library.c:3058` still maps the PTP DNG object format to a real MIME type:

```c
{PTP_OFC_DNG,		0, "image/x-adobe-dng"},
```

The middle field is the **vendor** column (0 = standard PTP), not a "raw" flag — so this row is correct as
written and matches every other standard format in the table. Confirmed present in the **shipped** build, not
just source:

```text
strings out/k3iii-readback-20261123-GwTN/feature-prefix/lib/libgphoto2/2.5.34/ptp2.so | grep adobe-dng
image/x-adobe-dng
```

Live proof on the attached K-3 III: a capture returned `PTP_RC_OK` and named a `.DNG` object, and our driver
also exposes the PEF/DNG selector deliberately in config (`config.c:11531 gp_widget_add_choice(*widget,"DNG")`)
with RawKind handled per Pentax contract (`pentax-utils.c:1291`). So DNG is recognised as a distinct image
format by our driver. **The original "DNG not seen as RAW because it's a Pentax thing" defect has not recurred
at this layer.**

## Astro Web UI layer: still JPEG-only — but that is open issue #355, not a regression

Two gates accept JPEG exclusively:

```c
/* container/astro/polaris-httpd.c:1232 */
static int ends_jpg(const char *s) {
    size_t n = strlen(s);
    return (n > 4 && !strcasecmp(s + n - 4, ".jpg")) || (n > 5 && !strcasecmp(s + n - 5, ".jpeg"));
}
```

```html
<!-- container/astro/webui/index.html:927 -->
<input id="gal-test-file" type="file" accept=".jpg,.jpeg,image/jpeg">
```

So a `.DNG` is rejected by the Gallery upload UI and by the backend before it ever reaches the solver. This is
exactly what **#355** describes ("Astro Web UI currently uploads and plate-solves JPEG only") and that issue is
still **OPEN** with its work breakdown untouched. It was never implemented, so nothing regressed — the gap is
the same one, still open.

Distinguish the two: the driver recognises DNG fine; the Astro kit simply refuses non-JPEG input by design,
pending #355's embedded-JPEG-preview work. If a user reports "DNG not recognised", ask which screen — camera
operations are driver-side (working), Gallery upload/solve is UI-side (#355, open).

## Related but separate: K-3 III in MTP mode exposes no writable format control

Live on this body (`--list-config`):

```text
/main/status/imageformat
/main/status/imagequality
```

Both under `/main/status/`, i.e. read-only — there is no writable `imageformat` here, which is consistent with
#386 ("imageformat/imagequality published writable but every write fails"). Also note `function flags
0x00000000` on this body versus `0x00000003` on the K-1 II, and `--summary` reports *"No Image Capture, No Open
Capture"* — yet `--capture-image` still succeeded with `PTP_RC_OK`. Worth its own look; not a DNG issue.

## Unresolved observation, flagged not concluded

Two captures returned `PTP_RC_OK` and named objects (`/IMGP4111.DNG`, `/IMGP4112.DNG`), but the card reports
no objects at all:

```text
--storage-info: description=SD1 totalcapacity=62334976 KB   (card present, ~62 GB)
-l -f /store_00010001: There are 0 folders in folder '/store_00010001'
-n -f /store_00010001: Number of files in folder '/store_00010001': 0
```

Two candidate explanations and I cannot separate them from here: (a) the K-3 III in MTP mode does not expose
DCIM contents over PTP at all, which would be benign and mode-specific; or (b) the capture writes nothing and
the OK status is hollow. `FreeSpace` was absent from `--storage-info`, which weakly favours (a). Resolving it
needs the body's USB setting switched to PTP, or checking the card in a reader — do not treat either capture
as confirmed-written until then.

Note: an earlier `-p /IMGP4112.DNG` attempt crashed with `*** buffer overflow detected ***`. That was **my
malformed CLI argument**, not a defect — it reproduces identically with stock libraries, so it is the system
gphoto2 CLI's argument handling, unrelated to our driver.
