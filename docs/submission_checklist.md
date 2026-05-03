# Submission Checklist

## Repository Structure

- `docs/` contains architecture, deployment, observability, and report materials
- `data/raw/` is reserved for original crawl/source inputs
- `data/processed/` contains the prepared DIU index used by the assistant
- `notebooks/` is reserved for optional experiments and evaluation notes
- `backend/`, `frontend/`, and `tests/` remain the actual application structure

## Before Final GitHub Submission

1. Remove temporary runtime files from `tmp/` except the kept scaffold files.
2. Remove generated frontend build output if it is not needed in the repo.
3. Confirm the working tree only contains intended source and documentation changes.
4. Run backend tests.
5. Run frontend tests and production build.
6. Confirm the report content is complete, not just outlined.

## Demo Readiness

1. Verify `/api/health`.
2. Verify normal chat.
3. Verify uploaded-document follow-up chat.
4. Verify at least one admission, one scholarship, and one program question.
5. Check `python3 scripts/review_backend_logs.py` after smoke tests.

## Recommended Production Decision

- Prefer an always-on backend tier over a sleeping free tier.
