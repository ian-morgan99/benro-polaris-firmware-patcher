import importlib.util
import socket
import threading
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "control_liveness",
    Path(__file__).parents[1] / "scripts" / "control-liveness.py",
)
probe_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe_mod)


# --- pure classification -----------------------------------------------------

def test_connect_failure_is_refused_not_unresponsive():
    """A refused port is a different fault from a silent one; conflating them
    hides the #182 wedge behind a plain 'device down'."""
    assert probe_mod.classify("ConnectionRefusedError", None) == "refused"
    assert probe_mod.classify(None, None) == "unresponsive"


def test_only_the_requested_code_counts_as_healthy():
    assert probe_mod.classify(None, probe_mod.PROBE_COMMAND) == "healthy"
    # A reply to some other code means the socket works but the probe did not
    # get its answer; that must not be reported as healthy.
    assert probe_mod.classify(None, 780) == "protocol_error"


def test_probe_command_is_the_read_only_state_query():
    """284 is what went unanswered during the soak wedge, and it triggers nothing."""
    assert probe_mod.PROBE_COMMAND == 284


def test_frame_parsing_accepts_both_wire_shapes():
    assert probe_mod.parse_frame("284@mode:1;state:0;") == (284, "mode:1;state:0;")
    assert probe_mod.parse_frame("1&284&2&mode:1;state:0;") == (284, "mode:1;state:0;")
    assert probe_mod.parse_frame("garbage") is None
    assert probe_mod.parse_frame("") is None


# --- socket-level behaviour, against a local fake ----------------------------

def _serve(handler, sock):
    try:
        handler(sock)
    except OSError:
        pass
    finally:
        sock.close()


def _listen():
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    return srv


def test_healthy_server_is_measured_with_latency():
    srv = _listen()
    port = srv.getsockname()[1]

    def accept_and_reply(server):
        conn, _ = server.accept()
        conn.recv(4096)
        conn.sendall(b"284@mode:1;state:0;#")
        conn.close()

    t = threading.Thread(target=_serve, args=(accept_and_reply, srv), daemon=True)
    t.start()
    state, elapsed, detail = probe_mod.probe("127.0.0.1", port, 3.0)
    t.join(timeout=3)
    assert state == "healthy", detail
    assert "state:0" in detail
    assert elapsed < 3.0


def test_server_that_accepts_but_never_replies_is_unresponsive():
    """This is the #182 signature: connect succeeds, so a TCP check alone would
    call the service alive."""
    srv = _listen()
    port = srv.getsockname()[1]
    held = []

    def accept_and_stall(server):
        conn, _ = server.accept()
        held.append(conn)  # keep it open, send nothing

    t = threading.Thread(target=_serve, args=(accept_and_stall, srv), daemon=True)
    t.start()
    state, elapsed, _ = probe_mod.probe("127.0.0.1", port, 0.6)
    assert state == "unresponsive"
    assert elapsed >= 0.6
    for conn in held:
        conn.close()
    srv.close()


def test_closed_socket_before_reply_is_a_protocol_error():
    srv = _listen()
    port = srv.getsockname()[1]

    def accept_and_close(server):
        conn, _ = server.accept()
        conn.close()

    t = threading.Thread(target=_serve, args=(accept_and_close, srv), daemon=True)
    t.start()
    state, _, detail = probe_mod.probe("127.0.0.1", port, 2.0)
    t.join(timeout=2)
    assert state == "protocol_error", detail
    srv.close()


def test_unsolicited_frames_do_not_masquerade_as_a_reply():
    """The device emits notifications around a session; only 284 satisfies the probe."""
    srv = _listen()
    port = srv.getsockname()[1]

    def accept_and_notify(server):
        conn, _ = server.accept()
        conn.recv(4096)
        conn.sendall(b"775@status:1;freespace:1;#")
        conn.recv(4096)
        conn.close()

    def driver(server):
        # first attempt gets only a notification -> must not be called healthy
        conn, _ = server.accept()
        conn.recv(4096)
        conn.sendall(b"775@status:1;freespace:1;#")
        conn.close()

    t = threading.Thread(target=driver, args=(srv,), daemon=True)
    t.start()
    state, _, _ = probe_mod.probe("127.0.0.1", port, 1.0)
    assert state in ("unresponsive", "protocol_error")
    srv.close()


def test_refused_connection_is_reported_as_refused():
    """A port nothing listens on must be distinguishable from a silent service."""
    srv = _listen()
    port = srv.getsockname()[1]
    srv.close()  # free the port so connect() is refused
    state, _, detail = probe_mod.probe("127.0.0.1", port, 1.0)
    assert state == "refused"
    assert "Refused" in detail or "refused" in detail.lower()


def test_main_maps_states_to_stable_exit_codes():
    srv = _listen()
    port = srv.getsockname()[1]
    srv.close()
    code = probe_mod.main(["--host", "127.0.0.1", "--port", str(port),
                           "--timeout", "0.5", "--iface", "", "--quiet"])
    assert code == probe_mod.EXIT_REFUSED == 2
    assert probe_mod.EXIT_HEALTHY == 0
    assert probe_mod.EXIT_UNRESPONSIVE == 1
    assert probe_mod.EXIT_PROTOCOL_ERROR == 3


# --- wrong-network guard -----------------------------------------------------
# 192.168.0.1 is shared with the home router. On 2026-10-09 the Wi-Fi dropped to
# the LAN and the probe reported `refused` for ~40 minutes about a device that
# was never unreachable. A liveness probe must not call the router "service down".

def test_route_interface_reports_the_device_used(monkeypatch):
    def fake_run(cmd, **kwargs):
        assert cmd[:3] == ["ip", "-o", "route"]
        return __import__("subprocess").CompletedProcess(
            cmd, 0,
            "192.168.0.1 via 192.168.68.1 dev enp11s0 src 192.168.68.89\n", "")
    monkeypatch.setattr(probe_mod.subprocess, "run", fake_run)
    assert probe_mod.route_interface("192.168.0.1") == "enp11s0"


def test_route_interface_is_none_when_ip_is_unavailable(monkeypatch):
    def boom(*a, **k):
        raise OSError("no ip command")
    monkeypatch.setattr(probe_mod.subprocess, "run", boom)
    assert probe_mod.route_interface("192.168.0.1") is None


def test_main_refuses_to_report_on_the_wrong_network(monkeypatch, capsys):
    monkeypatch.setattr(probe_mod, "route_interface", lambda host: "enp11s0")
    # probe() would say `refused` here; that verdict must never be reached.
    monkeypatch.setattr(probe_mod, "probe",
                        lambda *a, **k: ("refused", 0.0, "would be a false alarm"))
    code = probe_mod.main(["--host", "192.168.0.1", "--port", "9090"])
    assert code == probe_mod.EXIT_WRONG_NETWORK == 4
    out = capsys.readouterr().out
    assert "wrong_network" in out and "enp11s0" in out


def test_main_probes_normally_when_the_route_is_correct(monkeypatch):
    monkeypatch.setattr(probe_mod, "route_interface", lambda host: "wlp8s0")
    monkeypatch.setattr(probe_mod, "probe", lambda *a, **k: ("healthy", 0.02, "ok"))
    assert probe_mod.main(["--host", "192.168.0.1", "--port", "9090", "--quiet"]) == 0


def test_route_check_can_be_skipped_for_non_gimbal_targets(monkeypatch):
    monkeypatch.setattr(probe_mod, "route_interface", lambda host: "enp11s0")
    monkeypatch.setattr(probe_mod, "probe", lambda *a, **k: ("healthy", 0.01, "ok"))
    assert probe_mod.main(["--host", "127.0.0.1", "--port", "1", "--iface", "",
                           "--quiet"]) == 0
