from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.observability import get_log_path, read_events, summarize_events


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize DIU Assistant backend observability logs.",
    )
    parser.add_argument(
        "--log-path",
        default=str(get_log_path()),
        help="Path to the backend JSONL log file.",
    )
    parser.add_argument(
        "--slow-ms",
        type=int,
        default=None,
        help="Override the slow-request threshold in milliseconds.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="Number of top slow/failing questions to show.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the summary as JSON instead of human-readable text.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    events = read_events(Path(args.log_path))
    summary = summarize_events(events, slow_request_ms=args.slow_ms, top_n=args.top)

    if args.json:
        print(json.dumps(summary, indent=2))
        return 0

    print("DIU Assistant Backend Log Review")
    print("=" * 32)
    print(f"Log file: {args.log_path}")
    print(f"Total events: {summary['total_events']}")
    print(f"Slow request threshold: {summary['slow_request_ms']} ms")
    print()

    print("Event counts")
    print("-" * 12)
    if summary["event_counts"]:
        for name, count in sorted(summary["event_counts"].items()):
            print(f"{name}: {count}")
    else:
        print("No events recorded yet.")
    print()

    print("Top failed questions")
    print("-" * 20)
    if summary["top_failed_questions"]:
        for item in summary["top_failed_questions"]:
            print(f"{item['count']}x  {item['question']}")
    else:
        print("No repeated failures recorded.")
    print()

    print("Top slow questions")
    print("-" * 18)
    if summary["top_slow_questions"]:
        for item in summary["top_slow_questions"]:
            print(
                f"{item['count']}x  avg {item['avg_elapsed_ms']} ms  "
                f"max {item['max_elapsed_ms']} ms  {item['question']}"
            )
    else:
        print("No slow requests recorded above the threshold.")
    print()

    print("Recent failures")
    print("-" * 15)
    if summary["recent_failures"]:
        for item in summary["recent_failures"]:
            detail = f" | {item['detail']}" if item["detail"] else ""
            print(f"{item['ts']}  {item['event']}  {item['question']}{detail}")
    else:
        print("No recent failures recorded.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
