import importlib.util
from pathlib import Path


def load_probe():
    path = Path(__file__).parents[1] / "scripts" / "canary-probe.py"
    spec = importlib.util.spec_from_file_location("canary_probe_bulb", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakePolaris:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.sends = []

    def send(self, *args, **kwargs):
        self.sends.append((args, kwargs))

    def wait_code(self, wanted, _timeout):
        response = next(self.responses)
        assert response.startswith(f"{wanted}@")
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


def test_bulb_index_is_discovered_from_the_live_option_list():
    mod = load_probe()
    device = FakePolaris(["268@V:1;R:1/30,1s,Bulb,2s;#"])
    current, bulb = mod.prepare_bulb_shutter(device)
    assert (current, bulb) == (1, 2)
    assert device.sends == [((268,), {})]


def test_explicit_bulb_index_must_match_the_live_option_list():
    mod = load_probe()
    device = FakePolaris(["268@V:1;R:1/30,1s,Bulb,2s;#"])
    try:
        mod.prepare_bulb_shutter(device, explicit_index=1)
    except ValueError as exc:
        assert "not the live Bulb option" in str(exc)
    else:
        raise AssertionError("a guessed non-Bulb index must be rejected")


def test_shutter_ack_requires_explicit_ret_zero():
    mod = load_probe()
    for response in ("277@shutter:2;#", "277@shutter:2;ret:1;#"):
        device = FakePolaris([response])
        try:
            mod.set_shutter(device, 2)
        except RuntimeError as exc:
            assert "explicit ret:0" in str(exc)
        else:
            raise AssertionError("missing or nonzero ret must fail closed")


def test_bulb_session_restores_the_exact_prior_shutter():
    mod = load_probe()
    device = FakePolaris([
        "268@V:1;R:1/30,1s,Bulb,2s;#",
        "277@shutter:2;ret:0;#",
        "277@shutter:1;ret:0;#",
    ])
    with mod.bulb_shutter_session(device):
        pass
    assert device.sends == [
        ((268,), {}),
        ((277,), {"payload": "shutter:2;"}),
        ((277,), {"payload": "shutter:1;"}),
    ]


def test_current_shutter_can_be_restored_when_wire_reports_label():
    mod = load_probe()
    device = FakePolaris([
        "268@V:Bulb;R:1/30,1s,Bulb,2s;#",
        "277@shutter:2;ret:0;#",
        "277@shutter:2;ret:0;#",
    ])
    with mod.bulb_shutter_session(device):
        pass
    assert device.sends[-1] == ((277,), {"payload": "shutter:2;"})


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
        "268@V:1;R:1/30,1s,Bulb,2s;#",
        "277@shutter:2;ret:0;#",
        "277@shutter:1;ret:0;#",
    ])
    try:
        with mod.bulb_shutter_session(device):
            raise RuntimeError("capture failed")
    except RuntimeError as exc:
        assert str(exc) == "capture failed"
    else:
        raise AssertionError("capture exception was lost")


def test_capture_failure_remains_primary_when_restore_fails():
    mod = load_probe()
    device = FakePolaris([
        "268@V:1;R:1/30,1s,Bulb,2s;#",
        "277@shutter:2;ret:0;#",
        "277@shutter:1;ret:1;#",
    ])
    try:
        with mod.bulb_shutter_session(device):
            raise RuntimeError("capture failed")
    except RuntimeError as exc:
        assert str(exc) == "capture failed"
    else:
        raise AssertionError("capture exception was replaced by restore failure")


def test_restore_failure_fails_a_successful_capture():
    mod = load_probe()
    device = FakePolaris([
        "268@V:1;R:1/30,1s,Bulb,2s;#",
        "277@shutter:2;ret:0;#",
        "277@shutter:1;ret:1;#",
    ])
    try:
        with mod.bulb_shutter_session(device):
            pass
    except RuntimeError as exc:
        assert "explicit ret:0" in str(exc)
    else:
        raise AssertionError("restore failure did not fail the canary")
