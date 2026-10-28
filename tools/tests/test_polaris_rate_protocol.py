import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from polaris_rate_protocol import (
    JOG_SPEED_MAX,
    ProtocolError,
    JogSafety,
    RateSafety,
    decode_jog_frame,
    decode_frame,
    encode_jog_frame,
    encode_frame,
)


def test_static_frame_shape_round_trips_little_endian_float():
    frame = encode_frame(2, -0.125)
    assert frame[:3] == b"\xac\x4a\x02"
    assert len(frame) == 7
    axis, rate = decode_frame(frame)
    assert axis == 2
    assert math.isclose(rate, -0.125, rel_tol=0, abs_tol=1e-7)


@pytest.mark.parametrize(
    "frame",
    [b"", b"\xac\x4a\x01\x00", b"\x00\x00\x01\x00\x00\x00\x00", b"\xac\x4a\x00\x00\x00\x00\x00"],
)
def test_malformed_frames_fail_closed(frame):
    with pytest.raises(ProtocolError):
        decode_frame(frame)


def test_watchdog_and_disconnect_force_all_axes_to_zero():
    safety = RateSafety(max_rate=1.0, max_accel=10.0, watchdog_s=0.5)
    safety.request(encode_frame(1, 0.2), now=0.0)
    assert safety.state().safe_stopped is False
    assert safety.tick(now=0.6).reason == "watchdog"
    assert safety.state().rates == {1: 0.0, 2: 0.0, 3: 0.0}

    safety.request(encode_frame(3, -0.1), now=1.0)
    assert safety.disconnect().reason == "link-disconnect"
    assert safety.state().rates == {1: 0.0, 2: 0.0, 3: 0.0}


def test_rate_limit_and_acceleration_limit_are_rejected():
    safety = RateSafety(max_rate=0.5, max_accel=1.0, watchdog_s=1.0)
    with pytest.raises(ProtocolError):
        safety.request(encode_frame(1, 0.6), now=0.0)
    safety.request(encode_frame(1, 0.2), now=0.0)
    with pytest.raises(ProtocolError):
        safety.request(encode_frame(1, 0.4), now=0.1)


def test_static_fast_jog_frame_round_trips_signed_int16():
    frame = encode_jog_frame(3, -1200)
    assert frame == b"\xac\x41\x03\x50\xfb"
    assert decode_jog_frame(frame) == (3, -1200)


@pytest.mark.parametrize(
    "frame",
    [b"\xac\x41\x01", b"\xac\x4a\x01\x00\x00", b"\xac\x41\x00\x00\x00"],
)
def test_fast_jog_malformed_frames_fail_closed(frame):
    with pytest.raises(ProtocolError):
        decode_jog_frame(frame)


def test_fast_jog_safety_enforces_observed_floor_limit_and_watchdog():
    safety = JogSafety(max_speed=JOG_SPEED_MAX, max_accel=10000.0, watchdog_s=0.4)
    safety.request_jog(encode_jog_frame(1, 1200), now=0.0)
    assert safety.state().safe_stopped is False
    with pytest.raises(ProtocolError):
        safety.request_jog(encode_jog_frame(1, 50), now=0.01)
    with pytest.raises(ProtocolError):
        safety.request_jog(encode_jog_frame(1, 2501), now=0.2)
    assert safety.tick(now=0.5).reason == "watchdog"
    assert safety.state().rates == {1: 0.0, 2: 0.0, 3: 0.0}


def test_fast_jog_zero_is_a_stop_for_the_selected_axis():
    safety = JogSafety(max_speed=JOG_SPEED_MAX, max_accel=10000.0, watchdog_s=0.4)
    safety.request_jog(encode_jog_frame(1, 1200), now=0.0)
    safety.request_jog(encode_jog_frame(2, -800), now=0.1)
    state = safety.request_jog(encode_jog_frame(1, 0), now=0.3)
    assert state.safe_stopped is False
    assert state.rates == {1: 0.0, 2: -800.0, 3: 0.0}
