# Observability

## What Is Logged

The backend now records lightweight JSONL events for:

- slow chat requests
- retrieval misses
- weak retrieval matches
- backend errors
- empty streamed responses
- empty answer payloads

## Log Location

- default log file: `tmp/logs/backend_events.jsonl`

Environment overrides:

- `OBS_LOG_DIR`
- `OBS_LOG_PATH`
- `OBS_SLOW_REQUEST_MS`

## Why This Helps

This gives the project a simple quality-review loop without introducing heavy infrastructure.

You can now answer:

- which questions fail most often
- which requests are consistently slow
- whether failures come from retrieval misses, backend errors, or empty stream behavior

## Review Routine

Run:

```bash
python3 scripts/review_backend_logs.py
```

Useful options:

```bash
python3 scripts/review_backend_logs.py --top 10
python3 scripts/review_backend_logs.py --slow-ms 3000
python3 scripts/review_backend_logs.py --json
```

## Suggested Review Habit

1. Run a small smoke test set.
2. Review the log summary.
3. Fix repeated failure clusters first.
4. Re-run the same prompts and compare the new log output.
