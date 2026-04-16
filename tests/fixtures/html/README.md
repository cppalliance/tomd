Optional static HTML inputs for tests. Prefer inline strings in `test_html_*.py` unless a snippet is large or shared across files; then add a `.html` here and load with `Path(__file__).resolve().parent / "fixtures/html/name.html"`.

Golden regression outputs live in sibling directory [`../golden/`](../golden/): `*.golden.md` and optional `*.golden.prompts.md`, produced from `tomd/papers/*.html` via `convert_html`. See [`test_html_golden.py`](../../test_html_golden.py).
