(() => {
  const tg = window.Telegram?.WebApp;
  const inTelegram = !!tg?.initData;
  if (tg) { tg.ready(); tg.expand(); }

  // --- i18n ---
  const lang = (tg?.initDataUnsafe?.user?.language_code || navigator.language || 'en').slice(0, 2);
  document.documentElement.lang = lang === 'pl' ? 'pl' : 'en';
  const plural = (n, one, few, many) => (n === 1 ? one : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? few : many);
  const T = {
    pl: {
      mySkins: 'Moje skiny', heroesNav: 'Bohaterowie',
      cart: 'Koszyk', owned: 'Mam', search: 'Szukaj bohatera', all: 'Wszyscy', back: 'Wróć',
      roles: { Vanguard: 'Vanguard', Duelist: 'Duelist', Strategist: 'Strategist' },
      skinsCount: (n) => `${n} ${plural(n, 'skin', 'skiny', 'skinów')}`,
      ownedOf: (o, n) => `masz ${o} z ${n}`,
      costumes: 'Kostiumy', recolors: 'Recolory', anyRarity: 'Każda rzadkość',
      add: 'Do koszyka', inCart: 'W koszyku', have: 'Mam', haveIt: 'Masz', notHave: 'Nie mam',
      markOwned: (name) => `Oznacz „${name}” jako posiadany`,
      noHeroes: 'Żaden bohater nie pasuje do wyszukiwania.',
      noSkins: 'Brak skinów dla tego filtra.',
      emptyCart: 'Koszyk jest pusty. Wybierz bohatera i dodaj skiny, które chcesz kupić.',
      emptyOwned: 'Nie masz jeszcze oznaczonych skinów. Na stronie bohatera kliknij „Mam” przy skinach, które już posiadasz.',
      browse: 'Przeglądaj bohaterów',
      clearCart: 'Wyczyść koszyk', confirmClearCart: 'Usunąć wszystkie skiny z koszyka?',
      loading: 'Wczytuję skiny…',
      noData: 'Nie ma jeszcze danych. Pierwsze pobieranie z wiki trwa kilka minut – odśwież stronę za chwilę.',
      error: 'Nie udało się wczytać danych z serwera.', retry: 'Spróbuj ponownie',
      notFound: 'Nie ma takiego bohatera.',
      credits: 'Dane: <a href="https://marvelrivals.fandom.com" target="_blank" rel="noopener">Marvel Rivals Wiki</a> (CC BY-SA). Aplikacja fanowska, niezwiązana z NetEase ani Marvel.',
    },
    en: {
      mySkins: 'My skins', heroesNav: 'Heroes',
      cart: 'Cart', owned: 'Owned', search: 'Search heroes', all: 'All', back: 'Back',
      roles: { Vanguard: 'Vanguard', Duelist: 'Duelist', Strategist: 'Strategist' },
      skinsCount: (n) => `${n} ${n === 1 ? 'skin' : 'skins'}`,
      ownedOf: (o, n) => `${o} of ${n} owned`,
      costumes: 'Costumes', recolors: 'Recolors', anyRarity: 'Any rarity',
      add: 'Add to cart', inCart: 'In cart', have: 'Own it', haveIt: 'Owned', notHave: 'Not owned',
      markOwned: (name) => `Mark “${name}” as owned`,
      noHeroes: 'No hero matches your search.',
      noSkins: 'No skins match this filter.',
      emptyCart: 'Your cart is empty. Pick a hero and add the skins you want to buy.',
      emptyOwned: 'No owned skins yet. On a hero page, tap “Own it” on skins you already have.',
      browse: 'Browse heroes',
      clearCart: 'Clear cart', confirmClearCart: 'Remove all skins from the cart?',
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
  $('nav-mine-label').textContent = T.mySkins;
  $('nav-heroes-label').textContent = T.heroesNav;
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
  const norm = (s) => (s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  const rkey = (r) => norm(r).replace(/[^a-z]/g, '') || 'default';
  const byRarity = (a, b) => (RARITY_ORDER.indexOf(rkey(a.rarity)) + 1 || 50) - (RARITY_ORDER.indexOf(rkey(b.rarity)) + 1 || 50) || a.name.localeCompare(b.name);

  const img = (src, alt, onFail) => {
    if (!src) return onFail();
    const i = h('img', { src, alt, loading: 'lazy', decoding: 'async' });
    i.onerror = () => i.replaceWith(onFail());
    return i;
  };

  // --- User lists: cart and owned ---
  // Telegram CloudStorage (values are limited to 4096 chars, so lists are chunked), localStorage outside Telegram.
  const cloud = inTelegram && tg.CloudStorage && tg.isVersionAtLeast?.('6.9') ? tg.CloudStorage : null;
  const withTimeout = (p, ms, fallback) => Promise.race([p, new Promise((r) => setTimeout(() => r(fallback), ms))]);
  const makeStore = (key) => ({
    async load() {
      if (!cloud) { try { return JSON.parse(localStorage.getItem(key) || '[]'); } catch { return []; } }
      const get = (keys) => new Promise((res) => cloud.getItems(keys, (err, v) => res(err ? {} : v || {})));
      const head = await withTimeout(get([`${key}_n`]), 4000, {});
      const n = Number(head[`${key}_n`] || 0);
      if (!n) return [];
      const parts = await withTimeout(get(Array.from({ length: n }, (_, i) => `${key}_${i}`)), 4000, {});
      const joined = Array.from({ length: n }, (_, i) => parts[`${key}_${i}`] || '').join('');
      return joined ? joined.split(',') : [];
    },
    async save(ids) {
      if (!cloud) { try { localStorage.setItem(key, JSON.stringify(ids)); } catch {} return; }
      const s = ids.join(',');
      const chunks = s ? s.match(/[\s\S]{1,4000}/g) : [];
      const set = (k, v) => new Promise((res) => cloud.setItem(k, v, () => res()));
      await Promise.all(chunks.map((c, i) => set(`${key}_${i}`, c)));
      await set(`${key}_n`, String(chunks.length));
    },
  });
  // "wish" is the original cart key, kept so existing carts are not lost
  const lists = {
    cart: { set: new Set(), store: makeStore(cloud ? 'wish' : 'wishlist'), timer: null },
    owned: { set: new Set(), store: makeStore(cloud ? 'own' : 'owned'), timer: null },
  };

  // --- State ---
  let data = { heroes: [], skins: [] };
  let heroesById = new Map();
  let skinsByHero = new Map();
  let skinsById = new Map();
  const ui = { role: '', query: '', tab: {}, rarity: {}, mine: 'cart' };

  const known = (name) => [...lists[name].set].filter((id) => skinsById.has(id));
  function updateCounts() { $('nav-mine-count').textContent = known('cart').length || ''; }

  function flush(name) { const l = lists[name]; clearTimeout(l.timer); l.timer = null; l.store.save([...l.set]); }
  function persist(name) {
    const l = lists[name];
    clearTimeout(l.timer);
    l.timer = setTimeout(() => flush(name), 150); // debounce: several quick clicks = one save
  }
  // save pending changes if the app is closed right after a click
  const flushPending = () => Object.keys(lists).forEach((n) => lists[n].timer && flush(n));
  window.addEventListener('pagehide', flushPending);
  document.addEventListener('visibilitychange', () => document.visibilityState === 'hidden' && flushPending());

  function setState(id, { cart, owned }) {
    if (owned !== undefined) {
      if (owned) { lists.owned.set.add(id); lists.cart.set.delete(id); } // an owned skin leaves the cart
      else lists.owned.set.delete(id);
      persist('owned'); persist('cart');
    }
    if (cart !== undefined) {
      if (cart) lists.cart.set.add(id); else lists.cart.set.delete(id);
      persist('cart');
    }
    tg?.HapticFeedback?.impactOccurred?.('light');
    updateCounts();
  }

  // --- Skin card (hero page and My skins) ---
  function skinCard(s, { showHero = false, onChange } = {}) {
    const card = h('article', { class: 'skin', 'data-rarity': rkey(s.rarity) });
    const draw = () => {
      const owned = lists.owned.set.has(s.id);
      const inCart = lists.cart.set.has(s.id);
      card.classList.toggle('is-owned', owned);
      const tags = [s.theme, s.source].filter(Boolean);
      const change = (patch) => { setState(s.id, patch); onChange ? onChange() : draw(); };

      const mainBtn = owned
        ? h('button', { class: 'btn in-cart', type: 'button', onclick: () => change({ owned: false }) }, `✓ ${T.haveIt}`)
        : h('button', { class: `btn${inCart ? ' in-cart' : ''}`, type: 'button', 'aria-pressed': String(inCart), onclick: () => change({ cart: !inCart }) },
            inCart ? `✓ ${T.inCart}` : T.add);
      // "Owned" toggle on the artwork, like a favorite button on a product photo
      const ownToggle = h('button', {
        class: `own-toggle${owned ? ' on' : ''}`, type: 'button', 'aria-pressed': String(owned),
        title: owned ? T.notHave : T.markOwned(s.name), 'aria-label': owned ? `${T.notHave}: ${s.name}` : T.markOwned(s.name),
        onclick: () => change({ owned: !owned }),
      }, owned ? `✓ ${T.haveIt}` : T.have);

      card.replaceChildren(
        h('div', { class: 'art' },
          img(s.image, s.name, () => h('span', {})),
          s.rarity ? h('span', { class: 'rarity' }, s.rarity) : null,
          ownToggle),
        h('div', { class: 'body' },
          showHero ? h('a', { class: 'skin-hero', href: `#/hero/${s.heroId}` }, heroesById.get(s.heroId)?.name || s.heroName) : null,
          h('h3', {}, s.name),
          tags.length ? h('div', { class: 'tags' }, tags.map((t) => h('span', { class: 'tag' }, t))) : null,
          h('div', { class: 'actions' }, mainBtn)));
    };
    draw();
    return card;
  }

  // --- Home: My skins (cart / owned) ---
  function renderMine() {
    const which = ui.mine;
    const items = known(which).map((id) => skinsById.get(id))
      .sort((a, b) => (heroesById.get(a.heroId)?.name || a.heroName).localeCompare(heroesById.get(b.heroId)?.name || b.heroName) || byRarity(a, b));

    const counts = {};
    items.forEach((s) => { counts[s.rarity || '?'] = (counts[s.rarity || '?'] || 0) + 1; });
    const tab = (key, label) => h('button', {
      class: 'chip', type: 'button', role: 'tab', 'aria-selected': String(which === key), 'aria-pressed': String(which === key),
      onclick: () => { ui.mine = key; renderMine(); },
    }, label, h('span', { class: 'chip-count' }, String(known(key).length)));

    const clearCart = () => {
      const doIt = () => { lists.cart.set.clear(); persist('cart'); updateCounts(); renderMine(); };
      if (inTelegram && tg.showConfirm) tg.showConfirm(T.confirmClearCart, (ok) => ok && doIt());
      else if (confirm(T.confirmClearCart)) doIt();
    };

    view.replaceChildren(
      h('h1', { class: 'page-title' }, T.mySkins),
      h('div', { class: 'chips tabs', role: 'tablist' }, tab('cart', T.cart), tab('owned', T.owned)),
      ...(items.length
        ? [
            h('p', { class: 'summary' },
              Object.entries(counts).sort((a, b) => RARITY_ORDER.indexOf(rkey(a[0])) - RARITY_ORDER.indexOf(rkey(b[0])))
                .map(([r, n]) => h('span', { class: 'sum-item', 'data-rarity': rkey(r) }, `${r}: ${n}`)),
              which === 'cart' ? h('button', { class: 'link', type: 'button', onclick: clearCart }, T.clearCart) : null),
            h('section', { class: 'skins' }, items.map((s) => skinCard(s, { showHero: true, onChange: renderMine }))),
          ]
        : [h('div', { class: 'status' },
            h('p', {}, which === 'cart' ? T.emptyCart : T.emptyOwned),
            h('a', { class: 'btn ghost', href: '#/heroes' }, T.browse))]));
  }

  // --- Heroes ---
  function heroCard(hero) {
    const all = (skinsByHero.get(hero.id) || []).filter((s) => !s.isDefault);
    const owned = all.filter((s) => lists.owned.set.has(s.id)).length;
    return h('a', { class: 'hero-card', href: `#/hero/${hero.id}`, style: { '--hero': hero.color || '' } },
      img(hero.image, '', () => h('span', { class: 'ph' }, hero.name[0])),
      h('div', { class: 'meta' },
        h('p', { class: 'hero-name' }, hero.name),
        h('div', { class: 'hero-sub' },
          hero.role ? h('span', {}, T.roles[hero.role] || hero.role) : null,
          h('span', {}, owned ? T.ownedOf(owned, all.length) : T.skinsCount(all.length)))));
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
    const sub = h('p', {});
    const updateSub = () => {
      const owned = all.filter((s) => lists.owned.set.has(s.id)).length;
      sub.textContent = [hero.role ? (T.roles[hero.role] || hero.role) : null, T.skinsCount(all.length), owned ? T.ownedOf(owned, all.length) : null].filter(Boolean).join(', ');
    };

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
      grid.replaceChildren(...list.map((s) => skinCard(s, { onChange: () => { updateSub(); fill(); } })));
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

    updateSub();
    view.replaceChildren(
      h('header', { class: `banner${inTelegram ? '' : ' has-back'}`, style: { '--hero': hero.color || '' } },
        inTelegram ? null : h('button', { class: 'back', type: 'button', onclick: () => history.back() }, `‹ ${T.back}`),
        h('div', {}, h('h1', {}, hero.name), sub),
        img(hero.image, '', () => h('span', {}))),
      h('div', { class: 'tools' }, tabs, rarityChips),
      grid, empty);
    fill();
    window.scrollTo(0, 0);
  }

  // --- Routing: #/ (my skins), #/heroes, #/hero/<id> ---
  let routing = false;
  function route() {
    let hash = location.hash.replace(/^#/, '') || '/';
    if (hash === '/cart') { ui.mine = 'cart'; history.replaceState(null, '', '#/'); hash = '/'; } // old cart URL
    const m = hash.match(/^\/hero\/([^/]+)$/);
    const section = hash === '/' ? 'mine' : 'heroes';
    document.querySelectorAll('.nav a').forEach((a) => a.toggleAttribute('aria-current', a.dataset.section === section));
    if (m) renderHero(decodeURIComponent(m[1]));
    else if (hash === '/heroes') renderHeroes();
    else { renderMine(); window.scrollTo(0, 0); }
    if (inTelegram) (m ? tg.BackButton.show() : tg.BackButton.hide());
  }
  if (inTelegram) tg.BackButton.onClick(() => (history.length > 1 ? history.back() : (location.hash = '#/heroes')));

  async function init() {
    view.replaceChildren(h('p', { class: 'status' }, T.loading));
    try {
      const [res, cartIds, ownedIds] = await Promise.all([fetch('api/catalog'), lists.cart.store.load(), lists.owned.store.load()]);
      if (!res.ok) throw new Error(res.status);
      data = await res.json();
      heroesById = new Map(data.heroes.map((x) => [x.id, x]));
      skinsById = new Map(data.skins.map((s) => [s.id, s]));
      skinsByHero = new Map();
      for (const s of data.skins) { if (!skinsByHero.has(s.heroId)) skinsByHero.set(s.heroId, []); skinsByHero.get(s.heroId).push(s); }
      lists.cart.set = new Set(cartIds);
      lists.owned.set = new Set(ownedIds);
      updateCounts();
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
