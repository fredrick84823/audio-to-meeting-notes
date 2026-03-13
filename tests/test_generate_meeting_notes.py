"""
tests/test_generate_meeting_notes.py

測試 generate_meeting_notes.py 中的純函式（不需要外部 API）。
執行：uv run pytest tests/
"""

import pytest

from generate_meeting_notes import (
    _classify_line,
    _parse_inline_bold,
    _parse_table_rows,
    cleanup_segments,
    extract_date,
    inject_attendees,
    preprocess_content,
)


# ─── extract_date ─────────────────────────────────────────────────────────────

class TestExtractDate:
    def test_standard_filename(self):
        assert extract_date("data_meeting_20260309.m4a") == "20260309"

    def test_date_in_middle(self):
        assert extract_date("weekly_sync_20260312.mp3") == "20260312"

    def test_date_at_start(self):
        assert extract_date("20260101_standup.m4a") == "20260101"

    def test_no_date_raises(self):
        with pytest.raises(ValueError, match="無法從檔名提取日期"):
            extract_date("meeting_notes.mp3")

    def test_short_number_not_matched(self):
        with pytest.raises(ValueError):
            extract_date("meeting_123.mp3")

    def test_picks_first_8digit_sequence(self):
        # 2025 是 4 位，20260313 是 8 位，應取後者
        assert extract_date("carrefour_2025_report_20260313.mp3") == "20260313"


# ─── preprocess_content ───────────────────────────────────────────────────────

class TestPreprocessContent:
    def test_underline_to_bold(self):
        result = preprocess_content("<u>重要事項</u>")
        assert result == "**重要事項**"

    def test_removes_other_html_tags(self):
        result = preprocess_content("這是<b>粗體</b>文字")
        assert result == "這是粗體文字"

    def test_multiline_underline(self):
        content = "前文\n<u>標題</u>\n後文"
        result = preprocess_content(content)
        assert "**標題**" in result
        assert "<u>" not in result

    def test_no_html(self):
        content = "純文字內容"
        assert preprocess_content(content) == "純文字內容"

    def test_inline_underline_not_converted(self):
        # 非獨行的 <u> 不轉換為 bold，只去除標籤
        result = preprocess_content("這是 <u>行內</u> 文字")
        assert result == "這是 行內 文字"
        assert "**" not in result


# ─── inject_attendees ─────────────────────────────────────────────────────────

class TestInjectAttendees:
    def test_injects_after_date_line(self):
        content = "# 會議記錄\n- 日期：2026/03/13\n- 地點：線上"
        result = inject_attendees(content, ["Alice", "Bob"])
        lines = result.split("\n")
        date_idx = next(i for i, l in enumerate(lines) if "日期" in l)
        assert lines[date_idx + 1] == "- 與會者：Alice, Bob"

    def test_injects_after_h1_when_no_date(self):
        content = "# 會議記錄\n正文內容"
        result = inject_attendees(content, ["Alice"])
        lines = result.split("\n")
        assert lines[1] == "- 與會者：Alice"

    def test_skips_if_already_has_attendees(self):
        content = "# 會議記錄\n- 與會者：Alice"
        result = inject_attendees(content, ["Bob"])
        assert result.count("與會者") == 1

    def test_empty_attendees_returns_unchanged(self):
        content = "# 會議記錄"
        assert inject_attendees(content, []) == content

    def test_prepends_when_no_heading_or_date(self):
        content = "純文字"
        result = inject_attendees(content, ["Alice"])
        assert result.startswith("- 與會者：Alice")


# ─── _parse_inline_bold ───────────────────────────────────────────────────────

class TestParseInlineBold:
    def test_no_bold(self):
        plain, ranges = _parse_inline_bold("普通文字")
        assert plain == "普通文字"
        assert ranges == []

    def test_single_bold(self):
        plain, ranges = _parse_inline_bold("**重要**事項")
        assert plain == "重要事項"
        assert ranges == [(0, 2)]

    def test_multiple_bold(self):
        plain, ranges = _parse_inline_bold("**A** 和 **B**")
        assert plain == "A 和 B"
        assert len(ranges) == 2

    def test_bold_at_end(self):
        plain, ranges = _parse_inline_bold("前綴 **結尾**")
        assert plain == "前綴 結尾"
        assert ranges == [(3, 5)]


# ─── _classify_line ───────────────────────────────────────────────────────────

class TestClassifyLine:
    def test_heading_h1(self):
        kind, level, plain, _ = _classify_line("# 標題")
        assert kind == "heading"
        assert level == 1
        assert plain == "標題"

    def test_heading_h3(self):
        kind, level, _, _ = _classify_line("### 小標題")
        assert kind == "heading"
        assert level == 3

    def test_bullet_dash(self):
        kind, level, plain, _ = _classify_line("- 項目一")
        assert kind == "bullet"
        assert plain == "項目一"

    def test_bullet_star(self):
        kind, _, plain, _ = _classify_line("* 項目二")
        assert kind == "bullet"
        assert plain == "項目二"

    def test_indented_bullet(self):
        kind, level, _, _ = _classify_line("  - 縮排項目")
        assert kind == "bullet"
        assert level == 2

    def test_horizontal_rule(self):
        kind, _, plain, _ = _classify_line("---")
        assert kind == "normal"
        assert plain == ""

    def test_normal_text(self):
        kind, _, plain, _ = _classify_line("普通段落文字")
        assert kind == "normal"
        assert plain == "普通段落文字"


# ─── _parse_table_rows ────────────────────────────────────────────────────────

class TestParseTableRows:
    def test_basic_table(self):
        lines = [
            "| 欄位A | 欄位B |",
            "| --- | --- |",
            "| 值1 | 值2 |",
        ]
        rows = _parse_table_rows(lines)
        assert rows == [["欄位A", "欄位B"], ["值1", "值2"]]

    def test_separator_skipped(self):
        lines = ["| A | B |", "|---|---|", "| 1 | 2 |"]
        rows = _parse_table_rows(lines)
        assert len(rows) == 2

    def test_empty_cells(self):
        lines = ["| A |  |", "|---|---|", "|  | B |"]
        rows = _parse_table_rows(lines)
        assert rows[1] == ["", "B"]


# ─── cleanup_segments ─────────────────────────────────────────────────────────

class TestCleanupSegments:
    def test_auto_delete(self, tmp_path):
        files = [tmp_path / f"seg_{i}.mp3" for i in range(3)]
        for f in files:
            f.write_bytes(b"")
        cleanup_segments(files, auto_delete=True)
        assert all(not f.exists() for f in files)

    def test_no_delete_when_false(self, tmp_path, monkeypatch):
        files = [tmp_path / "seg.mp3"]
        files[0].write_bytes(b"")
        monkeypatch.setattr("builtins.input", lambda _: "n")
        cleanup_segments(files, auto_delete=False)
        assert files[0].exists()

    def test_interactive_delete(self, tmp_path, monkeypatch):
        files = [tmp_path / "seg.mp3"]
        files[0].write_bytes(b"")
        monkeypatch.setattr("builtins.input", lambda _: "y")
        cleanup_segments(files, auto_delete=False)
        assert not files[0].exists()
