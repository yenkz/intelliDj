#!/usr/bin/env python3
import os
import shutil
import subprocess
from pathlib import Path

import streamlit as st


REPO_ROOT = Path(__file__).resolve().parents[1]


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


def run_cmd_stream(label: str, cmd: list[str], env: dict) -> None:
    st.session_state.setdefault("logs", {})
    st.session_state.setdefault("codes", {})
    output = ""
    display = st.empty()
    status = st.empty()
    with st.spinner(f"Running {label}..."):
        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        if proc.stdout is None:
            st.error("Failed to capture output.")
            return
        for line in proc.stdout:
            output += line
            tail = "\n".join(output.splitlines()[-200:])
            display.code(tail)
        proc.stdout.close()
        rc = proc.wait()
    st.session_state["logs"][label] = output
    st.session_state["codes"][label] = rc
    if rc == 0:
        status.success(f"{label} completed")
    else:
        status.error(f"{label} failed with exit {rc}")


st.set_page_config(page_title="IntelliDj Pipeline", layout="wide")
st.title("IntelliDj Pipeline")
st.caption("Local, step-by-step UI for the IntelliDj workflow.")

with st.sidebar:
    st.header("Paths")
    env_path = st.text_input("Path to .env", value=str(REPO_ROOT / ".env"))
    spotify_csv_path = st.text_input("Project Spotify CSV", value=str(REPO_ROOT / "spotify_export.csv"))
    source_csv_path = st.text_input("Source CSV path (optional)", value="")
    candidates_csv_path = st.text_input("Candidates CSV", value=str(REPO_ROOT / "dj_candidates.csv"))
    downloads_dir = st.text_input("slskd downloads", value="~/Soulseek/downloads/complete")
    beets_config = st.text_input("beets config", value="~/.config/beets/config.yaml")
    library_dir = st.text_input("music library", value="~/Music/DJ/library")

    st.header("Options")
    custom_tags = st.checkbox("Write custom Spotify tags", value=True)
    report_path = st.text_input("Tag report (optional)", value=str(REPO_ROOT / "tag_enrichment_report.csv"))
    use_report = st.checkbox("Generate tag report", value=True)
    download_limit = st.number_input("Download limit (0 = no limit)", min_value=0, value=0, step=1)
    beets_preview = st.checkbox("Beets preview only (-p)", value=False)

    st.header("Loudnorm targets")
    target_lufs = st.text_input("LUFS", value="-9")
    target_tp = st.text_input("True Peak", value="-1.0")
    target_lra = st.text_input("LRA", value="9")


env = load_env(expand_path(env_path))

col1, col2 = st.columns(2)

with col1:
    st.subheader("Step 1: Load Spotify CSV")
    upload = st.file_uploader("Upload spotify_export.csv", type=["csv"])
    if st.button("Save uploaded CSV to project"):
        if upload is None:
            st.warning("Upload a CSV first.")
        else:
            dest = expand_path(spotify_csv_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(upload.getvalue())
            st.success(f"Saved to {dest}")
    if st.button("Copy source CSV to project"):
        if not source_csv_path:
            st.warning("Enter a source CSV path first.")
        else:
            src = expand_path(source_csv_path)
            dest = expand_path(spotify_csv_path)
            if not src.exists():
                st.error(f"Source CSV not found: {src}")
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, dest)
                st.success(f"Copied to {dest}")

    st.subheader("Step 2: Generate dj_candidates.csv")
    if st.button("Run csv_to_dj_pipeline.py"):
        run_cmd_stream("csv_to_dj_pipeline", ["python", "csv_to_dj_pipeline.py"], env)

    st.subheader("Step 3: Download via slskd")
    if st.button("Run dj_to_slskd_pipeline.py"):
        cmd = ["python", "dj_to_slskd_pipeline.py", "--csv", str(expand_path(candidates_csv_path))]
        if download_limit and int(download_limit) > 0:
            cmd += ["--limit", str(int(download_limit))]
        run_cmd_stream("dj_to_slskd_pipeline", cmd, env)

with col2:
    st.subheader("Step 4: Enrich tags from Spotify CSV")
    if st.button("Run enrich_tags_from_spotify_csv.py"):
        cmd = [
            "python",
            "scripts/enrich_tags_from_spotify_csv.py",
            "--csv",
            str(expand_path(spotify_csv_path)),
            "--input-dir",
            str(expand_path(downloads_dir)),
        ]
        if custom_tags:
            cmd.append("--custom-tags")
        if use_report and report_path:
            cmd += ["--report", str(expand_path(report_path))]
        run_cmd_stream("enrich_tags", cmd, env)

    st.subheader("Step 5: Beets import")
    if st.button("Run beets import"):
        cmd = [
            "beet",
            "-c",
            str(expand_path(beets_config)),
            "import",
            "-s",
            str(expand_path(downloads_dir)),
        ]
        if beets_preview:
            cmd.insert(-1, "-p")
        run_cmd_stream("beets_import", cmd, env)

    st.subheader("Step 6: Loudness normalization")
    if st.button("Run loudnorm (in-place)"):
        env2 = dict(env)
        env2["TARGET_LUFS"] = target_lufs
        env2["TARGET_TP"] = target_tp
        env2["TARGET_LRA"] = target_lra
        cmd = ["bash", "scripts/normalize_loudness.sh", "--input-dir", str(expand_path(library_dir))]
        run_cmd_stream("loudnorm", cmd, env2)


st.subheader("Command Output")
for label, output in st.session_state.get("logs", {}).items():
    code = st.session_state.get("codes", {}).get(label, 0)
    status = "ok" if code == 0 else f"exit {code}"
    st.text_area(f"{label} ({status})", value=output, height=220)
