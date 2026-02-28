#!/usr/bin/env python3
import os
import shlex
import subprocess
import sys
from pathlib import Path

import streamlit as st


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "find_duplicate_tracks.py"
IS_MACOS = sys.platform == "darwin"


def expand_path(value: str) -> Path:
    return Path(os.path.expanduser(value)).resolve()


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


def run_cmd_stream(label: str, cmd: list[str]) -> int:
    st.session_state.setdefault("dup_logs", {})
    st.session_state.setdefault("dup_codes", {})
    st.session_state.setdefault("dup_commands", {})

    output = ""
    cmd_str = " ".join(shlex.quote(part) for part in cmd)
    st.session_state["dup_commands"][label] = cmd_str

    with st.spinner(f"Running {label}..."):
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(REPO_ROOT),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            msg = f"Failed to start command: {exc}"
            st.session_state["dup_logs"][label] = msg
            st.session_state["dup_codes"][label] = 127
            return 127

        if proc.stdout is None:
            st.session_state["dup_logs"][label] = "Failed to capture output."
            st.session_state["dup_codes"][label] = 1
            return 1

        for line in proc.stdout:
            output += line
        proc.stdout.close()
        rc = proc.wait()

    st.session_state["dup_logs"][label] = output
    st.session_state["dup_codes"][label] = rc
    return rc


def _finder_script_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _run_finder_script(script: str) -> str | None:
    if not IS_MACOS:
        return None
    try:
        completed = subprocess.run(
            ["osascript", "-e", script],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    output = completed.stdout.strip()
    return output or None


def browse_folder(prompt: str) -> str | None:
    script = f'return POSIX path of (choose folder with prompt "{_finder_script_escape(prompt)}")'
    return _run_finder_script(script)


def browse_save_file(prompt: str, default_name: str) -> str | None:
    script = (
        f'return POSIX path of (choose file name with prompt "{_finder_script_escape(prompt)}" '
        f'default name "{_finder_script_escape(default_name)}")'
    )
    return _run_finder_script(script)


def queue_widget_update(widget_key: str, value: str) -> None:
    st.session_state[f"_pending_{widget_key}"] = value


def apply_pending_widget_updates(widget_keys: list[str]) -> None:
    for key in widget_keys:
        pending_key = f"_pending_{key}"
        pending_value = st.session_state.get(pending_key)
        if pending_value:
            st.session_state[key] = pending_value
            st.session_state[pending_key] = ""


st.set_page_config(page_title="IntelliDj Duplicate Finder", layout="wide")
st.title("IntelliDj Duplicate Finder")
st.caption("Guided duplicate detection workflow with ordered setup, safety gates, and logs.")

st.session_state.setdefault("dup_logs", {})
st.session_state.setdefault("dup_codes", {})
st.session_state.setdefault("dup_commands", {})
st.session_state.setdefault("dup_source_dir", "~/Music/DJ/library")
st.session_state.setdefault("dup_use_compare_dir", True)
st.session_state.setdefault("dup_compare_dir", "~/Soulseek/downloads/complete")
st.session_state.setdefault("dup_action", "report")
st.session_state.setdefault("dup_keep_strategy", "best")
st.session_state.setdefault("dup_delete_from", "compare")
st.session_state.setdefault("dup_review_dir", "~/Music/DJ/review_duplicates")
st.session_state.setdefault("dup_report_write_file", True)
st.session_state.setdefault("dup_report_format", "csv")
st.session_state.setdefault("dup_report_path", str(REPO_ROOT / "reports" / "duplicates.csv"))
st.session_state.setdefault("dup_dry_run", True)
st.session_state.setdefault("dup_match_mode", "hybrid")
st.session_state.setdefault("dup_duration_bucket_seconds", 2)
st.session_state.setdefault("dup_cleanup_empty_dirs", True)
st.session_state.setdefault("dup_confirm_changes", False)
st.session_state.setdefault("dup_run_counter", 0)
st.session_state.setdefault("_pending_dup_source_dir", "")
st.session_state.setdefault("_pending_dup_compare_dir", "")
st.session_state.setdefault("_pending_dup_review_dir", "")
st.session_state.setdefault("_pending_dup_report_path", "")

apply_pending_widget_updates(
    ["dup_source_dir", "dup_compare_dir", "dup_review_dir", "dup_report_path"]
)

tab_pipeline, tab_logs = st.tabs(["Pipeline", "Logs"])

with tab_pipeline:
    with st.expander("0) Select Action and Keep Policy", expanded=True):
        st.selectbox(
            "Action to perform",
            options=["report", "move", "delete"],
            key="dup_action",
        )
        st.selectbox(
            "Keep policy",
            options=["best", "newest", "oldest"],
            key="dup_keep_strategy",
        )
        if st.session_state["dup_action"] == "report":
            st.checkbox("Write report output file", key="dup_report_write_file")
            if st.session_state["dup_report_write_file"]:
                st.selectbox("Output format", options=["csv", "json"], key="dup_report_format")
                col_path, col_browse = st.columns([6, 1])
                with col_path:
                    st.text_input("Output file path", key="dup_report_path")
                with col_browse:
                    if IS_MACOS and st.button("Browse", key="dup_browse_report"):
                        extension = ".csv" if st.session_state["dup_report_format"] == "csv" else ".json"
                        chosen = browse_save_file("Select report output file", f"duplicates{extension}")
                        if chosen:
                            queue_widget_update("dup_report_path", chosen)
                            st.rerun()
        if st.session_state["dup_action"] == "move":
            col_path, col_browse = st.columns([6, 1])
            with col_path:
                st.text_input("Review folder (duplicates moved here)", key="dup_review_dir")
            with col_browse:
                if IS_MACOS and st.button("Browse", key="dup_browse_review"):
                    chosen = browse_folder("Select review folder")
                    if chosen:
                        queue_widget_update("dup_review_dir", chosen)
                        st.rerun()

    with st.expander("1) Select Source and Compare Folders", expanded=True):
        col_path, col_browse = st.columns([6, 1])
        with col_path:
            st.text_input("Source folder", key="dup_source_dir")
        with col_browse:
            if IS_MACOS and st.button("Browse", key="dup_browse_source"):
                chosen = browse_folder("Select source folder")
                if chosen:
                    queue_widget_update("dup_source_dir", chosen)
                    st.rerun()
        st.checkbox("Use compare folder", key="dup_use_compare_dir")
        if st.session_state["dup_use_compare_dir"]:
            col_path, col_browse = st.columns([6, 1])
            with col_path:
                st.text_input("Compare folder", key="dup_compare_dir")
            with col_browse:
                if IS_MACOS and st.button("Browse", key="dup_browse_compare"):
                    chosen = browse_folder("Select compare folder")
                    if chosen:
                        queue_widget_update("dup_compare_dir", chosen)
                        st.rerun()
            if st.session_state["dup_action"] == "delete":
                st.selectbox(
                    "If deleting, delete from",
                    options=["compare", "source"],
                    key="dup_delete_from",
                    help="The opposite side will be kept.",
                )

    with st.expander("2) Safe Preview (Dry Run)", expanded=True):
        st.checkbox("Dry run (safe preview)", key="dup_dry_run")
        if st.session_state["dup_dry_run"]:
            st.info("Dry run enabled: no files will be changed.")
        else:
            st.warning("Dry run disabled: selected action may modify files.")

    with st.expander("3) Matching Strategy", expanded=False):
        st.selectbox("Matching mode", options=["hybrid", "hash", "metadata"], key="dup_match_mode")
        st.number_input(
            "Duration bucket seconds (metadata mode)",
            min_value=1,
            max_value=30,
            step=1,
            key="dup_duration_bucket_seconds",
        )

    with st.expander("4) Safety Parameters", expanded=False):
        if st.session_state["dup_action"] in {"move", "delete"}:
            st.checkbox(
                "Remove empty parent folders after move/delete",
                key="dup_cleanup_empty_dirs",
            )
        destructive = st.session_state["dup_action"] in {"move", "delete"} and not st.session_state["dup_dry_run"]
        if destructive:
            st.checkbox("I understand this can modify files", key="dup_confirm_changes")
        else:
            st.info("No destructive confirmation needed for report or dry-run mode.")

    source_dir = expand_path(st.session_state["dup_source_dir"])
    use_compare_dir = st.session_state["dup_use_compare_dir"]
    compare_dir = expand_path(st.session_state["dup_compare_dir"]) if use_compare_dir else None
    review_dir = expand_path(st.session_state["dup_review_dir"])
    report_path = expand_path(st.session_state["dup_report_path"])

    script_ok = path_ok(SCRIPT_PATH, "file")
    source_ok = path_ok(source_dir, "dir")
    compare_ok = (not use_compare_dir) or (compare_dir is not None and path_ok(compare_dir, "dir"))
    review_ok = (st.session_state["dup_action"] != "move") or bool(st.session_state["dup_review_dir"].strip())
    report_ok = (
        st.session_state["dup_action"] != "report"
        or (not st.session_state["dup_report_write_file"])
        or bool(st.session_state["dup_report_path"].strip())
    )
    destructive = st.session_state["dup_action"] in {"move", "delete"} and not st.session_state["dup_dry_run"]
    confirmed = (not destructive) or st.session_state["dup_confirm_changes"]

    prefer_origin = None
    if use_compare_dir and st.session_state["dup_action"] == "delete":
        if st.session_state["dup_delete_from"] == "source":
            prefer_origin = "compare"
        else:
            prefer_origin = "source"

    cmd = [
        "python",
        "scripts/find_duplicate_tracks.py",
        "--source-dir",
        str(source_dir),
        "--match-mode",
        st.session_state["dup_match_mode"],
        "--duration-bucket-seconds",
        str(int(st.session_state["dup_duration_bucket_seconds"])),
        "--action",
        st.session_state["dup_action"],
        "--keep-strategy",
        st.session_state["dup_keep_strategy"],
    ]
    if use_compare_dir and compare_dir is not None:
        cmd += ["--compare-dir", str(compare_dir)]
    if prefer_origin:
        cmd += ["--prefer-origin", prefer_origin]
    if st.session_state["dup_action"] == "move":
        cmd += ["--review-dir", str(review_dir)]
    if st.session_state["dup_action"] in {"move", "delete"} and st.session_state["dup_cleanup_empty_dirs"]:
        cmd.append("--cleanup-empty-dirs")
    if st.session_state["dup_dry_run"]:
        cmd.append("--dry-run")
    elif st.session_state["dup_action"] in {"move", "delete"}:
        cmd.append("--yes")
    if st.session_state["dup_action"] == "report" and st.session_state["dup_report_write_file"]:
        if st.session_state["dup_report_format"] == "csv":
            cmd += ["--export-csv", str(report_path)]
        else:
            cmd += ["--export-json", str(report_path)]

    st.subheader("Quick Status")
    left, right = st.columns(2)
    with left:
        status_line("Duplicate script", script_ok, str(SCRIPT_PATH))
        status_line("Source folder", source_ok, str(source_dir))
        if use_compare_dir and compare_dir is not None:
            status_line("Compare folder", compare_ok, str(compare_dir))
    with right:
        status_line("Action config", review_ok, "review folder required for move")
        status_line("Report config", report_ok, "output file path required when enabled")
        if destructive:
            status_line("Destructive confirmation", confirmed, "check safety confirmation")
        else:
            st.success("Safety mode: report or dry-run")

    with st.expander("Command Preview", expanded=True):
        st.code(" ".join(shlex.quote(part) for part in cmd), language="bash")

    with st.expander("Run", expanded=True):
        can_run = script_ok and source_ok and compare_ok and review_ok and report_ok and confirmed
        if st.button("Run find_duplicate_tracks.py", disabled=not can_run, key="dup_run_button"):
            st.session_state["dup_run_counter"] += 1
            label = f"find_duplicate_tracks#{st.session_state['dup_run_counter']}"
            run_cmd_stream(label=label, cmd=cmd)
        if not can_run:
            st.info("Run is blocked until required paths and safety options are valid.")

with tab_logs:
    st.subheader("Command Logs")
    if st.button("Clear logs", key="dup_clear_logs"):
        st.session_state["dup_logs"] = {}
        st.session_state["dup_codes"] = {}
        st.session_state["dup_commands"] = {}
        st.success("Logs cleared.")

    labels = list(st.session_state.get("dup_logs", {}).keys())
    if not labels:
        st.info("No command output yet. Run a step from the Pipeline tab.")
    else:
        selected = st.selectbox("Select command", options=list(reversed(labels)), key="dup_selected_log")
        rc = st.session_state["dup_codes"].get(selected, 0)
        cmd_display = st.session_state.get("dup_commands", {}).get(selected, "")
        st.write(f"Exit code: `{rc}`")
        if cmd_display:
            st.code(cmd_display, language="bash")
        st.text_area(
            "Output",
            value=st.session_state["dup_logs"].get(selected, ""),
            height=420,
            key=f"dup_log_output_{selected}",
        )
