#!/usr/bin/env python3
import os
import shlex
import shutil
import subprocess
from pathlib import Path

import streamlit as st


REPO_ROOT = Path(__file__).resolve().parents[1]


def expand_path(value: str) -> Path:
    return Path(os.path.expanduser(value)).resolve()


def default_candidates_for_input(spotify_csv: str) -> str:
    input_path = expand_path(spotify_csv)
    return str(input_path.with_name(f"{input_path.stem}_dj_candidates.csv"))


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


st.set_page_config(page_title="IntelliDj Pipeline", layout="wide")
st.title("IntelliDj Pipeline")
st.caption("Guided local workflow with path validation and clear step-by-step actions.")

st.session_state.setdefault("logs", {})
st.session_state.setdefault("codes", {})
st.session_state.setdefault("commands", {})
st.session_state.setdefault("env_path", str(REPO_ROOT / ".env"))
st.session_state.setdefault("spotify_csv_path", str(REPO_ROOT / "spotify_export.csv"))
st.session_state.setdefault("source_csv_path", "")
st.session_state.setdefault("auto_candidates", True)
st.session_state.setdefault("manual_candidates_csv_path", str(REPO_ROOT / "dj_candidates.csv"))
st.session_state.setdefault("downloads_dir", "~/Soulseek/downloads/complete")
st.session_state.setdefault("beets_config", "~/.config/beets/config.yaml")
st.session_state.setdefault("library_dir", "~/Music/DJ/library")
st.session_state.setdefault("custom_tags", True)
st.session_state.setdefault("use_report", True)
st.session_state.setdefault("report_path", str(REPO_ROOT / "tag_enrichment_report.csv"))
st.session_state.setdefault("download_limit", 0)
st.session_state.setdefault("download_dry_run", False)
st.session_state.setdefault("beets_preview", False)
st.session_state.setdefault("target_lufs", "-9")
st.session_state.setdefault("target_tp", "-1.0")
st.session_state.setdefault("target_lra", "9")

with st.sidebar:
    st.header("Configuration")
    st.text_input("Path to .env", key="env_path")
    st.text_input("Spotify CSV (project)", key="spotify_csv_path")
    st.text_input("Source CSV path (optional copy source)", key="source_csv_path")
    st.checkbox("Auto candidates filename from Spotify CSV", key="auto_candidates")
    if st.session_state["auto_candidates"]:
        auto_out = default_candidates_for_input(st.session_state["spotify_csv_path"])
        st.text_input("Candidates CSV", value=auto_out, disabled=True)
    else:
        st.text_input("Candidates CSV", key="manual_candidates_csv_path")
    st.text_input("slskd downloads directory", key="downloads_dir")
    st.text_input("beets config path", key="beets_config")
    st.text_input("music library directory", key="library_dir")

    st.header("Options")
    st.checkbox("Download dry-run (no enqueue)", key="download_dry_run")
    st.number_input("Download limit (0 = no limit)", min_value=0, step=1, key="download_limit")
    st.checkbox("Write custom Spotify tags", key="custom_tags")
    st.checkbox("Generate tag report", key="use_report")
    st.text_input("Tag report path", key="report_path")
    st.checkbox("Beets preview only (-p)", key="beets_preview")
    st.text_input("Loudnorm LUFS", key="target_lufs")
    st.text_input("Loudnorm True Peak", key="target_tp")
    st.text_input("Loudnorm LRA", key="target_lra")

candidates_csv_path = (
    default_candidates_for_input(st.session_state["spotify_csv_path"])
    if st.session_state["auto_candidates"]
    else st.session_state["manual_candidates_csv_path"]
)

env_path = expand_path(st.session_state["env_path"])
spotify_csv = expand_path(st.session_state["spotify_csv_path"])
source_csv = expand_path(st.session_state["source_csv_path"]) if st.session_state["source_csv_path"] else None
candidates_csv = expand_path(candidates_csv_path)
downloads_dir = expand_path(st.session_state["downloads_dir"])
beets_config = expand_path(st.session_state["beets_config"])
library_dir = expand_path(st.session_state["library_dir"])
report_path = expand_path(st.session_state["report_path"])
env = load_env(env_path)

env_ok = env_path.exists()
spotify_ok = path_ok(spotify_csv, "file")
candidates_ok = path_ok(candidates_csv, "file")
downloads_ok = path_ok(downloads_dir, "dir")
beets_ok = path_ok(beets_config, "file")
library_ok = path_ok(library_dir, "dir")
api_key_ok = bool(env.get("SLSKD_API_KEY"))

tab_pipeline, tab_logs = st.tabs(["Pipeline", "Logs"])

with tab_pipeline:
    st.subheader("Quick Status")
    col_a, col_b = st.columns(2)
    with col_a:
        status_line("Environment file", env_ok, str(env_path))
        status_line("Spotify CSV", spotify_ok, str(spotify_csv))
        status_line("Candidates CSV", candidates_ok, str(candidates_csv))
    with col_b:
        status_line("Downloads directory", downloads_ok, str(downloads_dir))
        status_line("Beets config", beets_ok, str(beets_config))
        status_line("Library directory", library_ok, str(library_dir))
    if api_key_ok:
        st.success("SLSKD_API_KEY found in environment")
    else:
        st.warning("SLSKD_API_KEY missing in environment or .env")

    with st.expander("Step 1: Load Spotify CSV", expanded=True):
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

    with st.expander("Step 2: Generate download candidates", expanded=True):
        st.write(f"Input: `{spotify_csv}`")
        st.write(f"Output: `{candidates_csv}`")
        can_run = spotify_ok
        if st.button(
            "Run csv_to_dj_pipeline.py",
            key="run_candidates",
            disabled=not can_run,
        ):
            run_cmd_stream(
                label="csv_to_dj_pipeline",
                cmd=[
                    "python",
                    "csv_to_dj_pipeline.py",
                    "--input",
                    str(spotify_csv),
                    "--output",
                    str(candidates_csv),
                ],
                env=env,
            )
        if not can_run:
            st.info("Step is blocked until Spotify CSV exists.")

    with st.expander("Step 3: Queue slskd downloads", expanded=False):
        st.write(f"Input CSV: `{candidates_csv}`")
        can_run = candidates_ok and api_key_ok
        cmd = ["python", "dj_to_slskd_pipeline.py", "--csv", str(candidates_csv)]
        if st.session_state["download_limit"] > 0:
            cmd += ["--limit", str(int(st.session_state["download_limit"]))]
        if st.session_state["download_dry_run"]:
            cmd.append("--dry-run")
        if st.button(
            "Run dj_to_slskd_pipeline.py",
            key="run_slskd",
            disabled=not can_run,
        ):
            run_cmd_stream(label="dj_to_slskd_pipeline", cmd=cmd, env=env)
        if not can_run:
            st.info("Step is blocked until candidates CSV exists and SLSKD_API_KEY is configured.")

    with st.expander("Step 4: Enrich tags from Spotify CSV", expanded=False):
        st.write(f"CSV: `{spotify_csv}`")
        st.write(f"Input directory: `{downloads_dir}`")
        can_run = spotify_ok and downloads_ok
        cmd = [
            "python",
            "scripts/enrich_tags_from_spotify_csv.py",
            "--csv",
            str(spotify_csv),
            "--input-dir",
            str(downloads_dir),
        ]
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
            st.info("Step is blocked until Spotify CSV and downloads directory exist.")

    with st.expander("Step 5: Import with beets", expanded=False):
        st.write(f"Config: `{beets_config}`")
        st.write(f"Source: `{downloads_dir}`")
        can_run = beets_ok and downloads_ok
        cmd = ["beet", "-c", str(beets_config), "import", "-s", str(downloads_dir)]
        if st.session_state["beets_preview"]:
            cmd.insert(-1, "-p")
        if st.button(
            "Run beets import",
            key="run_beets",
            disabled=not can_run,
        ):
            run_cmd_stream(label="beets_import", cmd=cmd, env=env)
        if not can_run:
            st.info("Step is blocked until beets config and downloads directory exist.")

    with st.expander("Step 6: Loudness normalize library", expanded=False):
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
