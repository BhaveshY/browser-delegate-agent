def test_default_endpoint_is_tcp_on_windows(monkeypatch):
    import runtime_paths

    monkeypatch.setattr(runtime_paths.os, "name", "nt")
    monkeypatch.delenv("BH_TRANSPORT", raising=False)

    endpoint = runtime_paths.daemon_endpoint("default")

    assert endpoint == ("tcp", "127.0.0.1", 9330)


def test_transport_override_can_force_tcp(monkeypatch):
    import runtime_paths

    monkeypatch.setenv("BH_TRANSPORT", "tcp")

    endpoint = runtime_paths.daemon_endpoint("work")

    assert endpoint[0] == "tcp"
    assert endpoint[1] == "127.0.0.1"


def test_runtime_dir_honors_override(monkeypatch, tmp_path):
    import runtime_paths

    monkeypatch.setenv("BH_RUNTIME_DIR", str(tmp_path / "bh-runtime"))

    assert runtime_paths.runtime_dir() == tmp_path / "bh-runtime"
