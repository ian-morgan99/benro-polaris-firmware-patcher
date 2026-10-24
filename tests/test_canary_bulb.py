import importlib.util
from pathlib import Path

import pytest


def load_probe():
    path = Path(__file__).parents[1] / "scripts" / "canary-probe.py"
    spec = importlib.util.spec_from_file_location("canary_probe_bulb", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# A trimmed but format-faithful copy of what command 268 reports on the K-3 III
# Mark III: slash labels below 1s, `MM-SS` labels at and above 1s, and no
# `Bulb` entry anywhere (the longest exposure offered is `00-30`).
K3_SHUTTER_LIST = "1/8000,1/1000,1/60,1/4,00-03,00-08,00-30"
K3_CURRENT = 3  # 1/4 -- the value the body reports while in Manual mode


def info(current=K3_CURRENT, options=K3_SHUTTER_LIST):
    return f"268@V:{current};R:{options};#"


def ack(index, ret=0):
    return f"261@s:{index};ret:{ret};#"


class FakePolaris:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.sends = []

    def send(self, *args, **kwargs):
        self.sends.append((args, kwargs))

    def wait_code(self, wanted, _timeout):
        response = next(self.responses)
        assert response.startswith(f"{wanted}@"), (
            f"test queued a {wanted}@ reply but the device got {response!r}"
        )
        return response.split("@", 1)[1].rstrip("#")


def test_bulb_payload_is_explicit_and_nonzero():
    mod = load_probe()
    assert mod.bulb_capture_payload(8) == "state:1;bulb:8;c:-1;"
    assert mod.bulb_capture_payload(None) == "state:1;bulb:0;c:-1;"


def test_bulb_payload_rejects_zero_or_negative_duration():
    mod = load_probe()
    for seconds in (0, -1):
        try:
            mod.bulb_capture_payload(seconds)
        except ValueError:
            pass
        else:
            raise AssertionError("non-positive duration must not be a Bulb test")


def test_shutter_set_command_is_261_not_277():
    """277 is camera_set_aperture; 261 is the shutter setter the app itself uses."""
    mod = load_probe()
    assert mod.SHUTTER_SET_COMMAND == 261
    assert mod.SHUTTER_INFO_COMMAND == 268
    device = FakePolaris([ack(5), info(5)])
    mod.set_shutter(device, 5)
    assert device.sends[0] == ((261,), {"payload": "s:5;"})


def test_parse_shutter_seconds_handles_every_wire_label_form():
    mod = load_probe()
    assert mod.parse_shutter_seconds("1/8000") == 1 / 8000
    assert mod.parse_shutter_seconds("13/10") == 1.3
    assert mod.parse_shutter_seconds("00-30") == 30.0
    assert mod.parse_shutter_seconds("01-30") == 90.0
    assert mod.parse_shutter_seconds("  00-08 ") == 8.0
    # Non-exposure entries must never be mistaken for a duration.
    for label in ("Bulb", "B", "AUTO", "", "bulb", "1/x", "00-x"):
        assert mod.parse_shutter_seconds(label) is None


def test_resolve_shutter_index_prefers_exact_then_shortest_covering():
    mod = load_probe()
    options = K3_SHUTTER_LIST.split(",")
    assert mod.resolve_shutter_index(options, 8)[0] == 5      # exact 00-08
    assert mod.resolve_shutter_index(options, 1 / 60)[0] == 2  # exact 1/60
    assert mod.resolve_shutter_index(options, 4)[0] == 5      # 00-08 covers 4s
    assert mod.resolve_shutter_index(options, 9)[0] == 6      # 00-30 is the shortest cover
    assert mod.resolve_shutter_index(options, 120)[0] == 6    # nothing covers: longest


def test_resolve_shutter_index_rejects_a_list_without_durations():
    mod = load_probe()
    try:
        mod.resolve_shutter_index(["Bulb", "AUTO"], 8)
    except RuntimeError as exc:
        assert "no numeric shutter options" in str(exc)
    else:
        raise AssertionError("a list with no numeric options must fail closed")


def test_bulb_index_is_resolved_by_duration_without_a_Bulb_entry():
    """The K-3 III exposes no `Bulb` label, so resolution is by duration."""
    mod = load_probe()
    device = FakePolaris([info()])
    current, index, label, seconds, started_in_b = mod.prepare_bulb_shutter(device, 8)
    assert (current, index, label, seconds) == (K3_CURRENT, 5, "00-08", 8.0)
    assert started_in_b is False
    assert device.sends == [((268,), {})]


def test_explicit_shutter_index_overrides_duration_resolution():
    mod = load_probe()
    device = FakePolaris([info()])
    current, index, label, _, started_in_b = mod.prepare_bulb_shutter(
        device, 8, explicit_index=6
    )
    assert (current, index, label) == (K3_CURRENT, 6, "00-30")
    assert started_in_b is False


def test_explicit_shutter_index_outside_the_list_is_rejected():
    mod = load_probe()
    for bad in (-1, 99):
        try:
            mod.prepare_bulb_shutter(FakePolaris([info()]), 8, explicit_index=bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"index {bad} is outside the live option list")


def test_shutter_ack_requires_explicit_ret_zero():
    mod = load_probe()
    for response in ("261@s:5;#", "261@s:5;ret:-2;#"):
        device = FakePolaris([response])
        try:
            mod.set_shutter(device, 5, verify=False)
        except RuntimeError as exc:
            assert "explicit ret:0" in str(exc)
        else:
            raise AssertionError("missing or nonzero ret must fail closed")


def test_accepted_but_unapplied_shutter_fails_closed():
    """`ret:0` only means the request parsed; the readback is authoritative."""
    mod = load_probe()
    device = FakePolaris([ack(4), info(K3_CURRENT)])  # still reporting 1/4
    try:
        mod.set_shutter(device, 4, settle_timeout=0.0)
    except RuntimeError as exc:
        assert "accepted (ret:0)" in str(exc)
    else:
        raise AssertionError("a shutter that did not move must not report success")


def test_shutter_write_that_applies_late_is_not_reported_as_failure():
    """The K-3 III honours a 261 write seconds later; polling must not give up.

    Device evidence (Clog 2026-10-05): `s:54` ret:0 at 18:49:41, command 268
    still V:33 at 18:49:42, V:54 from 18:49:54. A single immediate readback
    turned that working write into a false "accepted but not applied" failure,
    which is how #173 was misattributed to the camera.
    """
    mod = load_probe()
    slept: list[float] = []
    device = FakePolaris([ack(4), info(K3_CURRENT), info(K3_CURRENT), info(4)])
    mod.set_shutter(
        device, 4, settle_timeout=30.0, poll_interval=1.0, sleep=slept.append
    )
    # Two polls were stale, a third confirmed, and no error was raised.
    assert len(slept) == 2
    assert device.sends[0] == ((261,), {"payload": "s:4;"})
    assert device.sends[1][0][0] == 268 and device.sends[2][0][0] == 268


def test_shutter_settle_budget_is_bounded_and_configurable():
    """A camera that never applies the write must still fail, not hang."""
    mod = load_probe()
    slept: list[float] = []
    # Every readback keeps reporting the old index.
    replies = [ack(4)] + [info(K3_CURRENT)] * 40
    device = FakePolaris(replies)
    clock = iter([0.0] + [i * 5.0 for i in range(1, 41)])
    real_monotonic = mod.time.monotonic
    mod.time.monotonic = lambda: next(clock)
    try:
        mod.set_shutter(
            device, 4, settle_timeout=10.0, poll_interval=5.0, sleep=slept.append
        )
    except RuntimeError as exc:
        assert "still is not reported after 10s" in str(exc)
    else:
        raise AssertionError("an endless stale readback must fail closed")
    finally:
        mod.time.monotonic = real_monotonic


def test_bulb_session_restores_the_exact_prior_shutter():
    mod = load_probe()
    device = FakePolaris([
        info(K3_CURRENT),
        ack(5),
        info(5),           # verification readback after selecting 00-08
        ack(K3_CURRENT),
        info(K3_CURRENT),  # verification readback after restoring
    ])
    with mod.bulb_shutter_session(device, 8):
        pass
    assert device.sends == [
        ((268,), {}),
        ((261,), {"payload": "s:5;"}),
        ((268,), {}),
        ((261,), {"payload": f"s:{K3_CURRENT};"}),
        ((268,), {}),
    ]


def test_a_shutter_already_at_the_requested_index_is_not_re_written():
    """Re-writing the current index is not a no-op: on device it answers ret:-2.

    When the body already reports the index the bulb request resolves to, the
    session must send no 261 at all — neither the "set" nor the "restore".
    """
    mod = load_probe()
    device = FakePolaris([info("00-08")])
    with mod.bulb_shutter_session(device, 8):
        pass
    assert device.sends == [((268,), {})]


def test_code_780_expected_version_is_checked_on_the_wire():
    mod = load_probe()
    device = FakePolaris(["780@sw:6.0.0.54.52;#"])
    assert mod.read_expected_sw(device, "6.0.0.54.52") == "6.0.0.54.52"
    assert device.sends == [((780,), {})]


def test_code_780_missing_or_wrong_version_fails_closed():
    mod = load_probe()
    for response in ("780@ret:0;#", "780@sw:8.0.0.76;#"):
        device = FakePolaris([response])
        try:
            mod.read_expected_sw(device, "6.0.0.54.52")
        except RuntimeError:
            pass
        else:
            raise AssertionError("invalid code-780 version response must fail closed")


def test_bulb_timeout_is_shared_across_canary_entry_points(monkeypatch):
    """Budget arithmetic must be identical wherever a shot is issued.

    These durations exceed the automated-testing ceiling on purpose: the point
    under test is the budget formula, not the guard. The override is exactly the
    escape hatch a deliberate long-exposure run uses, so the arithmetic stays
    exercised at realistic lengths instead of being silently downgraded to
    in-ceiling values.
    """
    monkeypatch.setenv("OPENPOLARIS_MAX_TEST_EXPOSURE", "600")
    mod = load_probe()
    assert mod.effective_shot_timeout(180, 70) == 180
    assert mod.effective_shot_timeout(120, 300) == 390


def test_capture_failure_remains_primary_when_restore_succeeds():
    mod = load_probe()
    device = FakePolaris([
        info(K3_CURRENT),
        ack(5),
        info(5),
        ack(K3_CURRENT),
        info(K3_CURRENT),
    ])
    try:
        with mod.bulb_shutter_session(device, 8):
            raise RuntimeError("capture failed")
    except RuntimeError as exc:
        assert str(exc) == "capture failed"
    else:
        raise AssertionError("capture exception was lost")


def test_capture_failure_remains_primary_when_restore_fails():
    mod = load_probe()
    device = FakePolaris([
        info(K3_CURRENT),
        ack(5),
        info(5),
        ack(K3_CURRENT, ret=1),
    ])
    try:
        with mod.bulb_shutter_session(device, 8):
            raise RuntimeError("capture failed")
    except RuntimeError as exc:
        assert str(exc) == "capture failed"
    else:
        raise AssertionError("capture exception was replaced by restore failure")


def test_restore_failure_fails_a_successful_capture():
    mod = load_probe()
    device = FakePolaris([
        info(K3_CURRENT),
        ack(5),
        info(5),
        ack(K3_CURRENT, ret=1),
    ])
    try:
        with mod.bulb_shutter_session(device, 8):
            pass
    except RuntimeError as exc:
        assert "explicit ret:0" in str(exc)
    else:
        raise AssertionError("restore failure did not fail the canary")


# With the dial on `B` the body reports a single-entry list instead of the timed
# one: `268@RD:0;V:0;R:00:00,;` (measured on device,
# o-v16c-context-lifetime-20261009). That entry is the bulb slot, so the bulb
# canary must run against it rather than abort with "no numeric shutter options".
B_MODE_INFO = "268@RD:0;V:0;R:00:00,;#"


def test_bulb_in_b_mode_uses_the_single_bulb_entry_instead_of_aborting():
    mod = load_probe()
    device = FakePolaris([B_MODE_INFO])
    current, index, label, seconds, started_in_b = mod.prepare_bulb_shutter(device, 5)
    assert (current, index, label, seconds) == (0, 0, "00:00", None)
    assert started_in_b is True
    assert device.sends == [((268,), {})]


def test_bulb_session_in_b_mode_writes_no_shutter_and_restores_nothing():
    """`s:0;` over an already-selected `V:0` answers ret:-2, so it must not be sent."""
    mod = load_probe()
    device = FakePolaris([B_MODE_INFO])
    with mod.bulb_shutter_session(device, 5):
        pass
    assert device.sends == [((268,), {})]


def test_bulb_session_still_writes_when_the_body_offers_timed_shutters():
    mod = load_probe()
    device = FakePolaris([
        info(),          # resolve -> index 5
        ack(5), info(5),  # set + verify
        ack(K3_CURRENT), info(K3_CURRENT),  # restore + verify
    ])
    with mod.bulb_shutter_session(device, 8):
        pass
    assert [call[1]["payload"] for call in device.sends
            if call[0][0] == 261] == ["s:5;", "s:3;"]


def test_a_single_numeric_entry_is_still_resolved_by_duration():
    """Only a non-duration single entry is the bulb slot; `00-30` is a real shutter."""
    mod = load_probe()
    device = FakePolaris([info(current=0, options="00-30")])
    current, index, label, seconds, started_in_b = mod.prepare_bulb_shutter(device, 8)
    assert (current, index, label, seconds) == (0, 0, "00-30", 30.0)
    assert started_in_b is False


# --- #206: B-mode detection must not depend on the entry's label format -------

def test_is_bulb_slot_list_accepts_colon_and_hyphen_zero_forms():
    """Both observed/possible B-slot encodings are recognised, and a real timed
    shutter is not (#206)."""
    mod = load_probe()
    assert mod.is_bulb_slot_list(["00:00"]) is True    # measured colon form
    assert mod.is_bulb_slot_list(["00-00"]) is True    # hypothetical hyphen form
    assert mod.is_bulb_slot_list(["Bulb"]) is True     # non-numeric label
    assert mod.is_bulb_slot_list(["00-30"]) is False   # a real 30 s shutter
    assert mod.is_bulb_slot_list(K3_SHUTTER_LIST.split(",")) is False


def test_hyphen_form_b_entry_is_treated_as_bulb_slot_not_aborted():
    """A future firmware reporting the B slot as `00-00` must not abort the canary
    via resolve_shutter_index's 'no numeric shutter options' (#206)."""
    mod = load_probe()
    device = FakePolaris(["268@RD:0;V:0;R:00-00,;#"])
    current, index, label, seconds, started_in_b = mod.prepare_bulb_shutter(device, 5)
    assert (current, index, seconds) == (0, 0, None)
    assert started_in_b is True


# --- #208: an explicit timed index while the dial is on B --------------------

def test_explicit_index_while_on_b_is_not_rejected_against_the_collapsed_list():
    """Index 5 is a valid K-3 III timed shutter; it is only unreachable while the
    dial sits on B, so it must not raise a range error (#208)."""
    mod = load_probe()
    device = FakePolaris([B_MODE_INFO])
    current, index, label, seconds, started_in_b = mod.prepare_bulb_shutter(
        device, 8, explicit_index=5
    )
    assert (current, index) == (0, 5)
    assert seconds is None and started_in_b is True
    assert device.sends == [((268,), {})]


def test_explicit_index_equal_to_the_b_slot_is_a_noop():
    mod = load_probe()
    device = FakePolaris([B_MODE_INFO])
    current, index, label, seconds, started_in_b = mod.prepare_bulb_shutter(
        device, 8, explicit_index=0
    )
    assert (current, index, label, seconds) == (0, 0, "00:00", None)
    assert started_in_b is True


def test_negative_explicit_index_is_still_rejected():
    mod = load_probe()
    try:
        mod.prepare_bulb_shutter(FakePolaris([B_MODE_INFO]), 8, explicit_index=-1)
    except ValueError:
        pass
    else:
        raise AssertionError("a negative index is invalid in any mode")


# --- #209: verify must not accept a match across a changing list shape -------

def test_set_shutter_rejects_a_wrong_shape_index_match_and_keeps_polling():
    """Writing timed index 0 while the body is still on B: a `V:0` in the collapsed
    list is NOT the timed index 0, so the poll must keep going until the timed
    list appears (#209)."""
    mod = load_probe()
    slept: list[float] = []
    device = FakePolaris([ack(0), B_MODE_INFO, info(0)])
    mod.set_shutter(device, 0, expect_bulb_slot=False,
                    settle_timeout=30.0, poll_interval=1.0, sleep=slept.append)
    assert len(slept) == 1  # first (collapsed-list) readback was rejected
    assert device.sends[0] == ((261,), {"payload": "s:0;"})


def test_set_shutter_accepts_a_bulb_slot_match_when_that_is_what_is_expected():
    """The inverse: restoring the B slot must accept the collapsed-list `V:0`."""
    mod = load_probe()
    device = FakePolaris([ack(0), B_MODE_INFO])
    mod.set_shutter(device, 0, expect_bulb_slot=True, settle_timeout=0.0)
    assert device.sends[0] == ((261,), {"payload": "s:0;"})


def test_set_shutter_fails_closed_when_the_shape_never_arrives():
    """A body that stays on B after a timed write must fail, not report success on
    the wrong coordinate system (#209)."""
    mod = load_probe()
    slept: list[float] = []
    replies = [ack(5)] + [B_MODE_INFO] * 40
    device = FakePolaris(replies)
    clock = iter([0.0] + [i * 5.0 for i in range(1, 41)])
    real_monotonic = mod.time.monotonic
    mod.time.monotonic = lambda: next(clock)
    try:
        mod.set_shutter(device, 5, expect_bulb_slot=False,
                        settle_timeout=10.0, poll_interval=5.0, sleep=slept.append)
    except RuntimeError as exc:
        assert "still is not reported after 10s" in str(exc)
    else:
        raise AssertionError("a timed index that never leaves the B list must fail")
    finally:
        mod.time.monotonic = real_monotonic


def test_bulb_session_from_b_restores_verifying_against_the_bulb_list():
    """Full #208 + #209 round trip: start on B, request timed index 5, capture,
    restore the B slot. The restore's readback is the collapsed list and must be
    accepted as the B slot, not rejected as a wrong-shape match."""
    mod = load_probe()
    device = FakePolaris([
        B_MODE_INFO,          # prepare: dial is on B
        ack(5), info(5),      # set timed index 5, verify against the timed list
        ack(0), B_MODE_INFO,  # restore B slot, verify against the collapsed list
    ])
    with mod.bulb_shutter_session(device, 8, explicit_index=5):
        pass
    assert [c[1]["payload"] for c in device.sends if c[0][0] == 261] == ["s:5;", "s:0;"]


# ---------------------------------------------------------------------------
# #206: B mode must be decided from the camera's own exposure mode, not from
# the shape of the command-268 list. The shape heuristic is wrong in both
# directions and the false negative is the one that breaks a run: with the dial
# physically on B on 6.0.0.54.67 the body reported a full 56-entry timed list,
# the probe wrote a timed index, and the capture was refused with state:-6
# (docs/evidence/o-v17b-physical-20261019/bulb-refusal-1.txt).
# ---------------------------------------------------------------------------

# The measured reply, trimmed to the first 17 entries. Index 9 is still the
# value the body reported (V:9) and the list is still multi-entry, so the
# list-shape heuristic returns False for it exactly as it did on device.
B_MODE_WITH_TIMED_LIST = (
    "268@RD:0;V:9;R:00-01,00-02,00-03,00-04,00-05,00-06,00-07,00-08,00-09,"
    "00-10,00-15,00-20,00-25,00-30,00-40,00-50,01-00,;#"
)

# Verbatim shape of the value libgphoto2 builds in _get_Pentax_Conditions
# (camlibs/ptp2/config.c) for the `pentaxconditions` config widget.
CONDITIONS_BULB = (
    "state=0; astro-phase=none; exposure-mode-raw=9; astro-mode=off; "
    "user-mode-raw=0; drive-mode-raw=0; ISO=0; bulb-timer=none;"
)
CONDITIONS_TIMED = CONDITIONS_BULB.replace("exposure-mode-raw=9", "exposure-mode-raw=1")


def test_exposure_mode_raw_is_parsed_from_the_conditions_value():
    mod = load_probe()
    assert mod.parse_exposure_mode_raw(CONDITIONS_BULB) == 9
    assert mod.parse_exposure_mode_raw(CONDITIONS_TIMED) == 1
    # Absent or unparseable must be unknown, never "not B".
    assert mod.parse_exposure_mode_raw("state=0; astro-phase=none;") is None
    assert mod.parse_exposure_mode_raw("exposure-mode-raw=none;") is None
    assert mod.parse_exposure_mode_raw("") is None


def test_bulb_exposure_modes_match_the_camera_protocol():
    """9 = B, 12 = B-off-auto, 20 = Astro Tracer.

    These are the raw exposure-mode values the K-3 III reports for a body that
    can perform a bulb exposure. They are the same values upstream libgphoto2
    uses for this exact decision (camlibs/ptp2/pentax-utils.h
    PENTAX_EXP_MODE_BULB / _BULB_LENS / _ASTROTRACER, consumed by
    pentax_bulb_action_mode_supported) and the pslr equivalents in
    camlibs/pentax/pslr.h (PSLR_EXPOSURE_MODE_B = 9, B_OFFAUTO = 12).
    """
    mod = load_probe()
    assert mod.BULB_EXPOSURE_MODES == frozenset({9, 12, 20})


def test_exposure_mode_query_is_skipped_without_an_ssh_target():
    """No device means no query and no noise: the caller falls back silently."""
    mod = load_probe()
    assert mod.camera_exposure_mode(None) is None
    assert mod.camera_exposure_mode("") is None


def test_direct_query_says_b_even_though_the_list_looks_timed():
    """The measured false negative: dial on B, body reporting a timed list.

    Before #206 the shape heuristic returned False here, the probe resolved a
    timed index and wrote it, and the camera refused the capture with state:-6.
    The direct query must win and the dial must be left alone.
    """
    mod = load_probe()
    mod.camera_exposure_mode = lambda *a, **k: 9
    device = FakePolaris([B_MODE_WITH_TIMED_LIST])
    current, index, label, seconds, started_in_b = mod.prepare_bulb_shutter(
        device, 5, ssh_host="root@192.168.0.1")
    assert started_in_b is True
    assert (index, seconds) == (current, None)
    assert "bulb slot" in label
    assert device.sends == [((268,), {})], "a timed shutter was written while on B"


def test_bulb_session_on_b_with_a_timed_list_writes_nothing():
    mod = load_probe()
    mod.camera_exposure_mode = lambda *a, **k: 9
    device = FakePolaris([B_MODE_WITH_TIMED_LIST])
    with mod.bulb_shutter_session(device, 5, ssh_host="root@192.168.0.1"):
        pass
    assert [c for c in device.sends if c[0][0] == 261] == []


def test_direct_query_overrides_a_false_positive_single_entry_list():
    """A degraded body can report one entry while not being on B (#206 case 1).

    The camera says a timed mode, so the entry must not be silently accepted as
    the bulb slot; with no usable timed shutter the canary fails loudly instead.
    """
    mod = load_probe()
    mod.camera_exposure_mode = lambda *a, **k: 1
    device = FakePolaris([B_MODE_INFO])
    try:
        mod.prepare_bulb_shutter(device, 5, ssh_host="root@192.168.0.1")
    except RuntimeError as exc:
        assert "no numeric shutter options" in str(exc)
    else:
        raise AssertionError("a non-B single-entry list was used as the bulb slot")


def test_list_shape_is_still_used_when_the_query_is_unavailable():
    """Fail-open: with no exposure mode the pre-#206 behaviour must remain."""
    mod = load_probe()
    mod.camera_exposure_mode = lambda *a, **k: None
    device = FakePolaris([B_MODE_INFO])
    current, index, label, seconds, started_in_b = mod.prepare_bulb_shutter(
        device, 5, ssh_host="root@192.168.0.1")
    assert (current, index, label, seconds) == (0, 0, "00:00", None)
    assert started_in_b is True


def test_explicit_index_is_still_honoured_from_b_with_a_timed_list():
    """#208 must keep working when the B-mode list is not collapsed."""
    mod = load_probe()
    mod.camera_exposure_mode = lambda *a, **k: 9
    device = FakePolaris([B_MODE_WITH_TIMED_LIST])
    current, index, label, seconds, started_in_b = mod.prepare_bulb_shutter(
        device, 5, explicit_index=20, ssh_host="root@192.168.0.1")
    assert (index, started_in_b) == (20, True)
    assert "requested from B mode" in label


def test_exposure_mode_query_has_a_kill_switch(monkeypatch):
    """The query opens a second gphoto2 session against a camera pgphoto holds,
    which has not been observed on hardware; POLARIS_EXPOSURE_MODE_QUERY=0 must
    be able to turn it off without touching any other behaviour."""
    mod = load_probe()
    monkeypatch.setenv("POLARIS_EXPOSURE_MODE_QUERY", "0")
    assert mod.camera_exposure_mode("root@192.168.0.1") is None
    monkeypatch.delenv("POLARIS_EXPOSURE_MODE_QUERY", raising=False)
    assert mod.EXPOSURE_MODE_QUERY_TIMEOUT_S <= 10.0


# ---------------------------------------------------------------------------
# #207: the capture timeout must be sized from the duration the camera will
# actually hold for, not only from the number typed on the command line. The
# 268 list is discrete, so a request can resolve to a *longer* slot than asked
# for; budgeting from the request alone then times out a capture that is still
# legitimately exposing.
def test_timeout_grows_when_the_resolved_shutter_is_longer_than_requested():
    mod = load_probe()
    # 5 s requested, but the list's shortest covering slot is 8 s.
    assert mod.effective_shot_timeout(30, 5, 8) == 98.0


def test_timeout_never_shortens_when_the_list_cannot_cover_the_request():
    """A list whose longest slot is shorter than the request keeps the old budget.

    This is the safety property: taking max(requested, resolved) means #207 can
    only ever extend a budget, never introduce a new false timeout.
    """
    mod = load_probe()
    assert mod.effective_shot_timeout(30, 35, 30) == 125.0


def test_timeout_in_b_mode_uses_the_requested_hold():
    """In B mode the collapsed list carries no duration, so resolved is None."""
    mod = load_probe()
    assert mod.effective_shot_timeout(30, 5, None) == 95.0


def test_transfer_margin_is_configurable_and_documented():
    mod = load_probe()
    # The base is a floor: the derived budget may exceed it but never go below it,
    # so --shot-timeout keeps meaning "at least this long" whatever the margin is.
    assert mod.effective_shot_timeout(10, 5, None, margin=0) == 10.0
    assert mod.effective_shot_timeout(2, 5, None, margin=0) == 5.0
    assert mod.effective_shot_timeout(10, 5, None, margin=30) == 35.0
    assert mod.DEFAULT_TRANSFER_MARGIN_S == 90.0


def test_negative_transfer_margin_is_rejected():
    mod = load_probe()
    try:
        mod.effective_shot_timeout(30, 5, None, margin=-1)
    except ValueError:
        pass
    else:
        raise AssertionError("a negative margin must be rejected")


def test_session_yields_the_resolved_duration_for_a_timed_slot():
    mod = load_probe()
    device = FakePolaris([
        info(),                              # resolve 8 s -> index 5 (00-08)
        ack(5), info(5),
        ack(K3_CURRENT), info(K3_CURRENT),
    ])
    with mod.bulb_shutter_session(device, 8) as ctx:
        index, resolved = ctx
        assert index == 5
        assert resolved == 8.0


def test_session_yields_no_duration_in_b_mode():
    mod = load_probe()
    device = FakePolaris([B_MODE_INFO])
    with mod.bulb_shutter_session(device, 5) as ctx:
        index, resolved = ctx
        assert index == 0
        assert resolved is None


def test_session_yields_the_explicit_index_duration_when_forced():
    """An explicit index is validated against the timed list (#208); its duration
    must still reach the caller so the budget reflects it."""
    mod = load_probe()
    device = FakePolaris([
        info(),                              # current 3, timed list
        ack(6), info(6),                     # select 00-30
        ack(K3_CURRENT), info(K3_CURRENT),   # restore
    ])
    with mod.bulb_shutter_session(device, 45, explicit_index=6) as ctx:
        index, resolved = ctx
        assert index == 6
        assert resolved == 30.0


# --- automated-testing exposure ceiling -------------------------------------
# Long exposures heat the sensor, and resolve_shutter_index() falls through to
# the longest available slot, so a mistyped request can silently select `20-00`.
# The ceiling constrains *requested* durations only; an operator who explicitly
# picks a long slot with --bulb-shutter-index is not restricted.

def test_ceiling_default_is_45_seconds():
    mod = load_probe()
    assert mod.max_test_exposure_seconds() == 45.0


def test_bulb_request_at_ceiling_is_allowed():
    mod = load_probe()
    # bulb_capture_payload returns str (the wire frame is encoded by the caller),
    # so assert on str -- a bytes needle here raises TypeError, not a failure.
    payload = mod.bulb_capture_payload(45)
    assert isinstance(payload, str)
    assert "bulb:45" in payload


def test_bulb_request_above_ceiling_is_blocked():
    """A 120 s request must fail loudly rather than resolve to a long slot."""
    mod = load_probe()
    with pytest.raises(ValueError) as exc:
        mod.bulb_capture_payload(120)
    assert "ceiling" in str(exc.value)


def run_probe(*args, env=None):
    """Invoke canary-probe.py as a subprocess, as the other canary tests do."""
    import subprocess
    import sys as _sys
    root = Path(__file__).parents[1]
    proc = subprocess.run(
        [_sys.executable, str(root / "scripts" / "canary-probe.py"), *args],
        capture_output=True, text=True, timeout=60, env=env, cwd=str(root))
    return proc


def test_timed_request_above_ceiling_is_blocked():
    """Enforcement lives in argument validation, so it exits before any socket."""
    proc = run_probe("--host", "127.0.0.1", "--port", "1", "--shot",
                     "--expected-files", "1", "--timed-seconds", "120")
    assert proc.returncode == 2
    assert "ceiling" in (proc.stderr + proc.stdout)


def test_ceiling_is_enforced_before_the_camera_is_touched():
    """A rejected request must fail without connecting.

    Port 1 on loopback is refused instantly, so if the ceiling were checked after
    the socket was opened this would surface a connection error instead of the
    ceiling message. That ordering is the point: an over-long exposure must never
    reach the camera at all.
    """
    proc = run_probe("--host", "127.0.0.1", "--port", "1", "--shot",
                     "--expected-files", "1", "--bulb-seconds", "600")
    combined = proc.stderr + proc.stdout
    assert proc.returncode == 2
    assert "ceiling" in combined
    assert "connect" not in combined.lower()


def test_ceiling_can_be_raised_for_a_deliberate_run(monkeypatch):
    monkeypatch.setenv("OPENPOLARIS_MAX_TEST_EXPOSURE", "300")
    mod = load_probe()
    assert mod.max_test_exposure_seconds() == 300.0
    mod.bulb_capture_payload(120)  # must not raise


def test_ceiling_rejects_nonsense_env_values(monkeypatch):
    """A typo in the override must not silently disable the guard."""
    mod = load_probe()
    for bad in ("bogus", "-5", "0"):
        monkeypatch.setenv("OPENPOLARIS_MAX_TEST_EXPOSURE", bad)
        with pytest.raises(ValueError):
            mod.max_test_exposure_seconds()


def test_slot_derived_duration_is_not_capped():
    """The ceiling guards typed requests, not durations read off the camera.

    ``resolved_seconds`` comes from the live command 268 slot table, so a long
    slot selected deliberately must widen the budget instead of raising (#208).
    """
    mod = load_probe()
    budget = mod.effective_shot_timeout(30.0, 45, resolved_seconds=1200.0)
    assert budget >= 1200.0
