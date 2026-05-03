# Architecture

## Short Diagram

```mermaid
flowchart LR
    U["User Browser"] --> F["Frontend UI (Vite/React)"]
    F --> P["API Endpoint (/api)"]
    P --> B["Python Backend (backend/main.py)"]
    B --> G["Gemini API"]
    B --> I["DIU Site Index (data/processed/daffodil_site_index.json)"]
    B --> R["Uploaded Context + Canvas Runtime (tmp/)"]
    B --> O["Observability Logs (tmp/logs/backend_events.jsonl)"]
```

## Runtime Roles

- `frontend/`: user interface, chat flow, upload flow, and browser-side fallbacks
- `backend/main.py`: main HTTP API for chat, upload, health, transcribe, and canvas artifact serving
- `src/core/knowledge.py`: DIU retrieval and grounding selection
- `src/core/gemini.py`: Gemini prompting, grounding, and streaming behavior
- `data/processed/daffodil_site_index.json`: prepared DIU knowledge index used for official-source grounding
- `tmp/`: local runtime state for uploaded text, canvas artifacts, and observability logs

## Submission Notes

- The production architecture now matches the intended long-term model: `static frontend + permanent Python backend`.
- The frontend stays static and lightweight.
- The backend remains the single source of truth for DIU retrieval, uploads, and model behavior.
