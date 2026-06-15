#!/usr/bin/env python3
import os
import shlex
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import streamlit as st


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from intellidj_common import cfg_get, load_project_config


def expand_path(value: str) -> Path:
    return Path(os.path.expanduser(value)).resolve()


def load_env(env_path: Path) -> dict:
    env = os.environ.copy()
    if not env_path.exists():
        return env
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        env[key] = value
    return env


def run_cmd_stream(label: str, cmd: list[str], env: dict) -> int:
    st.session_state.setdefault("logs", {})
    st.session_state.setdefault("codes", {})
    st.session_state.setdefault("commands", {})

    output = ""
    cmd_str = " ".join(shlex.quote(part) for part in cmd)
    st.session_state["commands"][label] = cmd_str

    with st.spinner(f"Running {label}..."):
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(REPO_ROOT),
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            msg = f"Failed to start command: {exc}"
            st.session_state["logs"][label] = msg
            st.session_state["codes"][label] = 127
            return 127

        if proc.stdout is None:
            st.session_state["logs"][label] = "Failed to capture output."
            st.session_state["codes"][label] = 1
            return 1

        for line in proc.stdout:
            output += line
        proc.stdout.close()
        rc = proc.wait()

    st.session_state["logs"][label] = output
    st.session_state["codes"][label] = rc
    return rc


def path_ok(path: Path, kind: str) -> bool:
    if kind == "file":
        return path.is_file()
    if kind == "dir":
        return path.is_dir()
    return path.exists()


def status_line(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        st.success(f"{label}: ready")
    else:
        msg = f"{label}: missing"
        if detail:
            msg = f"{msg} ({detail})"
        st.warning(msg)


def pick_folder_native(initial_dir: Path | None = None) -> str | None:
    if sys.platform == "darwin":
        default_clause = ""
        if initial_dir and initial_dir.exists():
            escaped = str(initial_dir).replace("\\", "\\\\").replace('"', '\\"')
            default_clause = f' default location POSIX file "{escaped}"'
        script_line = f'set chosenFolder to choose folder with prompt "Select local music folder"{default_clause}'
        cmd = ["osascript", "-e", script_line, "-e", "POSIX path of chosenFolder"]
        try:
            out = subprocess.check_output(cmd, text=True).strip()
        except subprocess.CalledProcessError:
            return None
        return out.rstrip("/") if out else None

    if sys.platform.startswith("win"):
        try:
            import tkinter as tk
            from tkinter import filedialog
        except Exception:
            return None
        root = tk.Tk()
        root.withdraw()
        selected = filedialog.askdirectory(
            title="Select local music folder",
            initialdir=str(initial_dir) if initial_dir else None,
        )
        root.destroy()
        return selected or None

    return None


def _get_fingerprint_count(db_path: Path) -> int:
    try:
        conn = sqlite3.connect(str(db_path))
        count = conn.execute(
            "SELECT COUNT(*) FROM library_fingerprints WHERE status = 'computed'"
        ).fetchone()[0]
        conn.close()
        return int(count)
    except Exception:
        return 0


st.set_page_config(page_title="IntelliDj Pipeline", layout="wide")
st.title("IntelliDj Pipeline")
st.caption("Guided local workflow with path validation and clear step-by-step actions.")

project_config = load_project_config()

st.session_state.setdefault("logs", {})
st.session_state.setdefault("codes", {})
st.session_state.setdefault("commands", {})
st.session_state.setdefault("env_path", str(REPO_ROOT / ".env"))
st.session_state.setdefault(
    "spotify_csv_path",
    str(REPO_ROOT / str(cfg_get(project_config, "paths.spotify_csv", "spotify_export.csv"))),
)
st.session_state.setdefault("source_csv_path", "")
st.session_state.setdefault("spotify_playlist_url", "")
st.session_state.setdefault("import_label", str(cfg_get(project_config, "pipeline.label", "")))
st.session_state.setdefault("processing_scope", str(cfg_get(project_config, "pipeline.scope", "new")))
st.session_state.setdefault("processing_batch_id", "")
st.session_state.setdefault("export_candidates_csv", False)
st.session_state.setdefault(
    "candidates_csv_path",
    str(REPO_ROOT / str(cfg_get(project_config, "paths.candidates_csv_export", "spotify_export_dj_candidates.csv"))),
)
st.session_state.setdefault("downloads_dir", str(cfg_get(project_config, "paths.downloads_dir", "~/Soulseek/downloads/complete")))
st.session_state.setdefault("inbox_dir", str(cfg_get(project_config, "paths.inbox_dir", "~/Music/DJ/inbox")))
st.session_state.setdefault("beets_config", str(cfg_get(project_config, "paths.beets_config", "~/.config/beets/config.yaml")))
st.session_state.setdefault("library_dir", str(cfg_get(project_config, "paths.library_dir", "~/Music/DJ/library")))
st.session_state.setdefault("custom_tags", True)
st.session_state.setdefault("use_report", True)
st.session_state.setdefault("report_path", str(REPO_ROOT / "tag_enrichment_report.csv"))
st.session_state.setdefault("download_limit", 0)
st.session_state.setdefault("download_dry_run", False)
st.session_state.setdefault("db_path", str(cfg_get(project_config, "db.path", str(REPO_ROOT / "intellidj.db"))))
st.session_state.setdefault("beets_preview", False)
st.session_state.setdefault("cover_art_force", bool(cfg_get(project_config, "cover_art.force", False)))
st.session_state.setdefault("cover_art_skip_embed", bool(cfg_get(project_config, "cover_art.skip_embed", False)))
st.session_state.setdefault("target_lufs", str(cfg_get(project_config, "loudnorm.target_lufs", "-9")))
st.session_state.setdefault("target_tp", str(cfg_get(project_config, "loudnorm.target_tp", "-1.0")))
st.session_state.setdefault("target_lra", str(cfg_get(project_config, "loudnorm.target_lra", "9")))
st.session_state.setdefault("scan_dir", str(cfg_get(project_config, "paths.scan_dir", "")))
st.session_state.setdefault("scan_dir_input", st.session_state["scan_dir"])
st.session_state.setdefault("scan_limit", 0)
st.session_state.setdefault("scan_dry_run", False)
# Fingerprint / library-check options
st.session_state.setdefault("fingerprint_on_scan", False)
st.session_state.setdefault("check_library_on_import", True)
st.session_state.setdefault("skip_if_in_library", True)
st.session_state.setdefault("inbox_move_mode", False)
st.session_state.setdefault("inbox_fingerprint", False)

if "scan_dir_pending" in st.session_state:
    pending = st.session_state.pop("scan_dir_pending")
    st.session_state["scan_dir"] = pending
    st.session_state["scan_dir_input"] = pending

with st.sidebar:
    st.header("Paths")
    st.text_input("Path to .env", key="env_path")
    st.text_input("Local scan directory (optional)", key="scan_dir_input")
    st.text_input("Spotify CSV (project)", key="spotify_csv_path")
    st.text_input("Source CSV path (optional copy source)", key="source_csv_path")
    st.text_input("slskd downloads directory", key="downloads_dir")
    st.text_input("Inbox / staging directory", key="inbox_dir")
    st.text_input("beets config path", key="beets_config")
    st.text_input("Music library directory", key="library_dir")

    st.header("Pipeline options")
    st.text_input("Batch label (optional)", key="import_label")
    st.checkbox("Optional CSV export after import", key="export_candidates_csv")
    st.text_input("Candidates CSV export path", key="candidates_csv_path", disabled=not st.session_state["export_candidates_csv"])
    st.selectbox(
        "Processing scope",
        options=["new", "existing", "all"],
        key="processing_scope",
        help="new = latest selected batch, existing = records outside that batch, all = everything in DB",
    )
    st.text_input("Processing batch id (optional)", key="processing_batch_id")
    st.text_input("Lifecycle DB path", key="db_path")

    st.header("Fingerprinting")
    st.checkbox("Fingerprint files during local scan", key="fingerprint_on_scan",
                help="Run fpcalc on each scanned file after indexing (requires: brew install chromaprint)")
    st.checkbox("Check library before generating candidates", key="check_library_on_import",
                help="Skip download if track is already found in local library by ISRC or artist+title")
    st.checkbox("Skip download if already in library", key="skip_if_in_library",
                help="Belt-and-suspenders check in the download step via library_files DB lookup")

    st.header("Advanced options")
    st.checkbox("Local scan dry-run", key="scan_dry_run")
    st.number_input("Local scan limit (0 = no limit)", min_value=0, step=1, key="scan_limit")
    st.checkbox("Download dry-run (no enqueue)", key="download_dry_run")
    st.number_input("Download limit (0 = no limit)", min_value=0, step=1, key="download_limit")
    st.checkbox("Move downloads to inbox (vs. copy)", key="inbox_move_mode",
                help="Default is copy for safety. Enable to move files instead.")
    st.checkbox("Fingerprint inbox files after staging", key="inbox_fingerprint")
    st.checkbox("Write custom Spotify tags", key="custom_tags")
    st.checkbox("Generate tag report", key="use_report")
    st.text_input("Tag report path", key="report_path")
    st.checkbox("Beets preview only (-p)", key="beets_preview")
    st.checkbox("Cover art force refresh", key="cover_art_force")
    st.checkbox("Cover art fetch only (skip embed)", key="cover_art_skip_embed")
    st.text_input("Loudnorm LUFS", key="target_lufs")
    st.text_input("Loudnorm True Peak", key="target_tp")
    st.text_input("Loudnorm LRA", key="target_lra")

st.session_state["scan_dir"] = st.session_state.get("scan_dir_input", "").strip()

env_path = expand_path(st.session_state["env_path"])
spotify_csv = expand_path(st.session_state["spotify_csv_path"])
source_csv = expand_path(st.session_state["source_csv_path"]) if st.session_state["source_csv_path"] else None
candidates_csv = expand_path(st.session_state["candidates_csv_path"])
downloads_dir = expand_path(st.session_state["downloads_dir"])
inbox_dir = expand_path(st.session_state["inbox_dir"])
beets_config = expand_path(st.session_state["beets_config"])
library_dir = expand_path(st.session_state["library_dir"])
report_path = expand_path(st.session_state["report_path"])
db_path = expand_path(st.session_state["db_path"])
scan_dir = expand_path(st.session_state["scan_dir"]) if st.session_state["scan_dir"] else None
env = load_env(env_path)
import_label = st.session_state["import_label"].strip() or None
processing_scope = st.session_state["processing_scope"]
processing_batch_id = None
raw_batch_id = st.session_state["processing_batch_id"].strip()
if raw_batch_id:
    try:
        processing_batch_id = int(raw_batch_id)
    except ValueError:
        processing_batch_id = None

env_ok = env_path.exists()
spotify_ok = path_ok(spotify_csv, "file")
db_ok = path_ok(db_path, "file")
downloads_ok = path_ok(downloads_dir, "dir")
inbox_ok = path_ok(inbox_dir, "dir")
beets_ok = path_ok(beets_config, "file")
library_ok = path_ok(library_dir, "dir")
scan_ok = path_ok(scan_dir, "dir") if scan_dir else False
api_key_ok = bool(env.get("SLSKD_API_KEY"))
fpcalc_ok = bool(shutil.which("fpcalc"))

tab_pipeline, tab_logs = st.tabs(["Pipeline", "Logs"])

with tab_pipeline:
    st.subheader("Quick Status")
    col_a, col_b = st.columns(2)
    with col_a:
        status_line("Environment file", env_ok, str(env_path))
        status_line("Local scan directory", scan_ok, str(scan_dir) if scan_dir else "")
        status_line("Spotify CSV", spotify_ok, str(spotify_csv))
        status_line("Downloads directory", downloads_ok, str(downloads_dir))
        status_line("fpcalc (Chromaprint)", fpcalc_ok, "brew install chromaprint" if not fpcalc_ok else "")
        if st.session_state["export_candidates_csv"]:
            status_line("Candidates CSV export", path_ok(candidates_csv, "file"), str(candidates_csv))
    with col_b:
        status_line("Lifecycle DB", db_ok, str(db_path))
        status_line("Inbox / staging directory", inbox_ok, str(inbox_dir))
        status_line("Beets config", beets_ok, str(beets_config))
        status_line("Library directory", library_ok, str(library_dir))
        if db_ok:
            fp_count = _get_fingerprint_count(db_path)
            st.info(f"Fingerprinted files in DB: {fp_count}")
    if api_key_ok:
        st.success("SLSKD_API_KEY found in environment")
    else:
        st.warning("SLSKD_API_KEY missing in environment or .env")

    if raw_batch_id and processing_batch_id is None:
        st.warning("Processing batch id must be an integer. It will be ignored until fixed.")

    st.divider()
    st.markdown("**Choose your ingestion path** — run Step 2A *or* 2B depending on your source:")

    with st.expander("Step 1: Load Spotify CSV (for Path B — Exportify)", expanded=False):
        st.write(f"Destination: `{spotify_csv}`")
        upload = st.file_uploader("Upload CSV", type=["csv"], key="upload_csv")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Save uploaded CSV", key="save_uploaded_csv"):
                if upload is None:
                    st.warning("Upload a CSV first.")
                else:
                    spotify_csv.parent.mkdir(parents=True, exist_ok=True)
                    spotify_csv.write_bytes(upload.getvalue())
                    st.success(f"Saved to {spotify_csv}")
        with c2:
            if st.button("Copy source CSV", key="copy_source_csv"):
                if source_csv is None:
                    st.warning("Set 'Source CSV path' in the sidebar.")
                elif not source_csv.exists():
                    st.error(f"Source CSV not found: {source_csv}")
                else:
                    spotify_csv.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(source_csv, spotify_csv)
                    st.success(f"Copied to {spotify_csv}")

    with st.expander("Step 2A: Scan local folder into DB (Path A — already on disk)", expanded=False):
        st.write("Use this if you already have music locally and want it tracked before or instead of CSV import.")
        st.write("Optionally computes Chromaprint fingerprints to enable duplicate prevention.")
        if scan_dir:
            st.write(f"Scan directory: `{scan_dir}`")
        if sys.platform == "darwin":
            if st.button("Select folder with Finder", key="pick_scan_dir_finder"):
                picked = pick_folder_native(scan_dir if scan_dir else Path.home())
                if picked:
                    st.session_state["scan_dir_pending"] = picked
                    st.success(f"Selected folder: {picked}")
                    st.rerun()
                else:
                    st.info("Folder selection canceled.")
        elif sys.platform.startswith("win"):
            if st.button("Select folder", key="pick_scan_dir_dialog"):
                picked = pick_folder_native(scan_dir if scan_dir else Path.home())
                if picked:
                    st.session_state["scan_dir_pending"] = picked
                    st.success(f"Selected folder: {picked}")
                    st.rerun()
                else:
                    st.info("Folder selection canceled.")
        can_run = scan_ok
        cmd = [
            "python",
            "scripts/scan_local_music.py",
            "--input-dir",
            str(scan_dir) if scan_dir else "",
            "--db-path",
            str(db_path),
        ]
        if import_label:
            cmd += ["--label", import_label]
        if st.session_state["scan_limit"] > 0:
            cmd += ["--limit", str(int(st.session_state["scan_limit"]))]
        if st.session_state["scan_dry_run"]:
            cmd.append("--dry-run")
        if st.session_state["fingerprint_on_scan"] and not st.session_state["scan_dry_run"]:
            cmd.append("--fingerprint")
            if not fpcalc_ok:
                st.warning("fpcalc not found — fingerprinting will be skipped. Install: `brew install chromaprint`")
        if st.button("Run scan_local_music.py", key="run_local_scan", disabled=not can_run):
            run_cmd_stream(label="scan_local_music", cmd=cmd, env=env)
        if not can_run:
            st.info("Step is blocked until local scan directory exists.")

    with st.expander("Step 2B: Import Spotify CSV into DB (Path B — Exportify)", expanded=True):
        st.write(f"Input: `{spotify_csv}`")
        if st.session_state["check_library_on_import"]:
            st.info("Library check enabled: tracks already in your local library will be marked and skipped for download.")
        if st.session_state["export_candidates_csv"]:
            st.write(f"Optional CSV export: `{candidates_csv}`")
        can_run = spotify_ok
        cmd = [
            "python",
            "csv_to_dj_pipeline.py",
            "--input",
            str(spotify_csv),
            "--db-path",
            str(db_path),
        ]
        if import_label:
            cmd += ["--label", import_label]
        if st.session_state["export_candidates_csv"]:
            cmd += ["--output", str(candidates_csv)]
        if st.session_state["check_library_on_import"]:
            cmd.append("--check-library")
        if st.button(
            "Run csv_to_dj_pipeline.py",
            key="run_candidates",
            disabled=not can_run,
        ):
            run_cmd_stream(label="csv_to_dj_pipeline", cmd=cmd, env=env)
        if not can_run:
            st.info("Step is blocked until Spotify CSV exists.")

    with st.expander("Step 2C: Import from Spotify (OAuth — alternative to 2B)", expanded=False):
        cache_exists = (REPO_ROOT / ".cache").exists()

        col_url, col_auth = st.columns([4, 1])
        with col_url:
            playlist_url = st.text_input(
                "Spotify playlist URL or ID",
                placeholder="https://open.spotify.com/playlist/...",
                key="spotify_playlist_url",
            ).strip()
        with col_auth:
            st.write("")  # vertical alignment spacer
            if cache_exists:
                st.success("Authenticated")
            else:
                st.warning("Not authenticated")

        if not cache_exists:
            st.info(
                "One-time setup: run this in your terminal to log in, then come back here.\n\n"
                "```\npython scripts/spotify_import.py --playlist URL --dry-run\n```"
            )

        can_run = bool(playlist_url) and cache_exists
        cmd = [
            "python",
            "scripts/spotify_import.py",
            "--playlist",
            playlist_url or "MISSING",
            "--db-path",
            str(db_path),
        ]
        if import_label:
            cmd += ["--label", import_label]
        if st.session_state["export_candidates_csv"]:
            cmd += ["--output", str(candidates_csv)]
        if st.session_state["check_library_on_import"]:
            cmd.append("--check-library")
        if st.button(
            "Import playlist into DB",
            key="run_spotify_oauth",
            disabled=not can_run,
        ):
            run_cmd_stream(label="spotify_oauth_import", cmd=cmd, env=env)

    with st.expander("Step 3: Fingerprint library (optional — enables duplicate prevention)", expanded=False):
        st.write("Compute Chromaprint fingerprints for all scanned library files.")
        st.write("Run this after Step 2A to enable audio-based duplicate detection before downloading.")
        st.write(f"Input directory: `{library_dir if not scan_dir else scan_dir}`")
        can_run = (scan_ok or library_ok) and fpcalc_ok
        fp_input = str(scan_dir) if scan_dir else str(library_dir)
        cmd = [
            "python",
            "intellidj_fingerprint.py",
            "--input-dir",
            fp_input,
            "--db-path",
            str(db_path),
        ]
        if import_label:
            cmd += ["--label", import_label]
        if processing_batch_id is not None:
            cmd += ["--batch-id", str(processing_batch_id)]
        if st.button("Run intellidj_fingerprint.py", key="run_fingerprint", disabled=not can_run):
            run_cmd_stream(label="fingerprint_library", cmd=cmd, env=env)
        if not fpcalc_ok:
            st.info("Requires fpcalc. Install: `brew install chromaprint` (macOS) or `apt install libchromaprint-tools` (Linux).")
        elif not can_run:
            st.info("Step is blocked until scan or library directory exists.")

    with st.expander("Step 4: Queue slskd downloads from DB", expanded=False):
        st.write(f"DB path: `{db_path}`")
        st.write(f"Scope: `{processing_scope}`")
        if st.session_state["skip_if_in_library"]:
            st.info("Skip-if-in-library enabled: tracks with an existing library file will not be queued.")
        can_run = db_ok and api_key_ok
        cmd = [
            "python",
            "dj_to_slskd_pipeline.py",
            "--db-path",
            str(db_path),
            "--scope",
            processing_scope,
        ]
        if import_label:
            cmd += ["--label", import_label]
        if processing_batch_id is not None:
            cmd += ["--batch-id", str(processing_batch_id)]
        if st.session_state["download_limit"] > 0:
            cmd += ["--limit", str(int(st.session_state["download_limit"]))]
        if st.session_state["download_dry_run"]:
            cmd.append("--dry-run")
        if st.session_state["skip_if_in_library"]:
            cmd.append("--skip-if-in-library")
        if st.button(
            "Run dj_to_slskd_pipeline.py",
            key="run_slskd",
            disabled=not can_run,
        ):
            run_cmd_stream(label="dj_to_slskd_pipeline", cmd=cmd, env=env)
        if not can_run:
            st.info("Step is blocked until lifecycle DB exists and SLSKD_API_KEY is configured.")

    with st.expander("Step 5: Move downloads to inbox (staging)", expanded=False):
        st.write("Move completed slskd downloads to the inbox for processing.")
        st.write(f"From: `{downloads_dir}`")
        st.write(f"To:   `{inbox_dir}`")
        can_run = downloads_ok
        cmd = [
            "python",
            "scripts/move_downloads_to_inbox.py",
            "--downloads-dir",
            str(downloads_dir),
            "--inbox-dir",
            str(inbox_dir),
            "--db-path",
            str(db_path),
        ]
        if import_label:
            cmd += ["--label", import_label]
        if st.session_state["inbox_move_mode"]:
            cmd.append("--move")
        if st.session_state["inbox_fingerprint"] and fpcalc_ok:
            cmd.append("--fingerprint")
        if st.button("Move downloads to inbox", key="run_move_to_inbox", disabled=not can_run):
            run_cmd_stream(label="move_to_inbox", cmd=cmd, env=env)
        if not can_run:
            st.info("Step is blocked until downloads directory exists.")

    with st.expander("Step 6: Enrich tags from DB metadata", expanded=False):
        st.write(f"DB path: `{db_path}`")
        st.write(f"Scope: `{processing_scope}`")
        st.write(f"Input directory: `{inbox_dir}`")
        can_run = (inbox_ok or downloads_ok) and db_ok
        effective_enrich_dir = str(inbox_dir) if inbox_ok else str(downloads_dir)
        cmd = [
            "python",
            "scripts/enrich_tags_from_spotify_csv.py",
            "--db-path",
            str(db_path),
            "--input-dir",
            effective_enrich_dir,
            "--scope",
            processing_scope,
        ]
        if import_label:
            cmd += ["--label", import_label]
        if processing_batch_id is not None:
            cmd += ["--batch-id", str(processing_batch_id)]
        if st.session_state["custom_tags"]:
            cmd.append("--custom-tags")
        if st.session_state["use_report"]:
            cmd += ["--report", str(report_path)]
        if st.button(
            "Run enrich_tags_from_spotify_csv.py",
            key="run_enrich",
            disabled=not can_run,
        ):
            run_cmd_stream(label="enrich_tags", cmd=cmd, env=env)
        if not can_run:
            st.info("Step is blocked until lifecycle DB and inbox (or downloads) directory exist.")

    with st.expander("Step 7: Import with beets", expanded=False):
        st.write(f"Config: `{beets_config}`")
        st.write(f"Source: `{inbox_dir}`")
        st.write(f"Scope: `{processing_scope}`")
        can_run = beets_ok and (inbox_ok or downloads_ok)
        effective_beets_dir = str(inbox_dir) if inbox_ok else str(downloads_dir)
        cmd = [
            "python",
            "scripts/run_beets_import.py",
            "--db-path",
            str(db_path),
            "--beets-config",
            str(beets_config),
            "--input-dir",
            effective_beets_dir,
            "--scope",
            processing_scope,
        ]
        if import_label:
            cmd += ["--label", import_label]
        if processing_batch_id is not None:
            cmd += ["--batch-id", str(processing_batch_id)]
        if st.session_state["beets_preview"]:
            cmd.append("--dry-run")
        if st.button(
            "Run beets import",
            key="run_beets",
            disabled=not can_run,
        ):
            run_cmd_stream(label="beets_import", cmd=cmd, env=env)
        if not can_run:
            st.info("Step is blocked until beets config and inbox (or downloads) directory exist.")

    with st.expander("Step 8: Fetch + embed cover art", expanded=False):
        st.write(f"Config: `{beets_config}`")
        st.write(f"Scope: `{processing_scope}`")
        can_run = beets_ok and db_ok
        cmd = [
            "python",
            "scripts/run_cover_art.py",
            "--db-path",
            str(db_path),
            "--beets-config",
            str(beets_config),
            "--scope",
            processing_scope,
        ]
        if import_label:
            cmd += ["--label", import_label]
        if processing_batch_id is not None:
            cmd += ["--batch-id", str(processing_batch_id)]
        if st.session_state["cover_art_force"]:
            cmd.append("--force")
        if st.session_state["cover_art_skip_embed"]:
            cmd.append("--skip-embed")
        if st.button(
            "Run cover art step",
            key="run_cover_art",
            disabled=not can_run,
        ):
            run_cmd_stream(label="cover_art", cmd=cmd, env=env)
        if not can_run:
            st.info("Step is blocked until beets config and lifecycle DB exist.")

    with st.expander("Step 9: Loudness normalize library", expanded=False):
        st.write(f"Library: `{library_dir}`")
        can_run = library_ok
        env2 = dict(env)
        env2["TARGET_LUFS"] = st.session_state["target_lufs"]
        env2["TARGET_TP"] = st.session_state["target_tp"]
        env2["TARGET_LRA"] = st.session_state["target_lra"]
        if st.button(
            "Run normalize_loudness.sh",
            key="run_loudnorm",
            disabled=not can_run,
        ):
            run_cmd_stream(
                label="loudnorm",
                cmd=["bash", "scripts/normalize_loudness.sh", "--input-dir", str(library_dir)],
                env=env2,
            )
        if not can_run:
            st.info("Step is blocked until library directory exists.")

with tab_logs:
    st.subheader("Command Logs")
    if st.button("Clear logs", key="clear_logs"):
        st.session_state["logs"] = {}
        st.session_state["codes"] = {}
        st.session_state["commands"] = {}
        st.success("Logs cleared.")

    labels = list(st.session_state.get("logs", {}).keys())
    if not labels:
        st.info("No command output yet. Run a step from the Pipeline tab.")
    else:
        selected = st.selectbox("Select command", options=list(reversed(labels)), key="selected_log")
        rc = st.session_state["codes"].get(selected, 0)
        cmd_display = st.session_state.get("commands", {}).get(selected, "")
        st.write(f"Exit code: `{rc}`")
        if cmd_display:
            st.code(cmd_display, language="bash")
        st.text_area(
            "Output",
            value=st.session_state["logs"].get(selected, ""),
            height=420,
            key=f"log_output_{selected}",
        )
