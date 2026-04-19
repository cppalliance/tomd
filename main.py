#!/usr/bin/env python3
"""tomd - Convert PDF and HTML files to Markdown.

PDF: hybrid dual extraction (MuPDF + spatial rules) with confidence scoring.
HTML: DOM traversal with generator-specific metadata extraction.

Usage (after `pip install -e tomd`):
    tomd input.pdf                  # -> input.md + input.prompts.md
    tomd input.html                 # -> input.md
    tomd *.pdf *.html --outdir out/ # batch mode

Also runnable as `python -m tomd.main ...`.
"""

import argparse
import glob as globmod
import sys
from pathlib import Path

_HTML_EXTENSIONS = frozenset({".html", ".htm"})
_PDF_EXTENSIONS = frozenset({".pdf"})


def main():
    """CLI entry point: parse arguments, resolve inputs, and convert files."""
    parser = argparse.ArgumentParser(
        prog="tomd",
        description="Convert PDF and HTML files to Markdown.",
    )
    parser.add_argument(
        "input", nargs="*",
        help="PDF/HTML file(s) or glob patterns to convert")
    parser.add_argument(
        "-o", "--output",
        help="Output Markdown path (single-file mode only)")
    parser.add_argument(
        "--outdir",
        help="Output directory for batch mode")
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging")
    parser.add_argument(
        "--qa", action="store_true",
        help="Run QA scoring instead of converting; prints a ranked report")
    parser.add_argument(
        "--qa-json",
        help="Write per-file QA metrics as JSON to this path (implies --qa)")
    parser.add_argument(
        "--workers", type=int, default=1,
        help="Parallel workers for --qa mode (default: 1)")
    parser.add_argument(
        "--timeout", type=int, default=120,
        help="Seconds with no progress before aborting remaining files (default: 120)")

    args = parser.parse_args()

    if args.verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG,
                            format="%(name)s: %(message)s")

    if not args.input:
        parser.print_help()
        sys.exit(0)

    input_files = []
    for pattern in args.input:
        expanded = globmod.glob(pattern, recursive=True)
        if expanded:
            input_files.extend(expanded)
        else:
            input_files.append(pattern)
    input_files = list(dict.fromkeys(input_files))
    input_files = [Path(f) for f in input_files]

    if args.qa or args.qa_json:
        qa_files = [f for f in input_files
                    if f.suffix.lower() in _PDF_EXTENSIONS | _HTML_EXTENSIONS]
        if not qa_files:
            print("No PDF/HTML files found for QA scoring.", file=sys.stderr)
            sys.exit(1)
        from .lib.pdf.qa import run_qa_report
        json_path = Path(args.qa_json) if args.qa_json else None
        run_qa_report(qa_files, json_path=json_path, workers=args.workers,
                      timeout=args.timeout)
        sys.exit(0)

    if args.output and len(input_files) > 1:
        parser.error("-o/--output cannot be used with multiple input files")

    successes = []
    failures = []

    for input_file in input_files:
        if not input_file.exists():
            print(f"SKIP: {input_file} not found", file=sys.stderr)
            failures.append(input_file)
            continue

        if args.output and len(input_files) == 1:
            md_path = Path(args.output)
        elif args.outdir:
            md_path = Path(args.outdir) / input_file.with_suffix(".md").name
        else:
            md_path = input_file.with_suffix(".md")

        prompts_path = md_path.with_suffix(".prompts.md")

        try:
            ext = input_file.suffix.lower()
            if ext in _HTML_EXTENSIONS:
                from .lib.html import convert_html
                md_text, prompts_text = convert_html(input_file)
            elif ext in _PDF_EXTENSIONS:
                from .lib.pdf import convert_pdf
                md_text, prompts_text = convert_pdf(input_file)
            else:
                print(f"SKIP: {input_file} unsupported format", file=sys.stderr)
                failures.append(input_file)
                continue

            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text(md_text, encoding="utf-8")

            if prompts_text:
                prompts_path.write_text(prompts_text, encoding="utf-8")
                print(f"  ok: {input_file} -> {md_path} + {prompts_path}")
            else:
                if prompts_path.exists():
                    prompts_path.unlink()
                print(f"  ok: {input_file} -> {md_path}")

            successes.append(input_file)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(
                "FAIL: %s", input_file, exc_info=True)
            print(f"FAIL: {input_file} -- {e}", file=sys.stderr)
            failures.append(input_file)

    if len(input_files) > 1:
        print(f"\n{len(successes)} succeeded, {len(failures)} failed")

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
