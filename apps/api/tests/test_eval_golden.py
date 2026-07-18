"""Golden-conversation loader/repair tests (src.eval.golden).

The second source file is structurally malformed (message objects embedded in a
conversation object with no key, trailing commas); the loader must recover it
tolerantly. Inline fixtures mirror both real shapes so the tests don't depend on
the large data files.
"""

import json
from pathlib import Path

from src.eval.golden import load_canonical, load_file1, load_file2, load_golden

_VALID_FILE1 = [
    {
        "id": 1,
        "messages": [
            {"role": "assistant", "content": "Dạ em có thể giúp gì ạ."},
            {"role": "user", "content": "tư vấn máy lạnh"},
            {"role": "assistant", "content": "Dạ phòng mình bao nhiêu m2 ạ?"},
        ],
    },
]

# Mirrors the malformed second file: conversation objects mixing keyed metadata
# with bare, key-less message objects, plus trailing commas.
_MALFORMED_FILE2 = """[
  {
    "label": "conv A",
      {
        "role": "assistant",
        "content": "Dạ em có thể giúp gì ạ."
      },
      {
        "role": "user",
        "content": "còn hàng tủ lạnh không",
        "web_url": "https://example.com/x"
      },
      {
        "role": "assistant",
        "content": "Dạ còn ạ. Anh/chị cần dung tích bao nhiêu \\"lít\\" ạ?",
      },
    "user_info": {}
  },
  {
    "label": "conv B",
      {
        "role": "user",
        "content": "so sánh 2 máy giặt"
      },
      {
        "role": "assistant",
        "content": "Dạ anh/chị cho em tên 2 model ạ."
      }
  }
]"""


def test_load_file1_parses_valid_conversations(tmp_path: Path) -> None:
    path = tmp_path / "f1.json"
    path.write_text(json.dumps(_VALID_FILE1, ensure_ascii=False), encoding="utf-8")

    convs = load_file1(path)

    assert len(convs) == 1
    assert convs[0].id == "f1-1"
    assert [m.role for m in convs[0].messages] == ["assistant", "user", "assistant"]
    assert convs[0].user_turns == ["tư vấn máy lạnh"]


def test_load_file2_recovers_conversations_from_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "f2.json"
    path.write_text(_MALFORMED_FILE2, encoding="utf-8")

    convs = load_file2(path)

    # Two conversations recovered despite the broken wrapping + trailing commas.
    assert len(convs) == 2
    assert [len(c.messages) for c in convs] == [3, 2]
    # Roles preserved in order.
    assert [m.role for m in convs[0].messages] == ["assistant", "user", "assistant"]


def test_load_file2_cleans_json_escapes_in_content(tmp_path: Path) -> None:
    path = tmp_path / "f2.json"
    path.write_text(_MALFORMED_FILE2, encoding="utf-8")

    convs = load_file2(path)

    # The escaped \"lít\" in the source must come back as real quotes, not a
    # literal backslash-quote.
    third = convs[0].messages[2].content
    assert '"lít"' in third
    assert "\\" not in third


def test_load_file2_ignores_metadata_only_regions(tmp_path: Path) -> None:
    path = tmp_path / "f2.json"
    path.write_text('[\n  {\n    "label": "no messages here",\n    "user_info": {}\n  }\n]',
                    encoding="utf-8")

    assert load_file2(path) == []


def test_load_golden_combines_both_sources_when_present(tmp_path: Path) -> None:
    from src.eval.golden import FILE1, FILE2

    (tmp_path / FILE1).write_text(json.dumps(_VALID_FILE1, ensure_ascii=False), encoding="utf-8")
    (tmp_path / FILE2).write_text(_MALFORMED_FILE2, encoding="utf-8")

    convs = load_golden(tmp_path)

    assert len(convs) == 3  # 1 from file1 + 2 from file2
    assert {c.source for c in convs} == {FILE1, FILE2}


def test_load_canonical_supports_privacy_reviewed_synthetic_dataset(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "business-1",
                    "source": "synthetic_business",
                    "messages": [
                        {"role": "user", "content": "Tư vấn máy lạnh demo"},
                        {"role": "assistant", "content": "Dạ phòng mình bao nhiêu m² ạ?"},
                    ],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    conversations = load_canonical(path)

    assert [conversation.id for conversation in conversations] == ["business-1"]
    assert conversations[0].source == "synthetic_business"
    assert conversations[0].user_turns == ["Tư vấn máy lạnh demo"]
