"""Tests for README generation."""

import json

from calendar_splitter.readme import generate_readme


class TestGenerateReadme:
    def test_generates_table_from_tokens(self, tmp_path):
        token_path = tmp_path / "tokens.json"
        token_path.write_text(json.dumps({
            "IS1200": "abc123",
            "DH2642": "def456",
        }), encoding="utf-8")

        content = generate_readme(
            token_map_path=token_path,
            base_url="https://example.com/feeds",
        )
        assert "| `DH2642` | `def456` |" in content
        assert "| `IS1200` | `abc123` |" in content
        assert "https://example.com/feeds/IS1200--abc123.ics" in content
        assert "Last updated:" in content

    def test_sorted_alphabetically(self, tmp_path):
        token_path = tmp_path / "tokens.json"
        token_path.write_text(json.dumps({
            "ZZ9999": "zzz",
            "AA1111": "aaa",
        }), encoding="utf-8")

        content = generate_readme(token_map_path=token_path, base_url="https://x.io")
        aa_pos = content.index("AA1111")
        zz_pos = content.index("ZZ9999")
        assert aa_pos < zz_pos

    def test_uses_header_template(self, tmp_path):
        token_path = tmp_path / "tokens.json"
        token_path.write_text(json.dumps({"IS1200": "abc"}), encoding="utf-8")

        header = tmp_path / "README.header.md"
        header.write_text(
            "# My Feeds\n\n<!-- BEGIN FEED TABLE -->\n<!-- END FEED TABLE -->\n",
            encoding="utf-8",
        )

        content = generate_readme(
            token_map_path=token_path,
            base_url="https://x.io",
            header_path=header,
        )
        assert content.startswith("# My Feeds")
        assert "IS1200" in content

    def test_uses_footer_template(self, tmp_path):
        token_path = tmp_path / "tokens.json"
        token_path.write_text(json.dumps({}), encoding="utf-8")

        footer = tmp_path / "README.footer.md"
        footer.write_text("---\n", encoding="utf-8")

        content = generate_readme(
            token_map_path=token_path,
            base_url="https://x.io",
            footer_path=footer,
        )
        assert "---" in content

    def test_writes_output_file(self, tmp_path):
        token_path = tmp_path / "tokens.json"
        token_path.write_text(json.dumps({"TEST": "tok"}), encoding="utf-8")

        out = tmp_path / "README.md"
        generate_readme(
            token_map_path=token_path,
            base_url="https://x.io",
            output_path=out,
        )
        assert out.exists()
        assert "TEST" in out.read_text(encoding="utf-8")

    def test_empty_token_map(self, tmp_path):
        token_path = tmp_path / "tokens.json"
        token_path.write_text("{}", encoding="utf-8")

        content = generate_readme(token_map_path=token_path, base_url="https://x.io")
        assert "BEGIN FEED TABLE" in content
        assert "Last updated:" in content

    def test_missing_token_file(self, tmp_path):
        content = generate_readme(
            token_map_path=tmp_path / "nonexistent.json",
            base_url="https://x.io",
        )
        assert "BEGIN FEED TABLE" in content

    def test_strips_trailing_slash_from_base_url(self, tmp_path):
        token_path = tmp_path / "tokens.json"
        token_path.write_text(json.dumps({"X": "y"}), encoding="utf-8")

        content = generate_readme(token_map_path=token_path, base_url="https://x.io/feeds/")
        assert "https://x.io/feeds/X--y.ics" in content
        assert "feeds//X" not in content
