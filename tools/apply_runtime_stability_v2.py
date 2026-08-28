#!/usr/bin/env python3
"""UD2 runtime stability guard: prevents save/rerun actions from rebuilding heavy secondary markets.
Does not alter projection math or official outputs.
"""
from __future__ import annotations
import argparse, py_compile, tempfile
from pathlib import Path
MARKER = "UD2_RUNTIME_STABILITY_V2_2026_08_28"
TAB_ANCHOR = "tab_kproj, tab_brain, tab_beta_outs, tab_first_inning_k, tab_beta_ip_debug, tab_moneyline, tab_loss_lab, tab_iq, tab_30d_learning, tab_learning_lab, tab_calibration, tab2, tab3, tab4, tab5, tab6 = st.tabs(["
BLOCK = r'''
# =============================================================================
# UD2_RUNTIME_STABILITY_V2_2026_08_28
# UI/runtime-only. Saving or ordinary Streamlit reruns must not count as a board refresh.
# Heavy secondary tabs are deferred and same-board frames are cached by the actual
# board refresh generation. Projection formulas remain unchanged.
# =============================================================================
try:
    MERGE_V254_ENABLE_AUTO_LINEUP_REFRESH = False
except Exception:
    pass

def _ud2_board_generation():
    try:
        return str(st.session_state.get("last_refresh_time") or st.session_state.get("board_refresh_time") or "NO_BOARD")
    except Exception:
        return "NO_BOARD"

def _ud2_lazy(fn, state_key):
    if not callable(fn) or getattr(fn, "_ud2_stability_lazy", False):
        return fn
    def wrapped(*args, **kwargs):
        gen = _ud2_board_generation()
        active = str(st.session_state.get(state_key) or "") == gen
        if not active:
            return None
        return fn(*args, **kwargs)
    wrapped.__name__ = getattr(fn, "__name__", state_key)
    wrapped._ud2_stability_lazy = True
    return wrapped

for _nm, _key in (
    ("render_sports_analysis_brain_tab", "_ud2_load_brain"),
    ("render_beta_pitching_outs_tab", "_ud2_load_po"),
    ("render_first_inning_k_tab", "_ud2_load_fik"),
    ("render_beta_ip_debug_tab", "_ud2_load_ip"),
    ("render_moneyline_edge_tab", "_ud2_load_ml"),
    ("render_true_projection_loss_lab_tab", "_ud2_load_loss"),
    ("render_30_day_gamelog_learning_iq", "_ud2_load_30d"),
    ("render_learning_lab_tab", "_ud2_load_learning"),
    ("render_calibration_audit_tab", "_ud2_load_cal"),
    ("render_advanced_daily_data_hub", "_ud2_load_cal"),
):
    if _nm in globals() and callable(globals()[_nm]):
        globals()[_nm] = _ud2_lazy(globals()[_nm], _key)

try:
    st.caption("⚡ UD2 Stability V2 active · Save actions do not refresh the board · heavy secondary markets are isolated from ordinary reruns.")
except Exception:
    pass
'''.strip()

def patch_text(text: str) -> str:
    if MARKER in text:
        return text
    if TAB_ANCHOR not in text:
        raise RuntimeError("UD2 tabs anchor not found")
    i = text.index(TAB_ANCHOR)
    return text[:i] + BLOCK + "\n\n" + text[i:]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--app", default="app.py"); a = ap.parse_args()
    p = Path(a.app); src = p.read_text(encoding="utf-8"); out = patch_text(src)
    if out != src: p.write_text(out, encoding="utf-8")
    with tempfile.TemporaryDirectory() as td:
        py_compile.compile(str(p), cfile=str(Path(td)/"app.pyc"), doraise=True)
    print("UD2 Runtime Stability V2 READY")
if __name__ == "__main__": main()
