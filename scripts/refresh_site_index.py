from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.config import load_local_env
from src.apps.documents.rag.ingestion import DEFAULT_MAX_PAGES, build_site_index


def main() -> None:
    load_local_env(ROOT / ".env")

    parser = argparse.ArgumentParser(description="Refresh the DIU website knowledge index.")
    parser.add_argument("--base-url", default="https://daffodilvarsity.edu.bd/")
    parser.add_argument("--output", default=str(ROOT / "data" / "processed" / "daffodil_site_index.json"))
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--delay", type=float, default=0.08)
    parser.add_argument("--timeout", type=int, default=None, help="Per-request network timeout in seconds.")
    parser.add_argument("--no-sitemaps", action="store_true")
    args = parser.parse_args()
    if args.timeout and args.timeout > 0:
        os.environ["DIU_FETCH_TIMEOUT_SECONDS"] = str(args.timeout)

    max_pages = args.max_pages if args.max_pages and args.max_pages > 0 else None
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix="diu-site-index-",
        dir=output_path.parent,
        delete=False,
    ) as temp_file:
        temp_output_path = Path(temp_file.name)

    try:
        metadata = build_site_index(
            args.base_url,
            temp_output_path,
            max_pages=max_pages,
            request_delay=max(args.delay, 0),
            include_sitemaps=not args.no_sitemaps,
        )
        if int(metadata.get("pages_count") or 0) <= 0 or int(metadata.get("chunks_count") or 0) <= 0:
            raise RuntimeError("Refresh found zero pages or chunks; keeping the previous knowledge index.")
        shutil.move(str(temp_output_path), output_path)
    except Exception:
        temp_output_path.unlink(missing_ok=True)
        raise

    crawl_budget = metadata.get("crawl_budget_pages") or max_pages or DEFAULT_MAX_PAGES
    print(
        "Refreshed DIU knowledge index: "
        f"{metadata.get('pages_count', 0)} pages, "
        f"{metadata.get('chunks_count', 0)} chunks, "
        f"budget {crawl_budget} pages."
    )
    print(f"Backend index: {output_path.resolve()}")


if __name__ == "__main__":
    main()
