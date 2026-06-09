import csv
import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from mutagen import File as MutagenFile


AUDIO_EXTENSIONS = {
    ".mp3",
    ".flac",
    ".wav",
    ".aif",
    ".aiff",
    ".m4a",
    ".aac",
    ".ogg",
    ".opus",
    ".wma",
}


@dataclass(frozen=True)
class TrackFile:
    path: Path
    origin: str
    size_bytes: int
    mtime: float
    duration_sec: Optional[float]
    bitrate_kbps: Optional[int]
    sample_rate: Optional[int]
    bits_per_sample: Optional[int]
    artist: Optional[str]
    title: Optional[str]
    file_hash: Optional[str]


@dataclass(frozen=True)
class Decision:
    group_id: int
    role: str
    action: str
    origin: str
    path: str
    target_path: str
    keep_path: str
    keep_strategy: str
    reason: str


class UnionFind:
    def __init__(self, size: int):
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, item: int) -> int:
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if self.rank[left_root] < self.rank[right_root]:
            self.parent[left_root] = right_root
        elif self.rank[left_root] > self.rank[right_root]:
            self.parent[right_root] = left_root
        else:
            self.parent[right_root] = left_root
            self.rank[left_root] += 1


def normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    text = value.lower().strip()
    text = re.sub(r"\(.*?\)|\[.*?\]|\{.*?\}", " ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _coerce_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _extract_tag(tags, key: str) -> Optional[str]:
    if not tags:
        return None
    key_lower = key.lower()
    for tag_key in tags.keys():
        if str(tag_key).lower() != key_lower:
            continue
        value = tags.get(tag_key)
        if isinstance(value, list):
            return str(value[0]).strip() if value else None
        if value is None:
            return None
        return str(value).strip()
    return None


def extract_track(path: Path, origin: str, include_hash: bool) -> TrackFile:
    stats = path.stat()
    duration_sec = None
    bitrate_kbps = None
    sample_rate = None
    bits_per_sample = None
    artist = None
    title = None

    try:
        audio = MutagenFile(path, easy=True)
    except Exception:
        audio = None

    if audio is not None:
        info = getattr(audio, "info", None)
        tags = getattr(audio, "tags", None)
        if info is not None:
            duration_sec = getattr(info, "length", None)
            bitrate = getattr(info, "bitrate", None)
            sample_rate = _coerce_int(getattr(info, "sample_rate", None))
            bits_per_sample = _coerce_int(getattr(info, "bits_per_sample", None))
            if bitrate is not None:
                try:
                    bitrate_kbps = int(round(float(bitrate) / 1000))
                except Exception:
                    bitrate_kbps = None
        artist = _extract_tag(tags, "artist")
        title = _extract_tag(tags, "title")

    file_hash = compute_sha256(path) if include_hash else None
    return TrackFile(
        path=path,
        origin=origin,
        size_bytes=stats.st_size,
        mtime=stats.st_mtime,
        duration_sec=duration_sec,
        bitrate_kbps=bitrate_kbps,
        sample_rate=sample_rate,
        bits_per_sample=bits_per_sample,
        artist=artist,
        title=title,
        file_hash=file_hash,
    )


def collect_tracks(directory: Path, origin: str, include_hash: bool) -> List[TrackFile]:
    tracks: List[TrackFile] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        tracks.append(extract_track(path, origin, include_hash))
    return tracks


def metadata_key(track: TrackFile, duration_bucket_seconds: int) -> Optional[str]:
    artist = normalize_text(track.artist)
    title = normalize_text(track.title)
    if not artist or not title or track.duration_sec is None:
        return None
    duration_bucket = int(round(track.duration_sec / max(duration_bucket_seconds, 1)))
    return f"{artist}|{title}|{duration_bucket}"


def _connect_group(uf: UnionFind, indices: Sequence[int]) -> None:
    if len(indices) < 2:
        return
    root = indices[0]
    for idx in indices[1:]:
        uf.union(root, idx)


def detect_duplicate_groups(
    tracks: Sequence[TrackFile],
    *,
    match_mode: str,
    duration_bucket_seconds: int,
    cross_compare_only: bool,
) -> List[List[TrackFile]]:
    if not tracks:
        return []

    uf = UnionFind(len(tracks))

    if match_mode in {"hash", "hybrid"}:
        by_hash: Dict[str, List[int]] = {}
        for idx, track in enumerate(tracks):
            if track.file_hash:
                by_hash.setdefault(track.file_hash, []).append(idx)
        for indices in by_hash.values():
            _connect_group(uf, indices)

    if match_mode in {"metadata", "hybrid"}:
        by_meta: Dict[str, List[int]] = {}
        for idx, track in enumerate(tracks):
            key = metadata_key(track, duration_bucket_seconds=duration_bucket_seconds)
            if key:
                by_meta.setdefault(key, []).append(idx)
        for indices in by_meta.values():
            _connect_group(uf, indices)

    components: Dict[int, List[int]] = {}
    for idx in range(len(tracks)):
        root = uf.find(idx)
        components.setdefault(root, []).append(idx)

    groups: List[List[TrackFile]] = []
    for indices in components.values():
        if len(indices) < 2:
            continue
        group = [tracks[idx] for idx in indices]
        if cross_compare_only and len({item.origin for item in group}) < 2:
            continue
        groups.append(sorted(group, key=lambda item: str(item.path)))

    groups.sort(key=lambda group: str(group[0].path))
    return groups


def is_lossless(track: TrackFile) -> bool:
    ext = track.path.suffix.lower()
    if ext in {".flac", ".wav", ".aif", ".aiff"}:
        return True
    return bool(track.bits_per_sample and track.bits_per_sample > 0)


def quality_key(track: TrackFile):
    return (
        1 if is_lossless(track) else 0,
        track.bitrate_kbps or 0,
        track.sample_rate or 0,
        track.bits_per_sample or 0,
        track.size_bytes,
        track.mtime,
        str(track.path),
    )


def choose_keeper(group: Sequence[TrackFile], keep_strategy: str) -> TrackFile:
    return choose_keeper_with_preference(group, keep_strategy=keep_strategy, prefer_origin=None)


def choose_keeper_with_preference(
    group: Sequence[TrackFile], keep_strategy: str, prefer_origin: Optional[str]
) -> TrackFile:
    candidates = list(group)
    if prefer_origin:
        preferred = [item for item in candidates if item.origin == prefer_origin]
        if preferred:
            candidates = preferred

    if keep_strategy == "newest":
        return max(candidates, key=lambda item: (item.mtime, str(item.path)))
    if keep_strategy == "oldest":
        return min(candidates, key=lambda item: (item.mtime, str(item.path)))
    return max(candidates, key=quality_key)


def prune_empty_parents(file_path: Path, prune_roots: Sequence[Path]) -> List[Path]:
    removed: List[Path] = []
    normalized_roots = [root.resolve() for root in prune_roots]
    parent = file_path.parent.resolve()

    while True:
        if parent in normalized_roots:
            break
        if not any(str(parent).startswith(f"{root}{os.sep}") or parent == root for root in normalized_roots):
            break
        try:
            next(parent.iterdir())
            break
        except StopIteration:
            parent.rmdir()
            removed.append(parent)
            parent = parent.parent.resolve()
        except FileNotFoundError:
            parent = parent.parent.resolve()
        except OSError:
            break
    return removed


def unique_destination(review_dir: Path, file_path: Path) -> Path:
    review_dir.mkdir(parents=True, exist_ok=True)
    candidate = review_dir / file_path.name
    if not candidate.exists():
        return candidate
    stem = file_path.stem
    suffix = file_path.suffix
    counter = 2
    while True:
        candidate = review_dir / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def apply_action(
    groups: Sequence[Sequence[TrackFile]],
    *,
    action: str,
    keep_strategy: str,
    prefer_origin: Optional[str],
    review_dir: Optional[Path],
    prune_roots: Optional[Sequence[Path]],
    cleanup_empty_dirs: bool,
    dry_run: bool,
) -> List[Decision]:
    decisions: List[Decision] = []
    effective_prune_roots = list(prune_roots or [])
    for group_id, group in enumerate(groups, start=1):
        keeper = choose_keeper_with_preference(
            group, keep_strategy=keep_strategy, prefer_origin=prefer_origin
        )
        keep_path = str(keeper.path)
        decisions.append(
            Decision(
                group_id=group_id,
                role="keep",
                action="keep",
                origin=keeper.origin,
                path=str(keeper.path),
                target_path=str(keeper.path),
                keep_path=keep_path,
                keep_strategy=keep_strategy,
                reason="selected_by_strategy",
            )
        )

        for track in group:
            if track.path == keeper.path:
                continue

            if action == "report":
                decisions.append(
                    Decision(
                        group_id=group_id,
                        role="duplicate",
                        action="report",
                        origin=track.origin,
                        path=str(track.path),
                        target_path=str(track.path),
                        keep_path=keep_path,
                        keep_strategy=keep_strategy,
                        reason="duplicate_detected",
                    )
                )
                continue

            if action == "move":
                if review_dir is None:
                    raise ValueError("review_dir is required for move action")
                destination = unique_destination(review_dir, track.path)
                if not dry_run:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(track.path), str(destination))
                    if cleanup_empty_dirs:
                        prune_empty_parents(track.path, effective_prune_roots)
                decisions.append(
                    Decision(
                        group_id=group_id,
                        role="duplicate",
                        action="move",
                        origin=track.origin,
                        path=str(track.path),
                        target_path=str(destination),
                        keep_path=keep_path,
                        keep_strategy=keep_strategy,
                        reason="moved_to_review",
                    )
                )
                continue

            if action == "delete":
                if not dry_run:
                    track.path.unlink()
                    if cleanup_empty_dirs:
                        prune_empty_parents(track.path, effective_prune_roots)
                decisions.append(
                    Decision(
                        group_id=group_id,
                        role="duplicate",
                        action="delete",
                        origin=track.origin,
                        path=str(track.path),
                        target_path="",
                        keep_path=keep_path,
                        keep_strategy=keep_strategy,
                        reason="deleted",
                    )
                )
                continue

            raise ValueError(f"Unsupported action: {action}")

    return decisions


def export_csv_rows(path: Path, rows: Iterable[Decision]) -> None:
    fieldnames = [
        "group_id", "role", "action", "origin", "path",
        "target_path", "keep_path", "keep_strategy", "reason",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def export_json_rows(path: Path, rows: Iterable[Decision]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump([row.__dict__ for row in rows], handle, indent=2)
