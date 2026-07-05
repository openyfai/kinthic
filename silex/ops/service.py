"""Platform service install helpers for 24/7 Kinthic daemon operation."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

SYSTEMD_UNIT_NAME = "kinthic-daemon.service"
LAUNCH_AGENT_LABEL = "ai.kinthic.daemon"


def _kinthic_executable() -> Path:
    """Resolve the kinthic CLI binary path."""
    which = shutil.which("kinthic")
    if which:
        return Path(which)
    venv_bin = Path.home() / ".kinthic" / "runtime" / "venv" / "bin" / "kinthic"
    if venv_bin.exists():
        return venv_bin
    return Path("kinthic")


def _systemd_unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / SYSTEMD_UNIT_NAME


def _launch_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


def render_systemd_unit() -> str:
    exec_path = _kinthic_executable()
    home = Path.home()
    return f"""[Unit]
Description=Kinthic background supervisor (gateway + workers)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={exec_path} daemon run
Restart=always
RestartSec=5
TimeoutStopSec=30
Environment=HOME={home}

[Install]
WantedBy=default.target
"""


def render_launch_agent_plist() -> str:
    exec_path = _kinthic_executable()
    home = str(Path.home())
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{LAUNCH_AGENT_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{exec_path}</string>
    <string>daemon</string>
    <string>run</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>{home}/.kinthic/logs/daemon.log</string>
  <key>StandardErrorPath</key>
  <string>{home}/.kinthic/logs/daemon.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key>
    <string>{home}</string>
  </dict>
</dict>
</plist>
"""


def is_service_installed() -> bool:
    system = platform.system()
    if system == "Linux":
        return _systemd_unit_path().exists()
    if system == "Darwin":
        return _launch_agent_path().exists()
    return False


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def _enable_linger_hint() -> str:
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    if not user:
        return ""
    return (
        f"\nOn headless servers, enable linger so the service survives logout:\n"
        f"  loginctl enable-linger {user}\n"
        f"(may require sudo)"
    )


def install_service(*, force: bool = False) -> tuple[bool, str]:
    system = platform.system()
    exec_path = _kinthic_executable()
    if not exec_path.exists() and shutil.which(str(exec_path)) is None:
        return False, f"kinthic executable not found at {exec_path}. Run the installer first."

    if system == "Linux":
        if not shutil.which("systemctl"):
            return False, "systemctl not found. Install systemd or run 'kinthic daemon run' in foreground."

        unit_path = _systemd_unit_path()
        if unit_path.exists() and not force:
            return False, f"Service already installed at {unit_path}. Use --force to overwrite."

        unit_path.parent.mkdir(parents=True, exist_ok=True)
        unit_path.write_text(render_systemd_unit(), encoding="utf-8")

        reload = _run(["systemctl", "--user", "daemon-reload"])
        if reload.returncode != 0:
            return False, f"systemctl daemon-reload failed: {reload.stderr.strip()}"

        enable = _run(["systemctl", "--user", "enable", "--now", SYSTEMD_UNIT_NAME])
        if enable.returncode != 0:
            return False, f"systemctl enable failed: {enable.stderr.strip()}"

        linger = _run(["loginctl", "enable-linger", os.environ.get("USER", "")])
        linger_note = ""
        if linger.returncode != 0:
            linger_note = _enable_linger_hint()

        from silex.utils.config import gateway_host, gateway_port
        port = gateway_port()
        host = gateway_host()
        return True, (
            f"Installed systemd user service: {unit_path}\n"
            f"Service is enabled and running.\n"
            f"Remote access (gateway binds to {host}):\n"
            f"  ssh -N -L {port}:{host}:{port} user@your-server"
            f"{linger_note}"
        )

    if system == "Darwin":
        plist_path = _launch_agent_path()
        if plist_path.exists() and not force:
            return False, f"LaunchAgent already installed at {plist_path}. Use --force to overwrite."

        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_path.write_text(render_launch_agent_plist(), encoding="utf-8")

        uid = os.getuid()
        domain = f"gui/{uid}"
        _run(["launchctl", "bootout", domain, str(plist_path)], check=False)
        load = _run(["launchctl", "bootstrap", domain, str(plist_path)])
        if load.returncode != 0:
            return False, f"launchctl bootstrap failed: {load.stderr.strip()}"

        return True, f"Installed LaunchAgent at {plist_path} and started the daemon."

    return False, (
        "Native service install is supported on Linux (systemd) and macOS (LaunchAgent).\n"
        "On Windows/WSL, use 'kinthic daemon install' inside WSL, or 'kinthic daemon run' in foreground."
    )


def uninstall_service() -> tuple[bool, str]:
    system = platform.system()

    if system == "Linux":
        unit_path = _systemd_unit_path()
        if not unit_path.exists():
            return False, "No systemd service installed."

        _run(["systemctl", "--user", "disable", "--now", SYSTEMD_UNIT_NAME], check=False)
        _run(["systemctl", "--user", "daemon-reload"], check=False)
        unit_path.unlink(missing_ok=True)
        return True, f"Removed systemd user service {SYSTEMD_UNIT_NAME}."

    if system == "Darwin":
        plist_path = _launch_agent_path()
        if not plist_path.exists():
            return False, "No LaunchAgent installed."

        uid = os.getuid()
        domain = f"gui/{uid}"
        _run(["launchctl", "bootout", domain, str(plist_path)], check=False)
        plist_path.unlink(missing_ok=True)
        return True, f"Removed LaunchAgent {LAUNCH_AGENT_LABEL}."

    return False, "No platform service to uninstall on this OS."


def start_service() -> tuple[bool, str]:
    system = platform.system()
    if system == "Linux" and _systemd_unit_path().exists():
        result = _run(["systemctl", "--user", "start", SYSTEMD_UNIT_NAME])
        if result.returncode == 0:
            return True, "Started kinthic-daemon via systemd."
        return False, f"systemctl start failed: {result.stderr.strip()}"
    if system == "Darwin" and _launch_agent_path().exists():
        uid = os.getuid()
        result = _run(["launchctl", "kickstart", "-k", f"gui/{uid}/{LAUNCH_AGENT_LABEL}"])
        if result.returncode == 0:
            return True, "Started kinthic daemon via LaunchAgent."
        return False, f"launchctl kickstart failed: {result.stderr.strip()}"
    return False, "Service not installed."


def stop_service() -> tuple[bool, str]:
    system = platform.system()
    if system == "Linux" and _systemd_unit_path().exists():
        result = _run(["systemctl", "--user", "stop", SYSTEMD_UNIT_NAME])
        if result.returncode == 0:
            return True, "Stopped kinthic-daemon via systemd."
        return False, f"systemctl stop failed: {result.stderr.strip()}"
    if system == "Darwin" and _launch_agent_path().exists():
        uid = os.getuid()
        result = _run(["launchctl", "bootout", f"gui/{uid}", str(_launch_agent_path())])
        if result.returncode == 0:
            return True, "Stopped kinthic daemon via LaunchAgent."
        return False, f"launchctl bootout failed: {result.stderr.strip()}"
    return False, "Service not installed."
