# Using your Benro Polaris with the astro kit

Who this is for: you own a Polaris head, you have put the astro kit on it, and you want to
point it at the sky and take pictures. No terminal, no code, no building anything.

Everything here describes what has actually been checked on a real camera. Where something
has not been proven yet, it says so plainly rather than guessing — that saves you from
chasing a fault that isn't yours.

---

## 1. Getting to the control page

The Polaris runs its own small website. You open it in any browser — phone, laptop, tablet.
Nothing needs installing on your computer.

**First time only.** Turn the head on. It broadcasts its own Wi-Fi network with a name like
`polaris_d13e86` — the word `polaris_` followed by six characters unique to your head. Join
that network from your phone or laptop, then open:

    http://192.168.0.1:8090

That is the whole setup. If the page opens, you are in.

**Joining your own Wi-Fi instead.** By default the head will not join your home network — it
only offers its own. To change that, put two files in a folder called `polaris-wifi` on the
microSD card:

1. A file named `autojoin`, which can be empty. Its mere presence is the switch — nothing runs
   unless it exists.
2. A file named `wpa.conf` next to it, holding your network name and password:

       network={
           ssid="YourNetworkName"
           psk="YourPassword"
       }

Use straight quotes, exactly as above. After a reboot the head joins your network and gets an
address from your router; you can then use that address instead of `192.168.0.1` and no longer
have to be connected to the head's own Wi-Fi to reach it.

**Your phone can still connect the old way.** Joining your network does not switch off the
head's own `polaris_...` hotspot — both keep working, so setting this up cannot lock you out.

**If the page does not open.** Check these in order:

1. Are you on the right network? The head's own Wi-Fi, or your network if you set up autojoin.
2. Is it `:8090` on the end? Forgetting the port is the most common reason.
3. Did the kit actually install? See "After every firmware update" in section 8.

---

## 2. The five tabs

Everything lives under one page with five tabs along the top.

| Tab | What it's for |
|---|---|
| **Control** | Live view, aiming the head, focusing, taking a picture |
| **Programs** | Timelapse, path-lapse, panorama, HDR, focus stacking |
| **Astro** | Telling it where you are, and tracking the stars |
| **Gallery** | Pictures you have taken |
| **Settings** | Location, camera plate orientation, Wi-Fi, what's installed |

One thing worth understanding early: **programmes run on the head itself, not in your
browser.** Start a timelapse, then close the page or walk away — it keeps going, and it stays
watchable when you come back. That is deliberate. A browser tab cannot be trusted to stay
alive for two hours; the head can.

---

## 3. Control tab — aiming and shooting

The live view fills the screen and the controls float on top of it, laid out the way the phone
app does it: joysticks under each thumb.

**Aiming.** The arrow buttons turn the head. The pairs with two arrows (◄◄ ►►) move faster than
the single ones. ↺ and ↻ rotate. There is a **STOP** button that halts motion immediately —
use it if something moves further than you meant.

**Live view.** Toggle it with the `live` control. If the picture freezes rather than updating,
turn it off and back on; this area has had faults before and is being worked on.

**Focusing.** `MF` and `AF` switch between manual and autofocus. For astrophotography you will
normally want manual — autofocus hunts on a dark sky and usually fails.

**Taking a picture.** The capture buttons are:

- **Capture current pose** — take one picture wherever the head is pointing right now
- **Start astro capture** — begin an astro exposure
- **Capture & solve** — take a picture and work out where it is pointing
- **● rec** — start and stop video

Both still-photo paths were tested on a Pentax K-3 III in November 2026 and produced real
files. A timed long exposure was also tested: you set the seconds, and the head holds the
shutter open for that long.

**Bulb exposure.** Programmes have a field called *"Bulb exposure (0 = camera's own shutter)"*.
Leave it at 0 and the camera decides how long to expose, exactly as it would on its own dial.
Put a number in and the head holds the shutter open that many seconds instead — that is what
you want for long exposures the camera won't do by itself.

---

## 4. Programs tab

Six programmes: **Timelapse**, **Path-lapse**, **Sun**, **Holy Grail**, **Panorama**,
**HDR**, and **Focus stack**.

They share a few ideas:

- **Interval between frames** — seconds to wait between shots
- **Frames** — how many to take
- **∞ unlimited** — keep going until you stop it

**Timelapse** takes pictures at an interval from one position. You can also set a video frame
rate if you want the result assembled into a clip.

**Path-lapse** moves between **waypoints**. For each leg you set *Frames to reach the next
waypoint* and *Interval per position*, so the head moves and shoots as it goes.

**Panorama** covers an area with a grid: **Columns**, **Rows**, **Step between columns**,
**Step between rows**, and which **Start corner** it begins from. Use **Preview panorama**
first — it shows you what it intends to do without taking anything.

**HDR** brackets exposures. **Preview HDR** works the same way, and *Merge in the head*
combines the bracketed frames on the Polaris rather than leaving that to your computer.

**Focus stack** takes a series at different focus distances. **Set near limit** and **Set far
limit** mark the range with the ◄◄ / ►► controls, **Rack focus** drives through it, **Dry
preview** walks the whole sequence without taking a single picture — use it before a long run —
and **Stitch all-in-focus in the head** combines the frames on the Polaris.

**Sun** and **Holy Grail** are pre-built sequences driven by **Keyframes**: you set each
keyframe's position and *Seconds to reach the next keyframe*, with an optional photo interval
(0 means motion only, no pictures). The ramp controls (*Enable the ramp*, *Target EV*,
*Safe low/high*, *Span low/high*) gradually change exposure as the sequence runs, which is what
you want for a sunset.

**Before committing to a long run, use the preview or dry-preview button.** They cost seconds
and tell you whether the geometry is right, instead of discovering it an hour in.

> Tested status: the shutter itself and timed exposures are proven on real hardware. The
> individual programmes above have not each been run end-to-end on a camera since this build
> was flashed. If one misbehaves, note exactly which buttons you pressed — that is what makes
> it fixable.

---

## 5. Astro tab — tracking the sky

Two steps, numbered in the page itself.

**Set your location first.** Plate-solve alignment and go-to need to know where you are
standing. Enter your **Latitude** and **Longitude** in Settings. Framing, focusing and the
programmes all work without this — only star tracking needs it.

**Celestial mode.** This puts the head into astro tracking mode and keeps its attitude readings
flowing. The head refreshes those readings itself every few seconds rather than relying on your
browser, so you can leave the page open or closed. Leaving astro mode stops tracking and returns
the head to ordinary photo mode.

**1 — Level the head.** This is tilt compensation, and it is worth understanding because it
sounds like it should be switched off. When it is **on**, the head works out its own tilt from
its attitude sensor and corrects for it, so you can track from an unlevel tripod. It only needs
to know which way is down — which it does. Leave it on unless you have a specific reason.

**2 — Align.** Plate solving takes a picture, identifies the stars in it, and works out exactly
which way the head is pointing. After that, go-to can aim at a target accurately.

> Honest status: the solver loads its full star catalogue and searches, and it has been seen
> working on a computer. **It has not yet completed a solve on the head itself.** If alignment
> never finishes, that is a known gap in this build, not something you have set up wrong. You
> can still frame by eye, use the programmes, and take pictures.

---

## 6. Gallery tab

Pictures land here. They are stored on the microSD card **in the Polaris**, not on your camera —
so the card in the head is what fills up, not your camera's card.

Thumbnails are generated on the head, which is why the grid loads in seconds. The phone app has
to pull whole frames to build a grid and is much slower.

**If a picture you took is missing**, check this first: **is your camera set to RAW only?** If
it is, the file is written as a `.DNG` and the gallery cannot display it — the gallery only
lists JPEGs, and no JPEG copy is made. The photograph exists and is fine; you just have to read
the card on a computer to see it. Switch the camera to JPEG, or JPEG+RAW, if you want pictures
to show up in the page.

This affects every RAW-only capture and has nothing to do with how the picture was taken.

---

## 7. Settings tab

Sections: **Observing site**, **Device**, **Head settings**, **Wi-Fi**, **Control link**,
**About**.

- **Latitude / Longitude** — where you are. Needed for star tracking.
- **Rotate the camera plate** — tells the head how your camera is mounted on it. If pictures
  come out rotated the wrong way, or framing looks sideways, this is usually the setting.
- **Release rotation limits (restricted angle)** — the head ships with some axes limited to
  protect the mechanics. Releasing them allows wider movement. Only do this if you have room
  and know what you are asking for.
- **Control link** — whether the head can see your camera at all. If capture buttons do nothing,
  look here first. It should say *up*. If it says *down*, check the USB cable between the camera
  and the head, then power-cycle the camera.
- **About** — firmware version and what is installed.

---

## 8. After every firmware update — read this

**A firmware update deletes the astro kit.** Not part of it — all of it, along with the thing
that starts it at boot. This is not a fault in the kit; updating replaces the whole area where
the kit lives.

So after any update you must install the kit again. If you skip it, the head comes back on the
new firmware looking completely normal — correct version number, everything working — with no
astro stack at all, and nothing tells you.

**How to check whether you need to do it:** open `http://192.168.0.1:8090`. If the page loads,
you are fine. If it does not load but your firmware is current, the kit is gone and needs
reinstalling.

These two checks are independent and one passing tells you nothing about the other:

- **Firmware version** — read it in the app. A reboot that did *not* update looks identical to
  one that did, so read the number rather than assuming.
- **The page on port 8090** — this is the only proof the astro kit actually started.

A correct version with no page means the install was skipped or stopped partway.

---

## 9. If something goes wrong

**Page won't load.** Right network, `:8090` on the end, kit installed after the last update.
Those three cover almost every case.

**Capture buttons do nothing.** Settings → Control link. If it says *down*, the head cannot see
the camera — reseat the USB cable and power-cycle the camera. Give it a couple of minutes after
reconnecting before trying again; the first attempt right after reconnecting can be accepted and
quietly lost.

**Pictures missing from the gallery.** RAW-only camera setting — see section 6.

**Head moves further than expected.** STOP button, then Settings → Control link to confirm it is
responding. If it consistently overshoots, check *Release rotation limits* hasn't been turned on.

**Alignment never completes.** Known gap in this build (section 5). Not your setup.

**You want it all off again.** There is an uninstaller on the card at
`/app/sd/polaris-astro/uninstall_astro.sh`. It stops the astro processes, restores whatever boot
setup was there before, and removes the kit. **Your pictures are not touched** — the microSD
card keeps your settings, indexes, logs and frames. Reboot afterwards to be sure nothing is left
running.

---

## 10. What has been proven, and what hasn't

Worth knowing so you don't debug something that isn't broken.

**Proven on a real camera (Pentax K-3 III, November 2026):**
- The head sees the camera and reports its name correctly
- Taking a picture works, including timed long exposures at a duration you set
- Exactly one stop is sent when you release — no double-firing mid-exposure
- All five tabs render with no errors
- Programmes keep running on the head after you close the page

**Not yet proven:**
- Plate solving completing on the head itself (works on a computer; not demonstrated on the head)
- Each individual programme run end-to-end since this build was flashed

**Known and understood:**
- RAW-only pictures don't appear in the gallery (section 6)
- Live view has had stability faults and is being worked on
