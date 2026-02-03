┌────────────────────┐
│  Spotify Playlists │
│ (curaduría humana) │
└─────────┬──────────┘
          │ Spotify API
          ▼
┌────────────────────────────┐
│  Python Orchestrator        │
│  - Limpieza de nombres      │
│  - Audio features           │
│  - Clasificación inicial    │
└─────────┬──────────────────┘
          │ CSV / JSON
          ▼
┌────────────────────────────┐
│  Soulseek (slskd)           │
│  - búsqueda exacta          │
│  - filtro 320 / FLAC        │
│  - descarga automática      │
└─────────┬──────────────────┘
          │ audio files
          ▼
┌────────────────────────────┐
│  beets / metadata cleanup   │
│  - renombrado               │
│  - tags consistentes        │
└─────────┬──────────────────┘
          │ files limpios
          ▼
┌────────────────────────────┐
│  Music Library (neutral)    │
│  - flat                     │
│  - portable                 │
└─────────┬──────────────────┘
          │ watch folder
          ▼
┌────────────────────────────┐
│  Traktor / Rekordbox        │
│  - análisis BPM / key       │
│  - playlists inteligentes  │
└────────────────────────────┘