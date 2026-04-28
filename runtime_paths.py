import hashlib
import os
import tempfile
from pathlib import Path


NAME = os.environ.get("BU_NAME", "default")


def _safe_name(name=None):
    raw = name or NAME
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in raw)


def runtime_dir():
    override = os.environ.get("BH_RUNTIME_DIR") or os.environ.get("BROWSER_HARNESS_RUNTIME_DIR")
    if override:
        root = Path(override).expanduser()
    elif os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or tempfile.gettempdir()) / "browser-harness"
    else:
        root = Path(tempfile.gettempdir()) / "browser-harness"
    root.mkdir(parents=True, exist_ok=True)
    return root


def transport():
    requested = (os.environ.get("BH_TRANSPORT") or "").strip().lower()
    if requested in {"tcp", "unix"}:
        return requested
    return "tcp" if os.name == "nt" else "unix"


def tcp_port(name=None):
    if os.environ.get("BU_PORT"):
        return int(os.environ["BU_PORT"])
    safe = _safe_name(name)
    if safe == "default":
        return 9330
    digest = hashlib.sha1(safe.encode()).digest()
    return 9331 + int.from_bytes(digest[:2], "big") % 1000


def daemon_paths(name=None):
    safe = _safe_name(name)
    root = runtime_dir()
    return {
        "sock": root / f"bu-{safe}.sock",
        "pid": root / f"bu-{safe}.pid",
        "log": root / f"bu-{safe}.log",
    }


def daemon_endpoint(name=None):
    if transport() == "tcp":
        return ("tcp", "127.0.0.1", tcp_port(name))
    return ("unix", str(daemon_paths(name)["sock"]))


def endpoint_description(name=None):
    endpoint = daemon_endpoint(name)
    if endpoint[0] == "tcp":
        return f"{endpoint[1]}:{endpoint[2]}"
    return endpoint[1]


def version_cache_path():
    return runtime_dir() / "bu-version-cache.json"


def screenshot_path(name):
    return runtime_dir() / name


def chrome_debug_profile_dir(profile_name="default"):
    return runtime_dir() / f"chrome-profile-{_safe_name(profile_name)}"


def chrome_profile_candidates():
    return [
        chrome_debug_profile_dir("default"),
        Path.home() / "Library/Application Support/Google/Chrome",
        Path.home() / "Library/Application Support/Comet",
        Path.home() / "Library/Application Support/Microsoft Edge",
        Path.home() / "Library/Application Support/Microsoft Edge Beta",
        Path.home() / "Library/Application Support/Microsoft Edge Dev",
        Path.home() / "Library/Application Support/Microsoft Edge Canary",
        Path.home() / ".config/google-chrome",
        Path.home() / ".config/chromium",
        Path.home() / ".config/chromium-browser",
        Path.home() / ".config/microsoft-edge",
        Path.home() / ".config/microsoft-edge-beta",
        Path.home() / ".config/microsoft-edge-dev",
        Path.home() / ".var/app/org.chromium.Chromium/config/chromium",
        Path.home() / ".var/app/com.google.Chrome/config/google-chrome",
        Path.home() / ".var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser",
        Path.home() / ".var/app/com.microsoft.Edge/config/microsoft-edge",
        Path.home() / "AppData/Local/Google/Chrome/User Data",
        Path.home() / "AppData/Local/Chromium/User Data",
        Path.home() / "AppData/Local/Microsoft/Edge/User Data",
        Path.home() / "AppData/Local/Microsoft/Edge Beta/User Data",
        Path.home() / "AppData/Local/Microsoft/Edge Dev/User Data",
        Path.home() / "AppData/Local/Microsoft/Edge SxS/User Data",
    ]
