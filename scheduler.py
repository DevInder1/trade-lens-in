import os
import plistlib
import subprocess
import sys
from pathlib import Path

from storage import APP_DIR, LOGS_DIR, ensure_dirs

LABEL = "in.tradelens.daily-report"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG = LOGS_DIR / "daily.log"


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _python() -> str:
    venv = APP_DIR / ".venv" / "bin" / "python"
    return str(venv if venv.exists() else Path(sys.executable))


def _launchctl(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True, check=False)


def status() -> dict:
    if not PLIST.exists():
        return {"enabled": False}
    try:
        data = plistlib.loads(PLIST.read_bytes())
        when = data["StartCalendarInterval"][0]
    except Exception:
        return {"enabled": False}
    loaded = _launchctl("print", f"{_domain()}/{LABEL}").returncode == 0
    return {"enabled": loaded, "hour": when["Hour"], "minute": when["Minute"]}


def enable(hour: int, minute: int) -> None:
    ensure_dirs()
    disable()
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    job = {
        "Label": LABEL,
        "ProgramArguments": [_python(), str(APP_DIR / "daily_report.py")],
        "WorkingDirectory": str(APP_DIR),
        "StartCalendarInterval": [{"Weekday": day, "Hour": hour, "Minute": minute} for day in range(1, 6)],
        "StandardOutPath": str(LOG),
        "StandardErrorPath": str(LOG),
        "RunAtLoad": False,
    }
    PLIST.write_bytes(plistlib.dumps(job))
    result = _launchctl("bootstrap", _domain(), str(PLIST))
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "launchctl could not schedule the report")


def disable() -> None:
    _launchctl("bootout", f"{_domain()}/{LABEL}")
    PLIST.unlink(missing_ok=True)


def last_log_lines(count: int = 15) -> str:
    try:
        return "\n".join(LOG.read_text(encoding="utf-8").splitlines()[-count:])
    except OSError:
        return ""
