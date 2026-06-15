# Architecture (DB-first)

```mermaid
flowchart LR
  subgraph Inputs
    A["Exportify CSV"] --> B["csv_to_dj_pipeline.py"]
    C["Local Music Folder"] --> D["scan_local_music.py"]
  end

  subgraph Core
    E["intellidj.db"]
    E1["ingestion_batches"]
    E2["tracks"]
    E3["exportify_tracks"]
    E4["library_files"]
    E5["track_stage_state"]
    E6["track_events / assets / duplicate_decisions"]
    E --> E1
    E --> E2
    E --> E3
    E --> E4
    E --> E5
    E --> E6
  end

  B --> E
  D --> E

  subgraph Pipeline Stages
    F["dj_to_slskd_pipeline.py"]
    G["slskd (Docker/API)"]
    H["enrich_tags_from_spotify_csv.py"]
    I["run_beets_import.py"]
    J["run_cover_art.py"]
    K["find_duplicate_tracks.py"]
    NORM["normalize_loudness.sh"]
  end

  E -->|"scope + label + batch_id"| F
  F --> G
  G -->|"downloads"| H
  E -->|"metadata + selectors"| H
  H --> I
  I --> J
  J --> K
  K --> NORM

  F --> E
  H --> E
  I --> E
  J --> E
  K --> E

  subgraph Orchestration
    L["run_pipeline.py"]
    M["Streamlit UI (ui/streamlit_app.py)"]
    N["Makefile targets"]
  end

  L --> B
  L --> D
  L --> F
  L --> H
  L --> I
  L --> J
  L --> K
  M --> B
  M --> D
  M --> F
  M --> H
  M --> I
  M --> J
  M --> K
  N --> L

  subgraph Outputs
    O["Music Library (~ /Music/DJ/library)"]
    P["Playlists (M3U)"]
    Q["Optional DB CSV export (export_db_csv.py)"]
    R["Pipeline JSON report"]
  end

  I --> O
  O --> P
  E --> Q
  L --> R
```

## Key ideas

- `intellidj.db` is the single source of truth between stages.
- CSV is only for ingestion (and optional DB export), not for stage-to-stage handoff.
- Stage execution is selectable with `--scope`, `--label`, and `--batch-id`.
- Every stage writes lifecycle state back into DB for traceability.

## Sequence Diagram (Typical Run)

```mermaid
sequenceDiagram
  autonumber
  participant U as User
  participant UI as Streamlit UI / Make / CLI
  participant CSV as csv_to_dj_pipeline.py
  participant SCAN as scan_local_music.py
  participant DB as intellidj.db
  participant SLSKD as dj_to_slskd_pipeline.py
  participant API as slskd API
  participant ENRICH as enrich_tags_from_spotify_csv.py
  participant BEETS as run_beets_import.py
  participant ART as run_cover_art.py
  participant DUP as find_duplicate_tracks.py

  U->>UI: Start run (label, scope, optional batch)
  alt Optional local scan
    UI->>SCAN: scan --input-dir
    SCAN->>DB: write ingestion_batches/library_files/stage_state
  end
  UI->>CSV: import --input spotify_export.csv
  CSV->>DB: write exportify_tracks/track_ingestions/stage_state

  UI->>SLSKD: queue downloads --scope/--label/--batch-id
  SLSKD->>DB: read pending tracks
  SLSKD->>API: create searches + enqueue best match
  API-->>SLSKD: responses / queued status
  SLSKD->>DB: write slskd_queue stage + assets/events

  UI->>ENRICH: enrich --scope/--label/--batch-id --input-dir
  ENRICH->>DB: read Exportify metadata + selectors
  ENRICH->>DB: write tag_enrichment stage + assets/events

  UI->>BEETS: beets import wrapper --scope/--label/--batch-id
  BEETS->>DB: read selected tracks
  BEETS->>DB: write beets_import stage state

  UI->>ART: fetch + embed artwork --scope/--label/--batch-id
  ART->>DB: read selected tracks
  ART->>DB: write cover_art stage state

  opt Optional duplicate lifecycle
    UI->>DUP: run duplicate analysis
    DUP->>DB: write duplicate_decisions + stage_state
  end

  UI-->>U: Show logs + statuses (report/json optional)
```
