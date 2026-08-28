#!/usr/bin/env python3
"""Undefeated 2.0 live Savant refresh used only by Refresh Live Board.

This no longer copies potentially stale Challenger GitHub CSV snapshots. Instead it
runs the same validated Challenger Savant refresher against Baseball Savant into a
staging directory, validates the outputs, then atomically publishes them to UD2's
learning_data. Projection code is never edited.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

SEASON = max(2026, datetime.now(timezone.utc).year)
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "learning_data"
RAW_TOOLS = "https://raw.githubusercontent.com/hernandezjh235-sudo/chanllger/main/tools"
REFRESH_SCRIPTS = [
    "refresh_savant_installer.py",
    "refresh_savant_installer_v2.py",
    "refresh_savant_installer_v3.py",
    "refresh_savant_installer_v4.py",
    "refresh_savant_installer_v5.py",
    "refresh_savant_installer_v6.py",
    "refresh_savant_installer_v7.py",
]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Undefeated-2.0-Live-Savant/2.0)"}


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _download_refresh_scripts(dst: Path):
    for name in REFRESH_SCRIPTS:
        url = f"{RAW_TOOLS}/{name}"
        r = requests.get(url, headers=HEADERS, timeout=(10, 90))
        r.raise_for_status()
        text = r.text or ""
        if len(text) < 100 or "<!doctype" in text[:300].lower() or "<html" in text[:300].lower():
            raise RuntimeError(f"invalid refresh script response: {name}")
        (dst / name).write_text(text, encoding="utf-8")


def _validate_staged(stage: Path):
    active = [
        f"savant_batter_platoon_{SEASON}.csv",
        "savant_batter_profiles.csv",
        "savant_pitcher_stats.csv",
        "pitch_mix_matchups.csv",
    ]
    minimums = {
        active[0]: 400,
        active[1]: 400,
        active[2]: 400,
        active[3]: 300,
    }
    required = {
        active[0]: {"mlbam_id", "player_name", "season", "vs_rhp_pa", "vs_rhp_k_pct", "vs_lhp_pa", "vs_lhp_k_pct"},
        active[1]: {"player_name", "season"},
        active[2]: {"player_name", "season"},
        active[3]: {"player_name", "season"},
    }
    counts = {}
    for name in active:
        p = stage / name
        lg = stage / name.replace(".csv", ".last_good.csv")
        if not p.exists() or p.stat().st_size <= 20:
            raise RuntimeError(f"missing/empty live Savant file: {name}")
        if not lg.exists() or lg.stat().st_size <= 20:
            raise RuntimeError(f"missing LAST_GOOD file: {lg.name}")
        df = pd.read_csv(p, low_memory=False)
        if len(df) < minimums[name]:
            raise RuntimeError(f"{name}: suspicious row count {len(df)}")
        missing = required[name] - set(df.columns)
        if missing:
            raise RuntimeError(f"{name}: missing columns {sorted(missing)}")
        seasons = set(pd.to_numeric(df["season"], errors="coerce").dropna().astype(int).tolist())
        if SEASON not in seasons:
            raise RuntimeError(f"{name}: season {SEASON} missing")
        counts[name] = len(df)
    return counts


def _publish(stage: Path, counts: dict):
    OUT.mkdir(parents=True, exist_ok=True)
    names = [
        f"savant_batter_platoon_{SEASON}.csv",
        f"savant_batter_platoon_{SEASON}.last_good.csv",
        "savant_batter_profiles.csv",
        "savant_batter_profiles.last_good.csv",
        "savant_pitcher_stats.csv",
        "savant_pitcher_stats.last_good.csv",
        "pitch_mix_matchups.csv",
        "pitch_mix_matchups.last_good.csv",
    ]
    for name in names:
        src = stage / name
        dst = OUT / name
        fd, tmp = tempfile.mkstemp(prefix=dst.name + ".", suffix=".tmp", dir=str(OUT))
        os.close(fd)
        try:
            shutil.copy2(src, tmp)
            os.replace(tmp, dst)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    # Normalize UD2 manifests after the validated live refresh.
    manifest = {
        "status": "CURRENT",
        "season": SEASON,
        "updated_at": now_iso(),
        "last_success_at": now_iso(),
        "source": "LIVE_BASEBALL_SAVANT_DIRECT_VIA_VALIDATED_CHALLENGER_REFRESHER",
        "ud20": True,
        "refresh_policy": "BOARD_REFRESH_ONLY",
        "files": counts,
    }
    for name in ("savant_refresh_manifest.json", "savant_aux_refresh_manifest.json"):
        dst = OUT / name
        tmp = dst.with_suffix(dst.suffix + ".tmp")
        tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        os.replace(tmp, dst)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="ud2_live_savant_") as td:
            work = Path(td)
            scripts = work / "tools"
            stage = work / "learning_data"
            scripts.mkdir(parents=True, exist_ok=True)
            stage.mkdir(parents=True, exist_ok=True)
            _download_refresh_scripts(scripts)
            cmd = [
                sys.executable,
                str(scripts / "refresh_savant_installer_v5.py"),
                "--out",
                str(stage),
            ]
            proc = subprocess.run(
                cmd,
                cwd=str(scripts),
                capture_output=True,
                text=True,
                timeout=690,
            )
            if proc.returncode != 0:
                raise RuntimeError((proc.stderr or proc.stdout or "live refresher failed")[-1600:])
            counts = _validate_staged(stage)
            _publish(stage, counts)
            print("UD2 live Savant refresh READY", json.dumps(counts))
            return 0
    except Exception as exc:
        # Non-destructive: prior validated active/LAST_GOOD data remains intact.
        print(f"UD2 live Savant refresh WARNING: {type(exc).__name__}: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
