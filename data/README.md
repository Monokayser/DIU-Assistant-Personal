# Data Layout

This folder is split to match the course-friendly `raw/` and `processed/` structure.

## `raw/`

Reserved for:

- original crawl exports
- DIU reference documents
- source PDFs, notices, or manual data captures used during knowledge-base preparation

## `processed/`

Current production-facing artifact:

- `daffodil_site_index.json`: prepared DIU site index used for grounding the assistant

## Regeneration Note

Refresh the processed DIU site index with the project script when needed:

```bash
python3 scripts/refresh_site_index.py
```

Keeping `raw/` and `processed/` separate makes the repository cleaner for submission without changing app behavior.
