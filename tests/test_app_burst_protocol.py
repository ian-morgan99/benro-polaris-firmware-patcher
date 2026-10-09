from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "app_burst_protocol", ROOT / "scripts" / "app-burst.py"
)
assert SPEC and SPEC.loader
APP_BURST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APP_BURST)


def test_camera_state_queries_use_the_app_type_one_wire_frame():
    for code in (265, 268, 275, 267, 266):
        assert APP_BURST.request_frame(code) == f"1&{code}&1&-1#"


def test_non_camera_state_queries_keep_type_two_wire_frame():
    for code in (286, 780, 284, 820, 823):
        assert APP_BURST.request_frame(code) == f"1&{code}&2&-100#"


def test_client_handshake_is_ordered_and_registers_app_identity():
    assert APP_BURST.CLIENT_HANDSHAKE == (
        "1&284&2&-100#",
        "1&820&2&-100#",
        "1&823&2&app:openpolaris-app-burst;ver:1;#",
    )


def test_frame_reader_preserves_coalesced_reply_for_next_query():
    class FakeSocket:
        def __init__(self):
            self.chunks = [b"780@sw:6.0.0.62;#266@state:1;#"]
            self.recv_calls = 0

        def settimeout(self, _timeout):
            pass

        def recv(self, _size):
            self.recv_calls += 1
            return self.chunks.pop(0) if self.chunks else b""

    sock = FakeSocket()
    reader = APP_BURST.FrameReader()

    assert reader.receive(sock, 780, APP_BURST.time.monotonic() + 1) == (
        "780@sw:6.0.0.62;"
    )
    assert reader.receive(sock, 266, APP_BURST.time.monotonic() + 1) == (
        "266@state:1;"
    )
    assert sock.recv_calls == 1


def test_frame_reader_retains_partial_frame_across_timeouts():
    class FakeSocket:
        def __init__(self):
            self.chunks = [b"266@state:", TimeoutError(), b"1;#"]

        def settimeout(self, _timeout):
            pass

        def recv(self, _size):
            item = self.chunks.pop(0) if self.chunks else b""
            if isinstance(item, Exception):
                raise item
            return item

    sock = FakeSocket()
    reader = APP_BURST.FrameReader()

    assert reader.receive(sock, 265, APP_BURST.time.monotonic() + 1) == ""
    assert reader.buffer == b"266@state:"
    assert reader.receive(sock, 266, APP_BURST.time.monotonic() + 1) == (
        "266@state:1;"
    )
