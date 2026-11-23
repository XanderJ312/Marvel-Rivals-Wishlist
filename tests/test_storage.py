import json

import pytest

from app import storage


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Adam Warlock", "adam-warlock"),
        ("Cloak & Dagger", "cloak-dagger"),
        ("Shou-Lao's Champion", "shou-lao-s-champion"),
        ("Pokémon Café", "pokemon-cafe"),
        ("  --Spider-Man--  ", "spider-man"),
        ("Ven#m", "ven-m"),
        ("!!!", "x"),
        ("", "x"),
    ],
)
def test_slugify(text, expected):
    assert storage.slugify(text) == expected


def test_read_json_returns_default_for_missing_file(data_dir):
    assert storage.read_json("nope.json", {"a": 1}) == {"a": 1}


def test_read_json_returns_default_for_broken_file(data_dir):
    (data_dir / "broken.json").write_text("{not json", "utf-8")
    assert storage.read_json("broken.json", []) == []


def test_write_json_round_trip_keeps_unicode(data_dir):
    payload = {"name": "Łucznik", "skins": [1, 2, 3]}
    storage.write_json("sub/dir/file.json", payload)

    written = data_dir / "sub" / "dir" / "file.json"
    assert json.loads(written.read_text("utf-8")) == payload
    assert "Łucznik" in written.read_text("utf-8")  # ensure_ascii=False
    assert storage.read_json("sub/dir/file.json") == payload


def test_write_json_leaves_no_temp_file(data_dir):
    storage.write_json("heroes.json", {"heroes": []})
    storage.write_json("heroes.json", {"heroes": [{"id": "x"}]})
    assert sorted(p.name for p in data_dir.iterdir()) == ["heroes.json"]
    assert storage.read_json("heroes.json") == {"heroes": [{"id": "x"}]}


def test_write_bytes(data_dir):
    storage.write_bytes("images/skins/a.png", b"\x89PNG")
    assert (data_dir / "images" / "skins" / "a.png").read_bytes() == b"\x89PNG"


def test_now_iso_is_utc_without_microseconds():
    value = storage.now_iso()
    assert value.endswith("+00:00")
    assert "." not in value
