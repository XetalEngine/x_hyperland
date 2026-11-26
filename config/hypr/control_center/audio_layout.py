"""Shared logical-pixel sizing for the taskbar mixer and its columns."""

OUTER_MARGIN = 24
MASTER_WIDTH = 200
MASTER_GAP = 12
COLUMN_WIDTH = 172
MIN_COLUMN_WIDTH = 144
COLUMN_GAP = 10
VISIBLE_APPS = 10
HEIGHT = 470
MAX_WIDTH = OUTER_MARGIN + MASTER_WIDTH + MASTER_GAP + VISIBLE_APPS * COLUMN_WIDTH + (VISIBLE_APPS - 1) * COLUMN_GAP


def fit(app_count, available=MAX_WIDTH):
    """Fit whole columns, keeping text readable when a small screen must scroll."""
    count = min(VISIBLE_APPS, max(0, int(app_count)))
    available = max(1, min(MAX_WIDTH, int(available)))
    base = OUTER_MARGIN + MASTER_WIDTH
    if not count:
        return min(base, available), COLUMN_WIDTH
    fixed = base + MASTER_GAP + (count - 1) * COLUMN_GAP
    column = max(MIN_COLUMN_WIDTH, min(COLUMN_WIDTH, (available - fixed) // count))
    return min(available, fixed + count * column), column
