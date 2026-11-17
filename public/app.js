(() => {
  const tg = window.Telegram?.WebApp;
  if (tg) { tg.ready(); tg.expand(); }

  // --- i18n ---
  const lang = (tg?.initDataUnsafe?.user?.language_code || navigator.language || 'en').slice(0, 2);
  document.documentElement.lang = lang === 'pl' ? 'pl' : 'en';
  const plural = (n, one, few, many) => (n === 1 ? one : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? few : many);
  const T = {
    pl: {
      search: 'Szukaj bohatera', all: 'Wszyscy', back: 'Wróć',
      roles: { Vanguard: 'Vanguard', Duelist: 'Duelist', Strategist: 'Strategist' },
      skinsCount: (n) => `${n} ${plural(n, 'skin', 'skiny', 'skinów')}`,
      costumes: 'Kostiumy', recolors: 'Recolory', anyRarity: 'Każda rzadkość',
      noHeroes: 'Żaden bohater nie pasuje do wyszukiwania.',
      noSkins: 'Brak skinów dla tego filtra.',
      loading: 'Wczytuję skiny…',
      noData: 'Nie ma jeszcze danych. Pierwsze pobieranie z wiki trwa kilka minut – odśwież stronę za chwilę.',
      error: 'Nie udało się wczytać danych z serwera.', retry: 'Spróbuj ponownie',
      notFound: 'Nie ma takiego bohatera.',
      credits: 'Dane: <a href="https://marvelrivals.fandom.com" target="_blank" rel="noopener">Marvel Rivals Wiki</a> (CC BY-SA). Aplikacja fanowska, niezwiązana z NetEase ani Marvel.',
    },
    en: {
      search: 'Search heroes', all: 'All', back: 'Back',
      roles: { Vanguard: 'Vanguard', Duelist: 'Duelist', Strategist: 'Strategist' },
      skinsCount: (n) => `${n} ${n === 1 ? 'skin' : 'skins'}`,
      costumes: 'Costumes', recolors: 'Recolors', anyRarity: 'Any rarity',
      noHeroes: 'No hero matches your search.',
      noSkins: 'No skins match this filter.',
      loading: 'Loading skins…',
      noData: 'No data yet. The first download from the wiki takes a few minutes – refresh shortly.',
      error: 'Could not load data from the server.', retry: 'Try again',
      notFound: 'Hero not found.',
      credits: 'Data: <a href="https://marvelrivals.fandom.com" target="_blank" rel="noopener">Marvel Rivals Wiki</a> (CC BY-SA). Fan-made app, not affiliated with NetEase or Marvel.',
    },
  }[lang === 'pl' ? 'pl' : 'en'];

  const RARITY_ORDER = ['legendary', 'epic', 'rare', 'uncommon', 'common', 'default'];
  const ROLE_ORDER = ['Vanguard', 'Duelist', 'Strategist'];
  const $ = (id) => document.getElementById(id);
  const view = $('view');
  $('credits').innerHTML = T.credits;

  const h = (tag, attrs = {}, ...children) => {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else if (k === 'style') Object.assign(el.style, v);
      else el.setAttribute(k, v === true ? '' : v);
    }
    for (const c of children.flat(3)) if (c != null && c !== false) el.append(c);
    return el;
  };
  const norm = (s) => (s || '').toLowerCase();
  const rkey = (r) => norm(r).replace(/[^a-z]/g, '') || 'default';
  const byRarity = (a, b) => (RARITY_ORDER.indexOf(rkey(a.rarity)) + 1 || 50) - (RARITY_ORDER.indexOf(rkey(b.rarity)) + 1 || 50) || a.name.localeCompare(b.name);

  const img = (src, alt, onFail) => {
    if (!src) return onFail();
    const i = h('img', { src, alt, loading: 'lazy', decoding: 'async' });
    i.onerror = () => i.replaceWith(onFail());
    return i;
  };

  // --- State ---
  let data = { heroes: [], skins: [] };
  let heroesById = new Map();
  let skinsByHero = new Map();
  let skinsById = new Map();
  const ui = { role: '', query: '', tab: {}, rarity: {} };

  // --- Skin card ---
  function skinCard(s) {
    const tags = [s.theme, s.source].filter(Boolean);
    return h('article', { class: 'skin', 'data-rarity': rkey(s.rarity) },
      h('div', { class: 'art' },
        img(s.image, s.name, () => h('span', {})),
        s.rarity ? h('span', { class: 'rarity' }, s.rarity) : null),
      h('div', { class: 'body' },
        h('h3', {}, s.name),
        tags.length ? h('div', { class: 'tags' }, tags.map((t) => h('span', { class: 'tag' }, t))) : null));
  }

  // --- Heroes ---
  function heroCard(hero) {
    const all = (skinsByHero.get(hero.id) || []).filter((s) => !s.isDefault);
    return h('a', { class: 'hero-card', href: `#/hero/${hero.id}`, style: { '--hero': hero.color || '' } },
      img(hero.image, '', () => h('span', { class: 'ph' }, hero.name[0])),
      h('div', { class: 'meta' },
        h('p', { class: 'hero-name' }, hero.name),
        h('div', { class: 'hero-sub' },
          hero.role ? h('span', {}, T.roles[hero.role] || hero.role) : null,
          h('span', {}, T.skinsCount(all.length)))));
  }

  function renderHeroes() {
    const roles = ROLE_ORDER.filter((r) => data.heroes.some((x) => x.role === r));
    const grid = h('section', { class: 'heroes' });
    const empty = h('p', { class: 'status', hidden: true }, T.noHeroes);
    const fill = () => {
      const q = norm(ui.query.trim());
      const list = data.heroes.filter((x) => (!ui.role || x.role === ui.role) && (!q || norm(x.name).includes(q)));
      grid.replaceChildren(...list.map(heroCard));
      empty.hidden = list.length > 0;
    };
    const chip = (value, label) => h('button', {
      class: 'chip', type: 'button', 'aria-pressed': String(ui.role === value),
      onclick: (e) => {
        ui.role = value;
        e.currentTarget.parentElement.querySelectorAll('.chip').forEach((c) => c.setAttribute('aria-pressed', String(c === e.currentTarget)));
        fill();
      },
    }, label);
    const search = h('input', { class: 'search', type: 'search', placeholder: T.search, value: ui.query, 'aria-label': T.search, autocomplete: 'off' });
    search.addEventListener('input', () => { ui.query = search.value; fill(); });

    view.replaceChildren(
      h('div', { class: 'tools' }, search, h('div', { class: 'chips', role: 'group' }, chip('', T.all), roles.map((r) => chip(r, T.roles[r] || r)))),
      grid, empty);
    fill();
  }

  function renderHero(id) {
    const hero = heroesById.get(id);
    if (!hero) { view.replaceChildren(h('p', { class: 'status' }, T.notFound)); return; }
    const all = (skinsByHero.get(id) || []).filter((s) => !s.isDefault);
    const types = [...new Set(all.map((s) => s.type))].sort((a, b) => (a === 'costume' ? -1 : b === 'costume' ? 1 : 0));
    if (!types.includes(ui.tab[id])) ui.tab[id] = types[0];

    const grid = h('section', { class: 'skins' });
    const empty = h('p', { class: 'status', hidden: true }, T.noSkins);
    const rarityChips = h('div', { class: 'chips', role: 'group' });
    const sub = [hero.role ? (T.roles[hero.role] || hero.role) : null, T.skinsCount(all.length)].filter(Boolean).join(', ');

    const fill = () => {
      const inTab = all.filter((s) => s.type === ui.tab[id]);
      const rarities = [...new Set(inTab.map((s) => rkey(s.rarity)))].sort((a, b) => RARITY_ORDER.indexOf(a) - RARITY_ORDER.indexOf(b));
      if (ui.rarity[id] && !rarities.includes(ui.rarity[id])) ui.rarity[id] = '';
      const chip = (value, label) => h('button', {
        class: 'chip', type: 'button', 'aria-pressed': String((ui.rarity[id] || '') === value),
        onclick: () => { ui.rarity[id] = value; fill(); },
      }, label);
      const labelOf = (k) => inTab.find((s) => rkey(s.rarity) === k)?.rarity || k;
      rarityChips.replaceChildren(...(rarities.length > 1 ? [chip('', T.anyRarity), ...rarities.map((k) => chip(k, labelOf(k)))] : []));
      const list = inTab.filter((s) => !ui.rarity[id] || rkey(s.rarity) === ui.rarity[id]).sort(byRarity);
      grid.replaceChildren(...list.map((s) => skinCard(s)));
      empty.hidden = list.length > 0;
    };

    const tabLabel = (t) => (t === 'costume' ? T.costumes : t === 'recolor' ? T.recolors : t);
    const tabs = types.length > 1 ? h('div', { class: 'chips', role: 'tablist' }, types.map((t) => h('button', {
      class: 'chip', type: 'button', role: 'tab', 'aria-pressed': String(ui.tab[id] === t), 'aria-selected': String(ui.tab[id] === t),
      onclick: (e) => {
        ui.tab[id] = t;
        e.currentTarget.parentElement.querySelectorAll('.chip').forEach((c) => {
          const on = c === e.currentTarget; c.setAttribute('aria-pressed', String(on)); c.setAttribute('aria-selected', String(on));
        });
        fill();
      },
    }, tabLabel(t)))) : null;

    view.replaceChildren(
      h('header', { class: 'banner has-back', style: { '--hero': hero.color || '' } },
        h('button', { class: 'back', type: 'button', onclick: () => history.back() }, `‹ ${T.back}`),
        h('div', {}, h('h1', {}, hero.name), h('p', {}, sub)),
        img(hero.image, '', () => h('span', {}))),
      h('div', { class: 'tools' }, tabs, rarityChips),
      grid, empty);
    fill();
    window.scrollTo(0, 0);
  }

  // --- Routing: #/ (heroes), #/hero/<id> ---
  let routing = false;
  function route() {
    const hash = location.hash.replace(/^#/, '') || '/';
    const m = hash.match(/^\/hero\/([^/]+)$/);
    if (m) renderHero(decodeURIComponent(m[1]));
    else renderHeroes();
  }

  async function init() {
    view.replaceChildren(h('p', { class: 'status' }, T.loading));
    try {
      const res = await fetch('api/catalog');
      if (!res.ok) throw new Error(res.status);
      data = await res.json();
      heroesById = new Map(data.heroes.map((x) => [x.id, x]));
      skinsById = new Map(data.skins.map((s) => [s.id, s]));
      skinsByHero = new Map();
      for (const s of data.skins) { if (!skinsByHero.has(s.heroId)) skinsByHero.set(s.heroId, []); skinsByHero.get(s.heroId).push(s); }
      if (!data.heroes.length) { view.replaceChildren(h('p', { class: 'status' }, T.noData)); return; }
      if (!routing) { window.addEventListener('hashchange', route); routing = true; }
      route();
    } catch (e) {
      console.error(e);
      view.replaceChildren(h('div', { class: 'status' }, h('p', {}, T.error), h('button', { class: 'btn ghost', type: 'button', onclick: init }, T.retry)));
    }
  }
  init();
})();
