import subprocess
import sys
from pathlib import Path


def get_version() -> str:
    path = Path(__file__).parent.parent / "VERSION"
    try:
        return path.read_text().strip()
    except Exception:
        return "0.0.0"


def get_python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def get_podman_version() -> str:
    try:
        r = subprocess.run(["podman", "--version"], capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else "N/A"
    except Exception:
        return "N/A"


APP_VERSION = get_version()
COMPONENTS = {
    "backend": APP_VERSION,
    "collector": APP_VERSION,
    "ai_worker": APP_VERSION,
    "schema": 1,
    "python": get_python_version(),
    "podman": get_podman_version(),
}
