"""Markdown rendering shared by the Google extractors.

Docs and Slides tables arrive in different API shapes — Docs cells nest full
structural elements, Slides cells hold a TextContent directly — but they render
identically. Traversal stays in each extractor; only the rendering is shared,
so a fix here fixes both.
"""


def _escape_cell(text: str) -> str:
    """A literal `|` in a cell is read as a column separator and splits the row."""
    return (text or "").replace("|", r"\|")


def render_markdown_table(rows: list[list[str]]) -> list[str]:
    """Markdown table lines for `rows`; the first row is the header.

    Every row is padded to the widest row rather than to the header, so a body
    row longer than the header widens the table instead of losing cells.
    """
    if not rows:
        return []
    width = max(len(row) for row in rows)
    if width == 0:
        return []

    def _line(cells: list[str]) -> str:
        padded = [_escape_cell(c) for c in cells] + [""] * (width - len(cells))
        return "| " + " | ".join(padded) + " |"

    header, *body = rows
    separator = "| " + " | ".join("---" for _ in range(width)) + " |"
    return [_line(header), separator, *(_line(cells) for cells in body)]
