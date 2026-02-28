from pathlib import Path

import scripts.find_duplicate_tracks as mod


def make_track(
    path: Path,
    *,
    origin: str = "source",
    size_bytes: int = 100,
    mtime: float = 1000.0,
    duration_sec: float | None = 120.0,
    bitrate_kbps: int | None = 320,
    sample_rate: int | None = 44100,
    bits_per_sample: int | None = None,
    artist: str | None = "Artist",
    title: str | None = "Track",
    file_hash: str | None = None,
) -> mod.TrackFile:
    return mod.TrackFile(
        path=path,
        origin=origin,
        size_bytes=size_bytes,
        mtime=mtime,
        duration_sec=duration_sec,
        bitrate_kbps=bitrate_kbps,
        sample_rate=sample_rate,
        bits_per_sample=bits_per_sample,
        artist=artist,
        title=title,
        file_hash=file_hash,
    )


def test_metadata_key_normalizes_artist_title():
    track = make_track(Path("/tmp/a.mp3"), artist="Artist A", title="Track (Extended Mix)")
    key = mod.metadata_key(track, duration_bucket_seconds=2)
    assert key == "artist a|track|60"


def test_choose_keeper_best_prefers_lossless():
    mp3 = make_track(Path("/tmp/a.mp3"), bitrate_kbps=320, bits_per_sample=None)
    flac = make_track(Path("/tmp/b.flac"), bitrate_kbps=900, bits_per_sample=16)
    keeper = mod.choose_keeper([mp3, flac], keep_strategy="best")
    assert keeper.path == flac.path


def test_choose_keeper_newest_oldest():
    old = make_track(Path("/tmp/old.mp3"), mtime=10)
    new = make_track(Path("/tmp/new.mp3"), mtime=20)
    assert mod.choose_keeper([old, new], keep_strategy="newest").path == new.path
    assert mod.choose_keeper([old, new], keep_strategy="oldest").path == old.path


def test_choose_keeper_with_prefer_origin():
    source_old = make_track(Path("/tmp/source.mp3"), origin="source", mtime=10)
    compare_new = make_track(Path("/tmp/compare.mp3"), origin="compare", mtime=20)
    keeper = mod.choose_keeper_with_preference(
        [source_old, compare_new], keep_strategy="newest", prefer_origin="source"
    )
    assert keeper.path == source_old.path


def test_detect_duplicate_groups_cross_compare():
    tracks = [
        make_track(Path("/tmp/source/a.mp3"), origin="source", file_hash="abc"),
        make_track(Path("/tmp/compare/a.mp3"), origin="compare", file_hash="abc"),
        make_track(Path("/tmp/source/unique.mp3"), origin="source", file_hash="zzz"),
    ]
    groups = mod.detect_duplicate_groups(
        tracks,
        match_mode="hash",
        duration_bucket_seconds=2,
        cross_compare_only=True,
    )
    assert len(groups) == 1
    assert {item.origin for item in groups[0]} == {"source", "compare"}


def test_apply_action_move_dry_run(tmp_path):
    keep = tmp_path / "keep.mp3"
    dup = tmp_path / "dup.mp3"
    keep.write_bytes(b"keep")
    dup.write_bytes(b"dup")
    review = tmp_path / "review"

    group = [make_track(keep, file_hash="x"), make_track(dup, file_hash="x")]
    decisions = mod.apply_action(
        [group],
        action="move",
        keep_strategy="best",
        prefer_origin=None,
        review_dir=review,
        prune_roots=[tmp_path],
        cleanup_empty_dirs=False,
        dry_run=True,
    )
    assert keep.exists()
    assert dup.exists()
    assert any(item.action == "move" for item in decisions)


def test_apply_action_move_real(tmp_path):
    keep = tmp_path / "keep.flac"
    dup = tmp_path / "dup.mp3"
    keep.write_bytes(b"keep")
    dup.write_bytes(b"dup")
    review = tmp_path / "review"

    group = [
        make_track(keep, bits_per_sample=16, bitrate_kbps=900, file_hash="x"),
        make_track(dup, bits_per_sample=None, bitrate_kbps=320, file_hash="x"),
    ]
    decisions = mod.apply_action(
        [group],
        action="move",
        keep_strategy="best",
        prefer_origin=None,
        review_dir=review,
        prune_roots=[tmp_path],
        cleanup_empty_dirs=False,
        dry_run=False,
    )
    assert keep.exists()
    assert not dup.exists()
    moved_rows = [item for item in decisions if item.action == "move"]
    assert len(moved_rows) == 1
    assert Path(moved_rows[0].target_path).exists()


def test_apply_action_move_removes_empty_parent_dirs(tmp_path):
    keep = tmp_path / "keep.flac"
    dup_dir = tmp_path / "dups" / "nested"
    dup_dir.mkdir(parents=True)
    dup = dup_dir / "dup.mp3"
    keep.write_bytes(b"keep")
    dup.write_bytes(b"dup")
    review = tmp_path / "review"

    group = [
        make_track(keep, bits_per_sample=16, bitrate_kbps=900, file_hash="x"),
        make_track(dup, bits_per_sample=None, bitrate_kbps=320, file_hash="x"),
    ]
    mod.apply_action(
        [group],
        action="move",
        keep_strategy="best",
        prefer_origin=None,
        review_dir=review,
        prune_roots=[tmp_path],
        cleanup_empty_dirs=True,
        dry_run=False,
    )
    assert not dup.exists()
    assert not dup_dir.exists()
    assert not (tmp_path / "dups").exists()


def test_apply_action_delete_real(tmp_path):
    keep = tmp_path / "keep.flac"
    dup = tmp_path / "dup.flac"
    keep.write_bytes(b"keep")
    dup.write_bytes(b"dup")

    group = [
        make_track(keep, file_hash="x", mtime=10),
        make_track(dup, file_hash="x", mtime=20),
    ]
    decisions = mod.apply_action(
        [group],
        action="delete",
        keep_strategy="oldest",
        prefer_origin=None,
        review_dir=None,
        prune_roots=[tmp_path],
        cleanup_empty_dirs=False,
        dry_run=False,
    )
    assert keep.exists()
    assert not dup.exists()
    assert any(item.action == "delete" for item in decisions)


def test_apply_action_delete_removes_empty_parent_dirs(tmp_path):
    keep = tmp_path / "keep.flac"
    dup_dir = tmp_path / "dups" / "nested"
    dup_dir.mkdir(parents=True)
    dup = dup_dir / "dup.flac"
    keep.write_bytes(b"keep")
    dup.write_bytes(b"dup")

    group = [
        make_track(keep, file_hash="x", mtime=10),
        make_track(dup, file_hash="x", mtime=20),
    ]
    mod.apply_action(
        [group],
        action="delete",
        keep_strategy="oldest",
        prefer_origin=None,
        review_dir=None,
        prune_roots=[tmp_path],
        cleanup_empty_dirs=True,
        dry_run=False,
    )
    assert not dup.exists()
    assert not dup_dir.exists()
    assert not (tmp_path / "dups").exists()
