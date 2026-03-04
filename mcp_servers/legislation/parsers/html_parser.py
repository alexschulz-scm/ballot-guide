"""
HTML text extractor for ballot measure legal text.

Uses stdlib html.parser — no external dependencies. Strips script, style,
and other non-visible tags, then returns the remaining visible text.
"""

from html.parser import HTMLParser


def extract_text_from_html(html: str) -> str:
    """
    Extract visible text content from an HTML string.

    Skips script, style, and other non-content tags. Returns the visible
    text as a single string with words separated by spaces.
    """
    parser = _TextExtractor()
    parser.feed(html)
    return parser.get_text()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


class _TextExtractor(HTMLParser):
    """Minimal HTML parser that collects only visible text content."""

    _SKIP_TAGS = frozenset({"script", "style", "head", "noscript", "meta", "link"})

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth: int = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self._parts.append(stripped)

    def get_text(self) -> str:
        return " ".join(self._parts)
