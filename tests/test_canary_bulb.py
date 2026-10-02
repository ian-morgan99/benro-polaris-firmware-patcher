import importlib.util
from pathlib import Path


def load_probe():
    path = Path(__file__).parents[1] / "scripts" / "canary-probe.py"
    spec = importlib.util.spec_from_file_location("canary_probe_bulb", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
