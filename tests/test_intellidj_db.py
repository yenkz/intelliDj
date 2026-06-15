from intellidj_db import IntelliDJDB, make_track_key


def test_get_pending_download_queries_includes_candidate_generated(tmp_path):
    db_path = tmp_path / "intellidj.db"
    db = IntelliDJDB(str(db_path))
    try:
        track_key = make_track_key(artist="Artist", title="Track", search_string="Artist - Track")
        track_id = db.upsert_track(
            track_key=track_key,
            artist="Artist",
            title="Track",
            source_search_string="Artist - Track",
            source_csv="spotify_export.csv",
        )
        db.add_event(
            run_id=None,
            track_id=track_id,
            stage="candidate_generation",
            status="candidate_generated",
            message="Artist - Track",
        )

        pending = db.get_pending_download_queries()
        assert pending == [(track_id, "Artist - Track")]
    finally:
        db.close()


def test_get_pending_download_queries_excludes_queued(tmp_path):
    db_path = tmp_path / "intellidj.db"
    db = IntelliDJDB(str(db_path))
    try:
        track_key = make_track_key(artist="Artist", title="Track", search_string="Artist - Track")
        track_id = db.upsert_track(
            track_key=track_key,
            artist="Artist",
            title="Track",
            source_search_string="Artist - Track",
            source_csv="spotify_export.csv",
        )
        db.add_event(
            run_id=None,
            track_id=track_id,
            stage="candidate_generation",
            status="candidate_generated",
            message="Artist - Track",
        )
        db.add_event(
            run_id=None,
            track_id=track_id,
            stage="slskd_queue",
            status="download_queued",
            message="queued",
        )

        pending = db.get_pending_download_queries()
        assert pending == []
    finally:
        db.close()


def test_pending_download_queries_v2_scope_new_and_existing(tmp_path):
    db_path = tmp_path / "intellidj.db"
    db = IntelliDJDB(str(db_path))
    try:
        batch_id = db.create_ingestion_batch(source_type="exportify_csv", import_method="csv", label="setA")

        new_key = make_track_key(artist="New A", title="New T", search_string="New A - New T")
        new_id = db.upsert_track(
            track_key=new_key,
            artist="New A",
            title="New T",
            source_search_string="New A - New T",
            source_csv="a.csv",
        )
        db.upsert_track_ingestion(
            track_id=new_id,
            batch_id=batch_id,
            source_type="exportify_csv",
            import_method="csv",
            row_index=0,
            is_new_track=True,
        )
        db.upsert_track_stage_state(track_id=new_id, stage="candidate_generation", status="candidate_generated")

        existing_key = make_track_key(artist="Old A", title="Old T", search_string="Old A - Old T")
        existing_id = db.upsert_track(
            track_key=existing_key,
            artist="Old A",
            title="Old T",
            source_search_string="Old A - Old T",
            source_csv="old.csv",
        )
        db.upsert_track_stage_state(track_id=existing_id, stage="candidate_generation", status="candidate_generated")

        new_rows = db.get_pending_download_queries_v2(scope="new", batch_id=batch_id)
        assert new_rows == [(new_id, "New A - New T")]

        existing_rows = db.get_pending_download_queries_v2(scope="existing", batch_id=batch_id)
        assert existing_rows == [(existing_id, "Old A - Old T")]
    finally:
        db.close()


def test_get_exportify_rows_by_scope(tmp_path):
    db_path = tmp_path / "intellidj.db"
    db = IntelliDJDB(str(db_path))
    try:
        batch1 = db.create_ingestion_batch(source_type="exportify_csv", import_method="csv", label="set1")
        batch2 = db.create_ingestion_batch(source_type="exportify_csv", import_method="csv", label="set2")

        track_key1 = make_track_key(artist="A1", title="T1", search_string="A1 - T1")
        t1 = db.upsert_track(track_key=track_key1, artist="A1", title="T1", source_search_string="A1 - T1")
        db.upsert_exportify_track(
            batch_id=batch1,
            track_id=t1,
            source_csv="one.csv",
            row_index=0,
            row={"Track URI": "u1", "Track Name": "T1", "Artist Name(s)": "A1"},
        )

        track_key2 = make_track_key(artist="A2", title="T2", search_string="A2 - T2")
        t2 = db.upsert_track(track_key=track_key2, artist="A2", title="T2", source_search_string="A2 - T2")
        db.upsert_exportify_track(
            batch_id=batch2,
            track_id=t2,
            source_csv="two.csv",
            row_index=0,
            row={"Track URI": "u2", "Track Name": "T2", "Artist Name(s)": "A2"},
        )

        resolved_batch, rows_new = db.get_exportify_rows(batch_id=batch2, scope="new")
        assert resolved_batch == batch2
        assert [r["Track URI"] for r in rows_new] == ["u2"]

        _, rows_existing = db.get_exportify_rows(batch_id=batch2, scope="existing")
        assert [r["Track URI"] for r in rows_existing] == ["u1"]
    finally:
        db.close()
