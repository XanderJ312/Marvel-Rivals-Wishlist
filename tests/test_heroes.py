import pytest

from app import heroes as heroes_mod
from app import storage
from app.wiki import WikiError

ADAM_IMG = "https://static.wikia.nocookie.net/marvel-rivals/images/7/7e/Adam_Warlock_Icon.png/revision/latest?cb=20250108204921"


def test_parse_heroes(fixture_html):
    heroes = heroes_mod.parse_heroes(fixture_html("heroes_page.html"))

    assert [h["id"] for h in heroes] == ["adam-warlock", "bruce-banner", "gorr-the-god-butcher"]

    adam = heroes[0]
    assert adam["name"] == "Adam Warlock"  # whitespace collapsed
    assert adam["role"] == "Strategist"
    assert adam["color"] == "#e29058"
    assert adam["imageRemote"] == ADAM_IMG  # lazy-loaded data-src wins over the data: placeholder
    assert adam["cardImageRemote"].endswith("Hero_Card_Adam_Warlock.png/revision/latest?cb=1")
    assert adam["wikiUrl"] == "https://marvelrivals.fandom.com/wiki/Adam_Warlock"

    bruce = heroes[1]
    assert bruce["role"] == "Vanguard"
    assert bruce["cardImageRemote"] is None

    gorr = heroes[2]
    assert gorr["role"] == "Duelist"
    assert gorr["imageRemote"] is None
    assert gorr["wikiUrl"] is None


def test_parse_heroes_on_unknown_markup_returns_empty_list():
    assert heroes_mod.parse_heroes("<div><p>Page redesigned</p></div>") == []


class FakeWiki:
    def __init__(self, html, broken_urls=()):
        self.html = html
        self.broken_urls = set(broken_urls)
        self.downloaded = []

    async def parse_html(self, page):
        assert page == "Heroes"
        return self.html

    async def download(self, url):
        if url in self.broken_urls:
            raise WikiError("HTTP 404")
        self.downloaded.append(url)
        return b"img:" + url.encode()


def _many_heroes_html(n):
    cards = "".join(
        f'<div class="herocard-wrapper"><div class="herocard-name">Hero {i}</div>'
        f'<div class="herocard-bg-normal"><img src="https://cdn.example/h{i}.png/revision/latest?cb=1"></div></div>'
        for i in range(n)
    )
    return f"<div>{cards}</div>"


async def test_update_heroes_saves_sorted_list_and_images(data_dir):
    wiki = FakeWiki(_many_heroes_html(12))
    result = await heroes_mod.update_heroes(wiki)

    assert len(result) == 12
    saved = storage.read_json(storage.HEROES_FILE)
    assert [h["name"] for h in saved["heroes"]] == sorted((f"Hero {i}" for i in range(12)), key=str.lower)
    assert saved["heroes"][0]["image"] == "/images/heroes/hero-0.png"
    assert (data_dir / "images" / "heroes" / "hero-0.png").exists()
    assert len(wiki.downloaded) == 12


async def test_update_heroes_downloads_only_new_or_changed_images(data_dir):
    await heroes_mod.update_heroes(FakeWiki(_many_heroes_html(12)))

    changed = _many_heroes_html(12).replace("h3.png/revision/latest?cb=1", "h3.png/revision/latest?cb=2")
    wiki = FakeWiki(changed)
    await heroes_mod.update_heroes(wiki)

    assert wiki.downloaded == ["https://cdn.example/h3.png/revision/latest?cb=2"]


async def test_update_heroes_falls_back_to_remote_url_when_download_fails(data_dir):
    url = "https://cdn.example/h5.png/revision/latest?cb=1"
    await heroes_mod.update_heroes(FakeWiki(_many_heroes_html(12), broken_urls=[url]))

    hero5 = next(h for h in storage.read_json(storage.HEROES_FILE)["heroes"] if h["id"] == "hero-5")
    assert hero5["image"] == url


async def test_update_heroes_refuses_to_overwrite_good_data_with_suspiciously_short_list(data_dir):
    storage.write_json(storage.HEROES_FILE, {"heroes": [{"id": "keep-me"}]})

    with pytest.raises(WikiError):
        await heroes_mod.update_heroes(FakeWiki(_many_heroes_html(3)))

    assert storage.read_json(storage.HEROES_FILE) == {"heroes": [{"id": "keep-me"}]}
