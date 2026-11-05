import json
import os
import subprocess
import sys
from pathlib import Path


def run_cli(*args: str) -> tuple[int, dict]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    src_dir = str(Path(__file__).resolve().parents[1] / "src")
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else src_dir
    cmd = [sys.executable, "-m", "film_date_agent.cli", *args, "--json"]
    proc = subprocess.run(cmd, capture_output=True, env=env)
    stdout_text = proc.stdout.decode("utf-8", errors="replace")
    data = json.loads(stdout_text)
    return proc.returncode, data


def test_cli_doctor():
    code, data = run_cli("doctor")
    assert code == 0
    assert data["ok"] is True
    assert "checks" in data


def test_cli_capabilities():
    code, data = run_cli("capabilities")
    assert code == 0
    assert data["ok"] is True
    assert "axes" in data
    assert "presets" in data


def test_cli_presets_list():
    code, data = run_cli("presets", "list")
    assert code == 0
    assert data["ok"] is True
    assert len(data["presets"]) >= 12


def test_cli_apply_dry_run(sample_image: Path):
    code, data = run_cli("apply", str(sample_image), "--dry-run")
    assert code == 0
    assert data["ok"] is True
    assert data["dry_run"] is True


def test_cli_invalid_input():
    code, data = run_cli("apply", "non_existent_image_12345.png")
    assert code != 0
    assert data["ok"] is False
    assert data["error"]["code"] == "input_not_found"
