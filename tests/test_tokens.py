"""Tests for token store."""

import json

from calendar_splitter.tokens import TokenStore


class TestTokenStore:
    def test_load_empty(self, tmp_path):
        store = TokenStore(tmp_path / "tokens.json")
        store.load()
        assert store.map == {}

    def test_load_existing(self, tmp_path):
        path = tmp_path / "tokens.json"
        path.write_text(json.dumps({"IS1200": "abc123"}), encoding="utf-8")
        store = TokenStore(path)
        store.load()
        assert store.map == {"IS1200": "abc123"}

    def test_get_or_create_existing(self, tmp_path):
        path = tmp_path / "tokens.json"
        path.write_text(json.dumps({"IS1200": "abc123"}), encoding="utf-8")
        store = TokenStore(path)
        store.load()
        token = store.get_or_create("IS1200")
        assert token == "abc123"

    def test_get_or_create_new(self, tmp_path):
        store = TokenStore(tmp_path / "tokens.json")
        store.load()
        token = store.get_or_create("IS1200")
        assert len(token) == 16
        assert token == store.get_or_create("IS1200")

    def test_save_and_reload(self, tmp_path):
        path = tmp_path / "tokens.json"
        store = TokenStore(path)
        store.load()
        store.get_or_create("IS1200")
        store.save()

        store2 = TokenStore(path)
        store2.load()
        assert "IS1200" in store2.map

    def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "nested" / "dir" / "tokens.json"
        store = TokenStore(path)
        store.load()
        store.get_or_create("TEST")
        store.save()
        assert path.exists()

    def test_load_invalid_json(self, tmp_path):
        path = tmp_path / "tokens.json"
        path.write_text("not json", encoding="utf-8")
        store = TokenStore(path)
        store.load()
        assert store.map == {}

    def test_load_non_dict_json(self, tmp_path):
        path = tmp_path / "tokens.json"
        path.write_text("[1,2,3]", encoding="utf-8")
        store = TokenStore(path)
        store.load()
        assert store.map == {}
