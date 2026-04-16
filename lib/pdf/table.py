"""Table detection from MuPDF block/line structure.

Detects tables by finding consecutive blocks where each block has
2+ lines with a large x-gap between them (columnar layout). Tables
are extracted with high confidence before dual-path comparison.
"""

import logging

from .types import Block, Line, Section, SectionKind, Confidence

_log = logging.getLogger(__name__)

_COLUMN_GAP_THRESHOLD = 50.0
_MIN_TABLE_ROWS = 2
_COLUMN_X_TOLERANCE = 10.0
_TABLE_Y_OVERLAP_MARGIN = 5.0


def _block_column_positions(block: Block) -> list[float] | None:
    """Return the x-start positions of columns in a block, or None.

    A block is columnar if it has 2+ lines where every line after
    the first starts significantly to the right of the first line's
    x-start position.
    """
    if len(block.lines) < 2:
        return None

    x_starts = []
    for line in block.lines:
        if not line.spans:
            return None
        x_starts.append(line.bbox[0])

    for i in range(1, len(x_starts)):
        if x_starts[i] - x_starts[0] < _COLUMN_GAP_THRESHOLD:
            return None

    return x_starts


def _columns_match(cols_a: list[float], cols_b: list[float]) -> bool:
    """Check if two column position lists represent the same table structure."""
    if len(cols_a) != len(cols_b):
        return False
    return all(abs(a - b) < _COLUMN_X_TOLERANCE for a, b in zip(cols_a, cols_b))


def detect_tables(blocks: list[Block]) -> tuple[list[Section], list[Block]]:
    """Detect table regions from MuPDF block structure.

    Returns (table_sections, remaining_blocks).
    Table sections have kind=TABLE with high confidence.
    Remaining blocks are the non-table blocks for normal processing.
    """
    table_sections: list[Section] = []
    remaining: list[Block] = []
    i = 0

    while i < len(blocks):
        cols = _block_column_positions(blocks[i])
        if cols is None:
            remaining.append(blocks[i])
            i += 1
            continue

        table_blocks = [blocks[i]]
        j = i + 1
        while j < len(blocks):
            next_cols = _block_column_positions(blocks[j])
            if next_cols is not None and _columns_match(cols, next_cols):
                table_blocks.append(blocks[j])
                j += 1
            else:
                break

        if len(table_blocks) >= _MIN_TABLE_ROWS:
            num_cols = len(cols)
            rows: list[list[list]] = []
            all_lines = []

            for blk in table_blocks:
                row = []
                for line in blk.lines[:num_cols]:
                    row.append(list(line.spans))
                    all_lines.append(line)
                while len(row) < num_cols:
                    row.append([])
                for line in blk.lines[num_cols:]:
                    all_lines.append(line)
                    line_x = line.bbox[0]
                    best_col = min(
                        range(num_cols),
                        key=lambda ci: abs(line_x - cols[ci]),
                    )
                    row[best_col].extend(line.spans)
                rows.append(row)

            text = "\n".join(
                " | ".join(
                    "".join(s.text for s in cell).strip()
                    for cell in row
                )
                for row in rows
            )

            table_sections.append(Section(
                kind=SectionKind.TABLE,
                text=text,
                confidence=Confidence.HIGH,
                lines=all_lines,
                page_num=table_blocks[0].page_num,
                columns=rows,
            ))
            _log.debug("Table detected: %d rows x %d cols on page %d",
                        len(rows), num_cols, table_blocks[0].page_num)
            i = j
        else:
            remaining.append(blocks[i])
            i += 1

    return table_sections, remaining


def exclude_table_regions(blocks: list[Block],
                          table_sections: list[Section]) -> list[Block]:
    """Remove blocks whose vertical midpoint falls within a detected table region."""
    if not table_sections:
        return blocks

    table_ranges = []
    for sec in table_sections:
        if not sec.lines:
            continue
        y_min = min(ln.bbox[1] for ln in sec.lines)
        y_max = max(ln.bbox[3] for ln in sec.lines)
        table_ranges.append((sec.page_num, y_min, y_max))

    result = []
    for block in blocks:
        in_table = False
        by = (block.bbox[1] + block.bbox[3]) / 2.0
        for pg, y_min, y_max in table_ranges:
            if (block.page_num == pg
                    and y_min - _TABLE_Y_OVERLAP_MARGIN <= by
                    <= y_max + _TABLE_Y_OVERLAP_MARGIN):
                in_table = True
                break
        if not in_table:
            result.append(block)
    return result
