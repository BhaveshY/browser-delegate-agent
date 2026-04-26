import sys
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch
import run


def test_c_flag_executes_code():
    stdout = StringIO()
    with patch.object(sys, "argv", ["browser-harness", "-c", "print('hello from -c')"]), \
         patch("run.ensure_daemon"), \
         patch("run.print_update_banner"), \
         patch("sys.stdout", stdout):
        run.main()
    assert stdout.getvalue().strip() == "hello from -c"


def test_c_flag_does_not_read_stdin():
    stdin_read = []
    fake_stdin = StringIO("should not be read")
    fake_stdin.read = lambda: stdin_read.append(True) or ""

    with patch.object(sys, "argv", ["browser-harness", "-c", "x = 1"]), \
         patch("run.ensure_daemon"), \
         patch("run.print_update_banner"), \
         patch("sys.stdin", fake_stdin):
        run.main()

    assert not stdin_read, "stdin should not be read when -c is passed"


def test_stdin_executes_code():
    stdout = StringIO()
    stdin = StringIO("print('hello from stdin')")

    with patch.object(sys, "argv", ["browser-harness"]), \
         patch("run.ensure_daemon"), \
         patch("run.print_update_banner"), \
         patch("sys.stdin", stdin), \
         patch("sys.stdout", stdout):
        run.main()

    assert stdout.getvalue().strip() == "hello from stdin"


def test_delegate_subcommand_dispatches(monkeypatch):
    seen = {}
    def fake_delegate(argv):
        seen["argv"] = argv
        return 0
    fake = SimpleNamespace(run_delegate_cli=fake_delegate)
    monkeypatch.setitem(sys.modules, "delegate", fake)

    with patch.object(sys, "argv", ["browser-harness", "delegate", "do", "thing"]):
        try:
            run.main()
        except SystemExit as e:
            assert e.code == 0

    assert seen["argv"] == ["do", "thing"]


def test_bootstrap_subcommand_dispatches(monkeypatch):
    seen = {}
    def fake_bootstrap(argv):
        seen["argv"] = argv
        return 0
    fake = SimpleNamespace(run_bootstrap_cli=fake_bootstrap)
    monkeypatch.setitem(sys.modules, "bootstrap", fake)

    with patch.object(sys, "argv", ["browser-harness", "--bootstrap", "--no-demo"]):
        try:
            run.main()
        except SystemExit as e:
            assert e.code == 0

    assert seen["argv"] == ["--no-demo"]
