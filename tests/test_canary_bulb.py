import importlib.util
from pathlib import Path


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


def test_bulb_timeout_is_shared_across_canary_entry_points():
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
