#!/usr/bin/env python3
from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app.py"
RUNTIME = ROOT / "runtime_app.py"

# Keep the pushed app.py untouched. All deployment-only guards are layered onto
# a fresh runtime copy so future app.py uploads remain the source of truth.
shutil.copy2(SOURCE, RUNTIME)

PATCHES = [
    "tools/apply_runtime_stability_v1.py",
    "tools/apply_runtime_stability_v2.py",
    "tools/apply_manual_refresh_state_v2.py",
    "tools/apply_savant_manual_only_v3.py",
    "tools/apply_ud20_opponent_k_pipeline_cleanup_v1.py",
]

for rel in PATCHES:
    script = ROOT / rel
    if not script.exists():
        raise FileNotFoundError(f"Required runtime patch missing: {rel}")
    subprocess.run(
        [sys.executable, str(script), "--app", str(RUNTIME)],
        cwd=str(ROOT),
        check=True,
    )

py_compile.compile(str(RUNTIME), doraise=True)

os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")
os.environ.setdefault("STREAMLIT_SERVER_RUN_ON_SAVE", "false")
port = str(os.environ.get("PORT") or "8080")

cmd = [
    "streamlit", "run", str(RUNTIME),
    "--server.port", port,
    "--server.address", "0.0.0.0",
    "--server.headless", "true",
    "--server.fileWatcherType", "none",
    "--server.runOnSave", "false",
]
os.execvp(cmd[0], cmd)
