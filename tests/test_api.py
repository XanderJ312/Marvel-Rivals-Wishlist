import pytest
from fastapi.testclient import TestClient

from app import main, storage


@pytest.fixture
def client(data_dir):
    main._cache.update(key=None, data=None)
    return TestClient(main.app)  # without `with`: the scheduler and the bot are not started


def _skin(sid, hero_id, hero_name, default=False, image=None):
    return {"id": sid, "heroId": hero_id, "heroName": hero_name, "name": sid,
            "rarity": "Default" if default else "Epic", "isDefault": default, "image": image}


def test_catalog_is_empty_without_data(client):
    body = client.get("/api/catalog").json()
    assert body["heroes"] == []
    assert body["skins"] == []
    assert body["skinsUpdatedAt"] is None


def test_catalog_merges_heroes_and_skins(client):
    storage.write_json(storage.HEROES_FILE, {"updatedAt": "2026-11-15T00:00:00+00:00", "heroes": [
        {"id": "groot", "name": "Groot", "role": "Vanguard", "image": "/images/heroes/groot.png"},
        {"id": "angela", "name": "Angela", "role": "Vanguard", "image": None},
    ]})
    storage.write_json(storage.SKINS_FILE, {"updatedAt": "2026-11-20T00:00:00+00:00", "skins": [
        _skin("groot--default", "groot", "Groot", default=True, image="/images/skins/groot--default.png"),
        _skin("groot--a", "groot", "Groot"),
        _skin("groot--b", "groot", "Groot"),
        _skin("angela--default", "angela", "Angela", default=True, image="/images/skins/angela--default.png"),
        # hero that is not (yet) on the heroes page
        _skin("blade--default", "blade", "Blade", default=True, image="/images/skins/blade--default.png"),
        _skin("blade--daybreak", "blade", "Blade"),
    ]})

    body = client.get("/api/catalog").json()
    heroes = {h["id"]: h for h in body["heroes"]}

    assert [h["name"] for h in body["heroes"]] == ["Angela", "Blade", "Groot"]  # sorted by name
    assert heroes["groot"]["skinCount"] == 2  # default skins are not counted
    assert heroes["groot"]["image"] == "/images/heroes/groot.png"  # own image is kept
    assert heroes["angela"]["image"] == "/images/skins/angela--default.png"  # default skin as fallback
    assert heroes["blade"]["role"] is None and heroes["blade"]["skinCount"] == 1
    assert len(body["skins"]) == 6
    assert body["skinsUpdatedAt"] == "2026-11-20T00:00:00+00:00"


def test_catalog_does_not_modify_saved_heroes(client):
    storage.write_json(storage.HEROES_FILE, {"heroes": [{"id": "groot", "name": "Groot", "image": None}]})
    storage.write_json(storage.SKINS_FILE, {"skins": [_skin("groot--a", "groot", "Groot")]})
    client.get("/api/catalog")
    assert "skinCount" not in storage.read_json(storage.HEROES_FILE)["heroes"][0]


def test_catalog_is_recomputed_after_data_changes(client):
    storage.write_json(storage.HEROES_FILE, {"heroes": [{"id": "groot", "name": "Groot"}]})
    assert len(client.get("/api/catalog").json()["heroes"]) == 1

    main._cache["key"] = ("stale",)  # simulate a file change detected via mtime
    storage.write_json(storage.HEROES_FILE, {"heroes": [{"id": "groot", "name": "Groot"}, {"id": "hela", "name": "Hela"}]})
    assert len(client.get("/api/catalog").json()["heroes"]) == 2


def test_status(client):
    storage.write_json(storage.SKINS_FILE, {"skins": [_skin("groot--a", "groot", "Groot")]})
    storage.write_json(storage.STATE_FILE, {"unmatched": ["Blade"], "skinsFailedAt": None})

    body = client.get("/api/status").json()
    assert body["heroes"] == 1
    assert body["skins"] == 1
    assert body["unmatched"] == ["Blade"]
    assert body["telegram"]["connected"] is False


def test_frontend_is_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Rivals Wishlist" in r.text
    assert client.get("/app.js").status_code == 200
