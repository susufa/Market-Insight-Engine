"""
tests/integration/test_acquisition_standalone_cli.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Integration tests for CLI execution commands:
`health`, `status`, `cleanup-zombies`
"""

import os
import subprocess
import sys
from pathlib import Path


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    proj_root = Path(__file__).resolve().parent.parent.parent
    python_exe = proj_root / ".venv" / "Scripts" / "python.exe"
    exe = str(python_exe) if python_exe.exists() else sys.executable
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{proj_root / 'src'}{os.pathsep}{proj_root}"
    cmd = [exe, "-m", "src.acquisition.cli"] + list(args)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(proj_root),
        env=env,
    )


def test_cli_help():
    """Verify CLI help exits with 0."""
    res = run_cli("--help")
    assert res.returncode == 0
    assert "Market Insight Engine - Modular Data Acquisition CLI" in res.stdout


def test_cli_health_command():
    """Verify CLI health command checks providers."""
    res = run_cli("health")
    assert res.returncode == 0
    assert "akshare" in res.stdout


def test_cli_cleanup_zombies_command():
    """Verify CLI cleanup-zombies runs cleanly."""
    res = run_cli("cleanup-zombies")
    assert res.returncode == 0
    assert "Zombie Task Sweep complete" in res.stdout
