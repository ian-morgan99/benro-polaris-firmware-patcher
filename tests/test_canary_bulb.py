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
    current, index, label, seconds = mod.prepare_bulb_shutter(device, 8)
    assert (current, index, label, seconds) == (K3_CURRENT, 5, "00-08", 8.0)
    assert device.sends == [((268,), {})]


def test_explicit_shutter_index_overrides_duration_resolution():
    mod = load_probe()
    device = FakePolaris([info()])
    current, index, label, _ = mod.prepare_bulb_shutter(device, 8, explicit_index=6)
    assert (current, index, label) == (K3_CURRENT, 6, "00-30")


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
        mod.set_shutter(device, 4)
    except RuntimeError as exc:
        assert "accepted (ret:0)" in str(exc)
    else:
        raise AssertionError("a shutter that did not move must not report success")


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


def test_current_shutter_can_be_restored_when_wire_reports_label():
    mod = load_probe()
    device = FakePolaris([
        info("00-08"),
        ack(5),
        info(5),
        ack(5),
        info(5),
    ])
    with mod.bulb_shutter_session(device, 8):
        pass
    assert device.sends[3] == ((261,), {"payload": "s:5;"})


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
