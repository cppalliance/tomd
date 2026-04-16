# HTML golden files

Expected outputs for [`test_html_golden.py`](../../test_html_golden.py). Inputs live under [`papers/`](../../../papers/) as `{stem}.html` (not copied into this folder).

## Refreshing baselines

From the `tomd/` directory (where `lib/` and `papers/` sit), after you intentionally change converter output:

```bash
python -c "
from pathlib import Path
from lib.html import convert_html
ROOT = Path('.').resolve()
papers, out = ROOT / 'papers', ROOT / 'tests/fixtures/golden'
for name in ['p3411r5.html', 'p2728r11.html', 'p3953r0.html', 'p4005r0.html',
             'p4020r0.html', 'p3911r2.html', 'n5034.html']:
    stem = Path(name).stem
    md, pr = convert_html(papers / name)
    (out / f'{stem}.golden.md').write_text(md, encoding='utf-8', newline='\n')
    ppath = out / f'{stem}.golden.prompts.md'
    if pr:
        ppath.write_text(pr, encoding='utf-8', newline='\n')
    elif ppath.exists():
        ppath.unlink()
"
```

Review diffs, then commit. Follow [wg21-papers `CLAUDE.md`](../../../../CLAUDE.md) and [`tomd/CLAUDE.md`](../../../CLAUDE.md).
