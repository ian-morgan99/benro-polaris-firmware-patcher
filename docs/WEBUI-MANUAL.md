# Polaris Astro Web UI — Manual

The browser control page served by `polaris-httpd` on the mount itself. Open it at
`http://<mount-ip>:8090/` from any device on the same network as the mount's Wi-Fi.

No app, no pairing, no account. The page is compiled into the `polaris-httpd`
binary and served from the mount, so it works with nothing installed and nothing
phoning home.

Everything below was verified against a live Benro Polaris Astro (firmware
`sw:6.0.0.54.97`, hardware `1.1.1.2`) with a Pentax K-1 Mark II attached.

---

## Before you start

**The mount must be levelled and aligned before anything astro-related will work.**
The page tells you what is missing rather than letting you press something that
does nothing: buttons stay disabled until their prerequisites are met, and the
reason is shown next to them.

Two things gate most of the Astro tab:

1. **Celestial mode** must be entered (the mount has to be levelled first).
2. **A position fix** — either a plate solve or a manual alignment.

Until both are true, tracking and "go to" controls are disabled. This is deliberate:
a mount that starts slewing from an unknown pose can point at the ground.

**Escape stops everything.** The `Stop all motion` button (top right) and the
`Esc` key both issue an immediate stop on every axis. Use it if anything moves
unexpectedly.

---

## Layout

Five tabs along the bottom: **Control · Programs · Astro · Gallery · Settings**.

Along the top are status chips: gimbal battery, card free space, and the connected
camera's name (e.g. `Ricoh Pentax K-1 Mark II`). The camera chip is hidden when no
body is attached. A small dot shows the state of the control link to the mount.

---

## Control tab

The shooting screen: live view in the middle, exposure and focus around it.

### Live view

Press **live** to start the preview stream.

Live view is served by the head's own stock preview server on port `8080`, not by
the control server. It is referenced directly rather than proxied, because proxying
a never-ending stream through a single-threaded server would block every other
request for as long as it was open.

Two things can go wrong, and the page now says which:

- **"Live view did not load from …"** — the connection was refused. The camera must
  be awake and in a mode that allows preview.
- **"The head opened the preview stream but sent no frame."** — the head's preview
  server has stopped serving frames. This is cleared by rebooting the mount;
  everything else on the page keeps working. Toggling live view off and on does
  *not* fix it (tested: the stuck socket count kept climbing across an off/on
  cycle). Tracked as issue #270.

### Exposure

Five slots — **shutter, aperture, ISO, EV, WB** — each a dropdown of the values the
camera currently allows. The list comes from the camera, so it changes with mode:
in some modes only a couple of options appear.

Changing one shows a small status badge while it is being applied:

| Badge | Meaning |
|---|---|
| `ISO: applying…` | Sent, waiting for the camera to confirm |
| `ISO: retry 2/3` | Not confirmed yet, sending again |
| `ISO: camera refused` | The camera rejected it — see below |
| *(badge disappears)* | Confirmed by reading the value back |

A change is not considered done until the page has **read the new value back from
the camera**. It retries three times and then gives up honestly rather than showing
a setting the camera never accepted.

**"camera refused" is usually the camera, not the page.** Which settings a body will
accept depends on what mode its dial is in. After a power cycle, every one of these
was refused while reads continued to work perfectly — the page retried, reported the
refusal, and left the real value displayed. Put the dial into a mode that allows the
setting you want.

### Focus

**MF / AF** chips switch focus mode; the active one is highlighted. Below them, four
buttons jog manual focus: `◄◄` `◄` `►` `►►` (coarse and fine, each direction).

### Buttons on the stage

| Button | What it does |
|---|---|
| **live** | Live view on/off |
| **#** | Framing grid overlay |
| **◎** | Focus peaking and histogram |
| **A** / **A+** | Toggle control and text size (persists between visits) |
| **⤢** | Fullscreen preview, with the joysticks and shutter still overlaid |
| **hold to shoot** | Press and hold to take a photo |
| **● rec** | Start/stop recording |
| **auto level** | Level the head now — *this moves the mount, so it asks first* |

### Jog pads

Three pads drive pan, tilt and rotation. The **gear slider** sets their top speed;
moving it while a pad is held re-applies the new speed immediately rather than
waiting for the next movement.

Each pad has a re-zero control to set the current pose as zero for that axis.

---

## Programs tab

Eight automated sequences, chosen from the segmented control at the top. Only one
panel is shown at a time.

| Programme | What it does | Key controls |
|---|---|---|
| **Timelapse** | Fixed-interval shots | interval, shots (`∞ unlimited` allowed), bulb, fps |
| **Path-lapse** | Moves to waypoints between shots | waypoint list, *Capture waypoint*, *Clear all* |
| **Sun** | Shoots around sunrise/sunset | event (Sunrise/Sunset) and timing |
| **Holy Grail** | Day-to-night exposure ramp | enable, target brightness curve, node times in minutes |
| **Panorama** | Grid of overlapping frames | columns, rows, start position and direction, coverage, frame overlap, horizontal/vertical angle, interval |
| **HDR** | Exposure bracketing | bracket spread in steps |
| **Focus stack** | Racks focus through a range | rack direction and step controls, focus curve plot |
| **Program** | Named keyframe sequence | keyframe list, *Capture current pose*, *Clear all* |

Starting a programme begins camera work and, for the ones that move, mount motion.
The running job's progress is shown on the same panel; **Settings → Control link**
and the Gallery both reflect what it produces.

---

## Astro tab

Sections: **Celestial mode · Plate solving · Auto-guiding · Mount status ·
Observatory bridges**.

### Celestial mode

Turning this on puts the mount into astro mode. It requires the mount to be levelled
first, and the page will say so if it is not.

- **Auto-level the head now** — levels the mount. Moves hardware, asks for
  confirmation.
- **Start tracking** — begins sidereal tracking once a position fix exists.
- **Tracking rate / half-speed / dither** — rate selection and small random offsets
  between frames to remove fixed-pattern noise.

### Plate solving

The mount takes a picture, works out exactly where it is pointing from the stars,
and uses that as its position fix. This is what makes "go to a star" accurate.

- **Capture & solve** — take a new frame and solve it.
- **Solve latest frame** — solve a frame already on the card.
- **Apply last** — use the previous solution.
- **Cancel solve** — appears while a solve is running.
- **Focal length** — enter the lens in use. Getting this right matters: the solver
  uses it to pick its search index, and a wrong value makes a solve slow or fail.

Status, the resulting coordinates, and the solver log are shown inline.

### Auto-guiding

Turn guiding on/off once tracking is running. Guiding corrects small tracking errors
during long exposures.

### Mount status

Live pose and mode read from the head. **Read position** refreshes it.

Altitude here is displayed the way you would say it out loud — the head reports it
positive-downward, and the page converts that for display.

### Observatory bridges

This server speaks **three mount protocols at once**, so most astronomy software can
drive the Polaris directly:

| Protocol | Typical clients |
|---|---|
| **ASCOM Alpaca** | NINA, Stellarium — auto-discovered |
| **Native INDI** | KStars/Ekos, PHD2 |
| **LX200 over TCP** | Stellarium, SkySafari, the LX200-generic driver |

The INDI server exposes **both a mount and a camera**: connect the *INDI Telescope*
and *INDI CCD* drivers to this host and port, and the camera side returns a live-view
frame for framing.

This section is folded away under **Diagnostics & bridges** so it doesn't clutter the
Astro tab; it also holds the solver, guiding and mount-status diagnostics.

---

## Gallery tab

Everything on the card, plus a solver test bench.

- **Filter chips** narrow by category — `All`, `Timelapse`, `Photos`, `Test input` —
  each showing its count.
- Thumbnails load lazily: only the ones you scroll to are fetched, which is why a
  large gallery opens fast.
- Click any image for a full view; **Escape** or the close button dismisses it.
- **Upload JPEG** puts a file on the card for testing.

### Historic image solver test

Deliberately separate from the live solve path. Pick an existing image, choose the
solver and give it focal length, sensor size, and optionally a known RA/Dec and
search radius, then **Solve selected image**. It reports the result without touching
the mount, so you can compare solvers or verify a catalogue against images you
already have. **Cancel** stops a running test.

---

## Settings tab

Sections: **Observing site · Device · Head settings · Wi-Fi · Control link · About**.

### Observing site

Latitude and longitude, entered by hand or filled in with **Use my location** (the
browser asks for geolocation permission). **Save site** stores it.

This matters more than it looks: the site is used for the plate-solving hint, for
sunrise/sunset timing, and for what the external bridges report. A wrong site makes
solves slower and can make them fail outright.

### Device

Firmware, hardware, Astro Kit version and the head's clock. **Refresh** reads them
again from the mount. If it says *"The control link is down — align the mount, then
Refresh"*, the link needs to be established first.

### Head settings

- **Camera direction** — which way the camera plate faces relative to the mount.
  Get this wrong and pointing calculations are mirrored.
- **Travel limits** — restricting the angle. Switching it **off** enforces the
  limits immediately and is always safe. Switching it **on** only *reveals* a second
  confirmation box; the limits are not released until you tick that clearance
  deliberately. Releasing travel limits lets the mount move somewhere it would
  otherwise refuse, so it cannot be done with one accidental click.

### Wi-Fi

- **Auto-join** — reconnect to a known network automatically.
- **Keep Wi-Fi awake** — stops the head dropping its radio when idle. Worth leaving
  on: a dropped radio mid-sequence loses the session.

### Control link

State of the connection to the mount, with counters for connects, drops and parse
errors. If controls stop responding, look here first.

### About

Build and version information.

---

## Safety model

Worth understanding before you rely on it in the field.

- **Anything that moves the mount asks for confirmation.** Auto-level, tracking,
  slewing to a target — each requires an explicit second step.
- **Nothing happens on a plain page load or a link click.** Every action endpoint
  requires POST; a GET is rejected with `405`. This exists because documentation
  tools, link scanners and browser prefetchers issue GETs, and one of them hitting
  `/api/astro/capture` would have started an *unbounded* capture stack.
- **Settings are confirmed by reading them back.** A value is not shown as applied
  until the camera has reported it.
- **Escape always stops motion**, from anywhere on the page.
- **Disabled means disabled.** Controls stay inactive until their prerequisites are
  met, with the reason shown, rather than accepting a press and doing nothing.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Page won't load | Check you're on the mount's Wi-Fi and using `http://<ip>:8090/` |
| Live view shows "sent no frame" | Head's preview server has wedged. Reboot the mount. Everything else still works (#270) |
| "camera refused" on every setting | The body's dial is in a mode that locks those settings. Change mode |
| Camera name chip missing | No camera attached, or the body is asleep |
| Tracking / go-to greyed out | Celestial mode not entered, or no position fix yet. Level, enter celestial mode, then solve |
| Solve slow or failing | Focal length in the Astro tab doesn't match the lens actually on the camera |
| Controls stop responding | Check Settings → Control link for drops/parse errors |
| Sunrise/sunset times wrong | Observing site is wrong — re-enter it in Settings |
| Battery chip turns **amber** | Below 20%. Charge soon |
| Battery chip turns **red** | Below 16%. Stop and charge — the mount will not warn you again mid-sequence |
| Battery chip shows **⚡** | Charging |

---

## Notes on behaviour that looks odd but isn't

- **The camera name appears over the live frame**, formatted as `Ricoh Pentax K-1
  Mark II` rather than the raw protocol string, which is over 90 characters of
  semicolon-separated fields.
- **Thumbnails only load as you scroll.** That's lazy loading, not a broken gallery.
- **A setting can take a few seconds** to show as applied. The page waits for the
  camera to confirm rather than assuming it worked.
- **Altitude in Mount status** reads positive-upward, which is how people say it;
  the head itself reports it positive-downward.
