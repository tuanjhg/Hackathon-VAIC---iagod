"""Load + normalize the golden advisory conversations into one canonical schema.

Two source shapes live under ``data/``:

* ``35sample_chat_history (1).json`` — valid JSON: ``[{"id", "messages":
  [{"role", "content"}]}]``.
* ``chat_history_buy_product.json`` — **structurally malformed**: each
  conversation is a JSON object that mixes keyed metadata (``label``,
  ``user_info`` …) with bare message objects that have no key, plus trailing
  commas. It cannot be ``json.loads``-ed. We recover it tolerantly: split on the
  conversation-level closing brace, then regex the ``role``/``content`` pairs
  (single-line values with standard JSON escaping) in document order.

Both normalize to :class:`GoldenConversation`. The raw files are never mutated;
:func:`write_normalized` emits a clean combined copy for inspection.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FILE1 = "35sample_chat_history (1).json"
FILE2 = "chat_history_buy_product.json"

_VALID_ROLES = ("assistant", "user", "system")

# role+content pair, content is single-line with standard JSON string escaping.
_MSG_RE = re.compile(
    r'"role"\s*:\s*"(assistant|user|system)"\s*,\s*"content"\s*:\s*"((?:[^"\\]|\\.)*)"',
    re.DOTALL,
)
# a conversation-level closing brace (2-space indent) delimits conversations in
# the malformed file.
_CONV_SPLIT_RE = re.compile(r"\n {2}\},?")


@dataclass(frozen=True)
class GoldenMessage:
    role: str
    content: str


@dataclass(frozen=True)
class GoldenConversation:
    id: str
    source: str
    messages: list[GoldenMessage]

    @property
    def user_turns(self) -> list[str]:
        return [m.content for m in self.messages if m.role == "user"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "messages": [{"role": m.role, "content": m.content} for m in self.messages],
        }


def _clean(content: str) -> str:
    """Undo JSON string escaping in a regex-captured content value."""
    return json.loads(f'"{content}"') if content else content


def load_file1(path: Path) -> list[GoldenConversation]:
    data = json.loads(path.read_text(encoding="utf-8"))
    conversations: list[GoldenConversation] = []
    for entry in data:
        messages = [
            GoldenMessage(role=m["role"], content=m["content"])
            for m in entry.get("messages", [])
            if m.get("role") in _VALID_ROLES and m.get("content")
        ]
        if messages:
            conversations.append(
                GoldenConversation(id=f"f1-{entry.get('id')}", source=FILE1, messages=messages)
            )
    return conversations


def load_file2(path: Path) -> list[GoldenConversation]:
    """Tolerantly recover conversations from the malformed second file."""
    text = path.read_text(encoding="utf-8")
    conversations: list[GoldenConversation] = []
    for index, chunk in enumerate(_CONV_SPLIT_RE.split(text)):
        messages = [
            GoldenMessage(role=role, content=_clean(content))
            for role, content in _MSG_RE.findall(chunk)
        ]
        if messages:
            conversations.append(
                GoldenConversation(id=f"f2-{index}", source=FILE2, messages=messages)
            )
    return conversations


def load_golden(data_dir: Path) -> list[GoldenConversation]:
    """Load and normalize both golden files into one list of conversations."""
    conversations: list[GoldenConversation] = []
    file1 = data_dir / FILE1
    file2 = data_dir / FILE2
    if file1.exists():
        conversations.extend(load_file1(file1))
    if file2.exists():
        conversations.extend(load_file2(file2))
    return conversations


def write_normalized(conversations: list[GoldenConversation], out_path: Path) -> None:
    """Write a clean combined copy (for human inspection); never touches sources."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [c.to_dict() for c in conversations]
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
