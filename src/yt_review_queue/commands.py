"""Telegram command parser.

Supports all commands from DESIGN-v2.md §5.1 including voice-transcription
normalization (e.g. "priority five" -> 5).
"""
from __future__ import annotations

import re
import typing as t

# Word-to-digit map for voice transcription normalization
_WORD_NUMS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
}

# Short bookmark ID pattern (alphanumeric, 3-8 chars)
_ID_RE = r"([A-Za-z0-9]{2,12})"


def _parse_priority(token: str) -> t.Optional[int]:
    """Parse a priority value from digit or word form."""
    if token.isdigit():
        n = int(token)
        return n if 0 <= n <= 5 else None
    return _WORD_NUMS.get(token.lower())


def parse_command(text: str) -> t.Optional[dict]:
    """Parse a raw Telegram message into a command dict.

    Returns None for unrecognised commands.

    Keys in the returned dict:
        cmd        — str: the command name
        priority   — int or None
        note       — str or None
        id         — str bookmark ID or None
        url        — str URL or None
        category   — str KB category or None
        candidate  — int candidate number or None
        label      — str account label or None
    """
    text = text.strip()
    if not text:
        return None

    lower = text.lower()

    # --- priority N [note] ---  (case-insensitive keyword, preserve case on note)
    m = re.match(r"^priority\s+(\S+)(?:\s+(.*))?$", text, re.IGNORECASE)
    if m:
        pri_token = m.group(1).lower()
        pri = _parse_priority(pri_token)
        if pri is None:
            return None
        note = m.group(2) or None
        return {"cmd": "priority", "priority": pri, "note": note,
                "id": None, "url": None, "category": None,
                "candidate": None, "label": None}

    # --- queue [id] ---  (case-insensitive keyword, preserve case on id)
    m = re.match(r"^queue(?:\s+(\S+))?$", text, re.IGNORECASE)
    if m:
        return {"cmd": "queue", "priority": None, "note": None,
                "id": m.group(1), "url": None, "category": None,
                "candidate": None, "label": None}

    # --- choose <id> <n> ---
    m = re.match(rf"^choose\s+{_ID_RE}\s+(\d+)$", text, re.IGNORECASE)
    if m:
        return {"cmd": "choose", "priority": None, "note": None,
                "id": m.group(1), "url": None, "category": None,
                "candidate": int(m.group(2)), "label": None}

    # --- link <id> <url> ---
    m = re.match(rf"^link\s+{_ID_RE}\s+(\S+)$", text, re.IGNORECASE)
    if m:
        return {"cmd": "link", "priority": None, "note": None,
                "id": m.group(1), "url": m.group(2), "category": None,
                "candidate": None, "label": None}

    # --- watched <id> ---
    m = re.match(rf"^watched\s+{_ID_RE}$", text, re.IGNORECASE)
    if m:
        return {"cmd": "watched", "priority": None, "note": None,
                "id": m.group(1), "url": None, "category": None,
                "candidate": None, "label": None}

    # --- wiki <id> [as <category>] ---
    m = re.match(rf"^wiki\s+{_ID_RE}(?:\s+as\s+(\S+))?$", text, re.IGNORECASE)
    if m:
        return {"cmd": "wiki", "priority": None, "note": None,
                "id": m.group(1), "url": None, "category": m.group(2),
                "candidate": None, "label": None}

    # --- status ---
    if lower == "status":
        return {"cmd": "status", "priority": None, "note": None,
                "id": None, "url": None, "category": None,
                "candidate": None, "label": None}

    # --- switch <label> ---
    m = re.match(r"^switch\s+(\S+)$", text, re.IGNORECASE)
    if m:
        return {"cmd": "switch", "priority": None, "note": None,
                "id": None, "url": None, "category": None,
                "candidate": None, "label": m.group(1)}

    return None
