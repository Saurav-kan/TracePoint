#!/usr/bin/env python3
"""CLI script to run the ingestion pipeline on a document."""
import argparse
import sys
from pathlib import Path

# Add backend to path so app imports work when run from project root
_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from app.ingestion.pipeline import ingest_document


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest a document into the evidence database."
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Path to document (PDF, DOCX, images, Markdown, .txt; default: read from stdin)",
    )
    parser.add_argument(
        "--label",
        "-l",
        required=True,
        help="Evidence type label (e.g., witness, gps, alibi)",
    )
    parser.add_argument(
        "--source",
        "-s",
        help="Source document name for tracking",
    )
    args = parser.parse_args()

    if args.input:
        path = Path(args.input)
        if not path.exists():
            print(f"Error: File not found: {path}", file=sys.stderr)
            return 1
        source = args.source or path.name
        try:
            count = ingest_document(
                file_path=path,
                label=args.label,
                source_document=source,
            )
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    else:
        text = sys.stdin.read()
        if not text.strip():
            print("Error: No text to ingest.", file=sys.stderr)
            return 1
        source = args.source or "stdin"
        try:
            count = ingest_document(
                text=text,
                label=args.label,
                source_document=source,
            )
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    print(f"Ingested {count} chunk(s) with label '{args.label}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
