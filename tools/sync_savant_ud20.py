#!/usr/bin/env python3
"""Undefeated 2.0 Savant data bootstrap/sync.

Pulls the same validated current-season Savant datasets used by the protected
Challenger data repo, validates required columns/season, then atomically writes
active + LAST_GOOD copies under learning_data/.  This script is data-only and
never edits app.py or projection logic.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

SEASON = max(2026, datetime.now(timezone.utc).year)
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "learning_data"
BASE = "https://raw.githubusercontent.com/hernandezjh235-sudo/chanllger/main/learning_data"
FILES = {
    f"savant_batter_platoon_{SEASON}.csv": {"mlbam_id","player_name","season","vs_rhp_pa","vs_rhp_k_pct","vs_lhp_pa","vs_lhp_k_pct"},
    "savant_batter_profiles.csv": {"player_id","player_name","season","PA","SO","K%"},
    "savant_pitcher_stats.csv": {"player_id","player_name","season","PA","SO","K%"},
    "pitch_mix_matchups.csv": {"player_id","player_name","season","pitch_type","pitch_usage"},
}
HEADERS = {"User-Agent":"Mozilla/5.0 (compatible; Undefeated-2.0-Savant-Sync/1.0)"}


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fetch(name):
    url = f"{BASE}/{name}"
    r = requests.get(url, headers=HEADERS, timeout=(10,120))
    r.raise_for_status()
    text = (r.text or "").strip()
    if not text or "<html" in text[:300].lower():
        raise RuntimeError(f"{name}: non-CSV response")
    return pd.read_csv(io.StringIO(text), low_memory=False)


def validate(name, df, required):
    if df is None or df.empty:
        raise RuntimeError(f"{name}: empty")
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(f"{name}: missing columns {sorted(missing)}")
    seasons = set(pd.to_numeric(df["season"], errors="coerce").dropna().astype(int).tolist())
    if SEASON not in seasons:
        raise RuntimeError(f"{name}: current season {SEASON} missing")
    minimum = 300 if "pitch_mix" in name else 400
    if len(df) < minimum:
        raise RuntimeError(f"{name}: suspicious row count {len(df)}")


def atomic_csv(df, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name+".", suffix=".tmp", dir=str(path.parent))
    os.close(fd)
    try:
        df.to_csv(tmp, index=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    staged = {}
    try:
        for name, required in FILES.items():
            df = fetch(name)
            validate(name, df, required)
            staged[name] = df
        for name, df in staged.items():
            active = OUT / name
            last_good = OUT / name.replace(".csv", ".last_good.csv")
            atomic_csv(df, active)
            shutil.copy2(active, last_good)
        manifest = {
            "status":"CURRENT", "season":SEASON, "updated_at":now_iso(),
            "source":"VALIDATED_CHALLENGER_BASEBALL_SAVANT_FEED",
            "ud20":True, "files":{k:int(len(v)) for k,v in staged.items()},
        }
        (OUT/"savant_refresh_manifest.json").write_text(json.dumps(manifest, indent=2))
        (OUT/"savant_aux_refresh_manifest.json").write_text(json.dumps(manifest, indent=2))
        print("UD2 Savant sync READY", json.dumps(manifest))
        return 0
    except Exception as exc:
        # Non-destructive: keep any prior active/LAST_GOOD files. Railway startup
        # can continue; the app's normal fallback rules decide data authority.
        print(f"UD2 Savant sync WARNING: {exc}")
        return 0

if __name__ == "__main__":
    raise SystemExit(main())
