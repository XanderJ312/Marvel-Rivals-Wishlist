import pytest

from app import skins as skins_mod
from app import storage

HEROES = [
    {"id": "adam-warlock", "name": "Adam Warlock"},
    {"id": "bruce-banner", "name": "Bruce Banner"},
    {"id": "gorr-the-god-butcher", "name": "Gorr the God Butcher"},
    {"id": "spider-man", "name": "Spider-Man"},
    {"id": "spider-woman", "name": "Spider-Woman"},
]


# --- matching template names to heroes ---------------------------------------------
@pytest.mark.parametrize(
    ("cosmetics_name", "expected"),
    [
        ("Adam Warlock", "adam-warlock"),  # exact
        ("Hulk", "bruce-banner"),  # alias
        ("Gorr", "gorr-the-god-butcher"),  # unique prefix
        ("Spider", None),  # ambiguous prefix
        ("Blade", None),  # unknown
    ],
)
def test_match_hero(cosmetics_name, expected):
    hero = skins_mod.match_hero(cosmetics_name, HEROES)
    assert (hero["id"] if hero else None) == expected


# --- template parsing --------------------------------------------------------------
def test_parse_template(fixture_html):
    skins = skins_mod.parse_template(fixture_html("costumes_template.html"), "adam-warlock", "Adam Warlock")

    assert [(s["id"], s["type"], s["rarity"]) for s in skins] == [
        ("adam-warlock--default", "costume", "Default"),
        ("adam-warlock--cosmic-warlock", "costume", "Legendary"),
        ("adam-warlock--cosmic-warlock-2", "costume", "Epic"),
        ("adam-warlock--king-in-white", "recolor", None),
    ]

    default, cosmic = skins[0], skins[1]
    assert default["isDefault"] is True
    assert cosmic["isDefault"] is False
    assert cosmic["name"] == "Cosmic Warlock"
    assert cosmic["heroId"] == "adam-warlock"
    assert cosmic["heroName"] == "Adam Warlock"
    assert cosmic["theme"] == "Cosmic"
    assert cosmic["source"] == "Battle Pass"
    assert cosmic["cost"] == "1,800 Units"
    assert cosmic["imageRemote"].endswith("Cosmic_Warlock_Icon.png/revision/latest/scale-to-width-down/300?cb=20260110020954")
    assert cosmic["image"] is None
    assert cosmic["wikiUrl"] == "https://marvelrivals.fandom.com/wiki/Cosmic_Warlock"

    assert skins[3]["name"] == "King in White"  # name taken from the image alt


def test_parse_template_without_tabs_treats_everything_as_costumes():
    html = """
    <div class="wikia-gallery-item">
      <img class="thumbimage" src="https://cdn.example/a.png">
      <div class="lightbox-caption"><div class="emote-text emote-rarity-Rare"><a href="/wiki/A">Skin A</a></div></div>
    </div>"""
    [skin] = skins_mod.parse_template(html, "groot", "Groot")
    assert skin["type"] == "costume"
    assert skin["rarity"] == "Rare"


# --- fake wiki for the update tests ------------------------------------------------
def gallery(*items):
    """Minimal template HTML: (name, rarity, image url) tuples."""
    body = "".join(
        f'<div class="wikia-gallery-item"><img class="thumbimage" src="{url}">'
        f'<div class="lightbox-caption"><div class="emote-text emote-rarity-{rarity}">'
        f'<a href="/wiki/{name}">{name}</a></div></div></div>'
        for name, rarity, url in items
    )
    return f"<div>{body}</div>"


class FakeWiki:
    def __init__(self, templates: dict[str, tuple[int, str]]):
        """templates: {hero name in template title: (revid, html)}"""
        self.templates = templates
        self.parsed: list[str] = []
        self.downloaded: list[str] = []

    async def query_all(self, **params):
        assert params["gapprefix"] == "COSMETICS - "
        pages = [
            {"title": f"Template:COSMETICS - {name} Costumes", "revisions": [{"revid": revid}]}
            for name, (revid, _) in self.templates.items()
        ]
        pages.append({"title": "Template:COSMETICS - Navbox"})  # not a costumes template
        return pages

    async def parse_html(self, page):
        self.parsed.append(page)
        name = page[len("Template:COSMETICS - "):-len(" Costumes")]
        return self.templates[name][1]

    async def download(self, url):
        self.downloaded.append(url)
        return b"png"


ADAM_V1 = gallery(("Default", "Default", "https://cdn.example/adam-default.png?cb=1"),
                  ("Cosmic Warlock", "Legendary", "https://cdn.example/adam-cosmic.png?cb=1"))
HULK_V1 = gallery(("Hero Hulk", "Epic", "https://cdn.example/hulk-hero.png?cb=1"))


async def test_list_costume_templates():
    wiki = FakeWiki({"Adam Warlock": (11, ADAM_V1), "Hulk": (22, HULK_V1)})
    assert await skins_mod.list_costume_templates(wiki) == {
        "Adam Warlock": {"title": "Template:COSMETICS - Adam Warlock Costumes", "revid": 11},
        "Hulk": {"title": "Template:COSMETICS - Hulk Costumes", "revid": 22},
    }


async def test_update_skins_first_run_downloads_everything(data_dir):
    wiki = FakeWiki({"Adam Warlock": (11, ADAM_V1), "Hulk": (22, HULK_V1)})
    unmatched = await skins_mod.update_skins(wiki, HEROES)

    assert unmatched == []
    saved = storage.read_json(storage.SKINS_FILE)["skins"]
    assert [s["id"] for s in saved] == [
        "adam-warlock--default", "adam-warlock--cosmic-warlock", "bruce-banner--hero-hulk",
    ]
    assert saved[1]["image"] == "/images/skins/adam-warlock--cosmic-warlock.png"
    assert (data_dir / "images" / "skins" / "adam-warlock--cosmic-warlock.png").exists()
    assert len(wiki.downloaded) == 3

    state = storage.read_json(storage.STATE_FILE)
    assert state["templates"]["Hulk"] == {"revid": 22, "heroId": "bruce-banner"}


async def test_update_skins_only_reparses_changed_templates(data_dir):
    await skins_mod.update_skins(FakeWiki({"Adam Warlock": (11, ADAM_V1), "Hulk": (22, HULK_V1)}), HEROES)

    hulk_v2 = gallery(("Hero Hulk", "Epic", "https://cdn.example/hulk-hero.png?cb=1"),
                      ("Gamma Gladiator", "Legendary", "https://cdn.example/hulk-gamma.png?cb=1"))
    wiki = FakeWiki({"Adam Warlock": (11, ADAM_V1), "Hulk": (23, hulk_v2)})
    await skins_mod.update_skins(wiki, HEROES)

    assert wiki.parsed == ["Template:COSMETICS - Hulk Costumes"]
    assert wiki.downloaded == ["https://cdn.example/hulk-gamma.png?cb=1"]  # unchanged images are kept
    ids = [s["id"] for s in storage.read_json(storage.SKINS_FILE)["skins"]]
    assert "bruce-banner--gamma-gladiator" in ids
    assert "adam-warlock--cosmic-warlock" in ids


async def test_update_skins_full_rebuild_reparses_everything(data_dir):
    templates = {"Adam Warlock": (11, ADAM_V1), "Hulk": (22, HULK_V1)}
    await skins_mod.update_skins(FakeWiki(templates), HEROES)

    wiki = FakeWiki(templates)
    await skins_mod.update_skins(wiki, HEROES, full=True)
    assert len(wiki.parsed) == 2
    assert wiki.downloaded == []


async def test_update_skins_removes_images_of_deleted_skins(data_dir):
    await skins_mod.update_skins(FakeWiki({"Adam Warlock": (11, ADAM_V1)}), HEROES)
    adam_v2 = gallery(("Default", "Default", "https://cdn.example/adam-default.png?cb=1"))
    await skins_mod.update_skins(FakeWiki({"Adam Warlock": (12, adam_v2)}), HEROES)

    files = sorted(p.name for p in (data_dir / "images" / "skins").iterdir())
    assert files == ["adam-warlock--default.png"]


async def test_update_skins_reports_unmatched_templates_but_keeps_their_skins(data_dir):
    wiki = FakeWiki({"Adam Warlock": (11, ADAM_V1), "Blade": (5, gallery(("Daybreak", "Epic", "https://cdn.example/b.png")))})
    unmatched = await skins_mod.update_skins(wiki, HEROES)

    assert unmatched == ["Blade"]
    blade = [s for s in storage.read_json(storage.SKINS_FILE)["skins"] if s["heroId"] == "blade"]
    assert [s["name"] for s in blade] == ["Daybreak"]


async def test_update_skins_keeps_previous_data_when_template_is_empty(data_dir):
    await skins_mod.update_skins(FakeWiki({"Adam Warlock": (11, ADAM_V1)}), HEROES)
    await skins_mod.update_skins(FakeWiki({"Adam Warlock": (12, "<div>broken</div>")}), HEROES)

    ids = [s["id"] for s in storage.read_json(storage.SKINS_FILE)["skins"]]
    assert ids == ["adam-warlock--default", "adam-warlock--cosmic-warlock"]


async def test_update_skins_aborts_when_wiki_returns_no_templates(data_dir):
    class EmptyWiki(FakeWiki):
        async def query_all(self, **params):
            return []

    with pytest.raises(skins_mod.WikiError):
        await skins_mod.update_skins(EmptyWiki({}), HEROES)
