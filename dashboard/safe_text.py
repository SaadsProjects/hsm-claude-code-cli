"""
One escaping helper for untrusted text on Markdown-capable elements (unit U4,
NFR1.5).

Backend messages, record keys, file names and CSV reasons reach notices,
captions and widget labels through ``escape_md``, so Markdown cannot style,
link, show images or colour text, and HTML angle brackets, entities,
``:emoji:`` codes and ``$math$`` are shown literally. Record values and audit
entries are drawn as data frames, and selector options are plain text; neither
interprets Markdown, so neither is escaped (escaping them would show the
backslashes).
No Streamlit import.
"""

# CommonMark lets every ASCII punctuation character be backslash-escaped, so
# an escaped "&" can no longer start an entity such as "&lt;" (security-design).
_SPECIAL = frozenset("\\`*_{}[]()#+-.!|~><:$&")


def escape_md(text):
    """``text`` with every Markdown and HTML control character backslash-
    escaped. Line breaks are kept; ``None`` gives ``""``; non-text values are
    shown as their ``str``."""
    if text is None:
        return ""
    return "".join("\\" + ch if ch in _SPECIAL else ch for ch in str(text))
