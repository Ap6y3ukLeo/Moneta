'use strict';

/* ------------------------------------------------------------------ utils */
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const PALETTE = ['#14d1a3', '#3d7bff', '#ffd54f', '#8b5cf6', '#ff7a59', '#1c284a', '#2dc7d9', '#a3e635'];
const YEAR = 365.25 * 864e5;
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const icon = (name, cls = '') => `<svg class="ic ${cls}"><use href="#i-${name}"/></svg>`;
const nf = (d, min = 0) => new Intl.NumberFormat('ru-RU', { minimumFractionDigits: min, maximumFractionDigits: d });

function num(v, d = 2) {
  if (v == null || !isFinite(v)) return '—';
  return nf(d).format(v);
}
function money(v, d) {
  if (v == null || !isFinite(v)) return '—';
  const abs = Math.abs(v);
  const digits = d ?? (abs >= 1000 ? 0 : 2);
  return (v < 0 ? '−' : '') + nf(digits, digits).format(abs) + ' ₽';
}
function price(v) {
  if (v == null || !isFinite(v)) return '—';
  const a = Math.abs(v);
  const d = a >= 10 ? 2 : a >= 1 ? 3 : a >= 0.01 ? 4 : 6;
  return nf(d).format(v);
}
function pct(v) {
  if (v == null || !isFinite(v)) return '—';
  return (v > 0 ? '+' : '') + nf(2).format(v) + '%';
}
function chg(v) {
  if (v == null || !isFinite(v)) return '<span class="muted">—</span>';
  return `<span class="${v >= 0 ? 'up' : 'down'}">${pct(v)}</span>`;
}
function parseNum(v) {
  if (typeof v === 'number') return v;
  const cleaned = String(v ?? '').replace(/\s|₽|%/g, '').replace(',', '.');
  if (!cleaned) return NaN;
  const n = Number(cleaned);
  return isFinite(n) ? n : NaN;
}
function parseDate(s) {
  if (!s) return new Date();
  const [y, m, d] = String(s).slice(0, 10).split('-').map(Number);
  return y && m && d ? new Date(y, m - 1, d) : new Date(s);
}
function isoDate(d = new Date()) {
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
function addMonths(date, months) {
  const d = new Date(date);
  const day = d.getDate();
  d.setMonth(d.getMonth() + months);
  if (d.getDate() < day) d.setDate(0);
  return d;
}
function timeOf(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (!isFinite(d)) return '—';
  const time = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  const now = new Date();
  return d.toDateString() === now.toDateString()
    ? time
    : `${d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })}, ${time}`;
}
function daysBetween(a, b) { return Math.max(0, (b - a) / 864e5); }
function uid() {
  return 'p' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
}
function qtyText(v) {
  return nf(6).format(v).replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '');
}
function toast(msg, isErr = false) {
  const el = $('#toast');
  el.textContent = msg;
  el.className = 'toast show' + (isErr ? ' toast--err' : '');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.className = 'toast'; }, 3200);
}
function sparkline(values, color, w = 120, h = 44) {
  const arr = (values || []).filter((v) => isFinite(v));
  if (arr.length < 2) return `<svg class="spark" viewBox="0 0 ${w} ${h}" aria-hidden="true"></svg>`;
  const min = Math.min(...arr);
  const max = Math.max(...arr);
  const span = max - min || 1;
  const pts = arr.map((v, i) => [(i / (arr.length - 1)) * w, h - 3 - ((v - min) / span) * (h - 8)]);
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">
    <path class="area" d="${d} L ${w} ${h} L 0 ${h} Z" fill="${color}"/>
    <path d="${d}" stroke="${color}" vector-effect="non-scaling-stroke"/>
  </svg>`;
}
const coin = (txt, cls = '') => `<span class="coin ${cls}">${esc(String(txt).slice(0, 4))}</span>`;
const cryptoIcon = (c) => {
  const symbol = String(c?.symbol || '').toLowerCase();
  return `<span class="coin coin--logo">${esc(String(c?.symbol || '?').slice(0, 4))}${symbol ? `<img src="https://cdn.jsdelivr.net/npm/cryptocurrency-icons@0.18.1/32/color/${encodeURIComponent(symbol)}.png" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : ''}</span>`;
};
const metalIcon = (code) => coin(code === 'XAU' ? 'Au' : code === 'XAG' ? 'Ag' : code === 'XPT' ? 'Pt' : 'Pd',
  code === 'XAU' ? 'coin--gold' : code === 'XAG' ? 'coin--silver' : 'coin--platinum');
const ext = (url, label = '', cls = 'icon-btn') => url
  ? `<a class="${cls}" href="${esc(url)}" target="_blank" rel="noopener" title="${esc(label || 'Открыть источник')}" aria-label="${esc(label || 'Открыть источник')}">${icon('ext')}</a>`
  : '';

/* ------------------------------------------------------------------ state */
const PROFILE_KEY = 'monetka:profiles:v1';
const PORTFOLIO_PREFIX = 'monetka:portfolio:v2:';
const LEGACY_PORTFOLIO_KEY = 'monetka:portfolio:v2';
const S = {
  market: null,
  deposits: null,
  realty: null,
  errors: {},
  loading: true,
  refreshing: false,
  profiles: loadProfiles(),
  portfolio: [],
  addKind: 'crypto',
  addPreset: {},
  dep: { amount: 500000, months: 12, limit: 40 },
  re: { q: '', rooms: 'all', source: 'all', city: 'all', sort: 'price', limit: 24 },
  calc: null,
};
S.portfolio = loadPortfolio(S.profiles.active);

function readLegacyPortfolio() {
  try {
    const raw = JSON.parse(localStorage.getItem(LEGACY_PORTFOLIO_KEY) || '[]');
    return Array.isArray(raw) ? raw.filter((p) => p && p.kind) : [];
  } catch { return []; }
}
function loadProfiles() {
  try {
    const raw = JSON.parse(localStorage.getItem(PROFILE_KEY) || 'null');
    if (raw && Array.isArray(raw.items) && raw.items.length) {
      const items = raw.items
        .filter((p) => p && p.id)
        .map((p) => ({ id: String(p.id), name: String(p.name || 'Профиль').slice(0, 24) }));
      if (items.length) {
        const active = items.some((p) => p.id === raw.active) ? raw.active : items[0].id;
        return { items, active };
      }
    }
  } catch { /* localStorage может быть недоступен */ }
  const id = 'u' + Date.now().toString(36);
  const legacy = readLegacyPortfolio();
  localStorage.setItem(PROFILE_KEY, JSON.stringify({ items: [{ id, name: 'Алексей' }], active: id }));
  if (legacy.length) localStorage.setItem(PORTFOLIO_PREFIX + id, JSON.stringify(legacy));
  return { items: [{ id, name: 'Алексей' }], active: id };
}
function activeProfile() {
  return S.profiles.items.find((p) => p.id === S.profiles.active) || S.profiles.items[0];
}
function loadPortfolio(profileId) {
  try {
    const raw = JSON.parse(localStorage.getItem(PORTFOLIO_PREFIX + profileId) || '[]');
    return Array.isArray(raw) ? raw.filter((p) => p && p.kind) : [];
  } catch { return []; }
}
function savePortfolio() {
  try { localStorage.setItem(PORTFOLIO_PREFIX + S.profiles.active, JSON.stringify(S.portfolio)); } catch { /* ignore */ }
}
function saveProfiles() {
  try { localStorage.setItem(PROFILE_KEY, JSON.stringify(S.profiles)); } catch { /* ignore */ }
}
function usdRate() {
  return (S.market?.fx?.items || []).find((i) => i.code === 'USD')?.value || 0;
}
function rub(usd) {
  const r = usdRate();
  return r ? usd * r : 0;
}
const cryptoList = () => S.market?.crypto?.items || [];
const metalList = () => S.market?.metals?.items || [];
const fxList = () => S.market?.fx?.items || [];
const depositList = () => S.deposits?.items || [];
const realtyList = () => S.realty?.items || [];
function bestDeposit(amount = S.dep.amount) {
  return [...depositList()]
    .filter((d) => (!d.currency || d.currency === 'RUB') && (!d.min || d.min <= amount) && (!d.max || d.max >= amount))
    .sort((a, b) => (b.rate || 0) - (a.rate || 0))[0] || null;
}
const findCrypto = (id) => cryptoList().find((c) => c.id === id);
const findMetal = (id) => metalList().find((m) => m.id === id);
const findFx = (code) => fxList().find((f) => f.code === code);
const keyRateValue = () => S.market?.keyRate?.value ?? S.deposits?.keyRate?.value ?? 0;

/* ------------------------------------------------------------------ data */
async function fetchJson(url, timeout = 30000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const res = await fetch(url, { headers: { Accept: 'application/json' }, cache: 'no-store', signal: controller.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}
async function refresh({ silent = false, marketOnly = false } = {}) {
  if (S.refreshing) return;
  S.refreshing = true;
  document.body.classList.add('is-refreshing');
  const jobs = [['market', '/api/market?force=1', 'рыночные котировки', 30000]];
  if (!marketOnly) {
    jobs.push(
      ['deposits', '/api/deposits', 'вклады банков', 35000],
      ['realty', '/api/realty', 'недвижимость', 45000],
    );
  }
  const results = await Promise.all(jobs.map(async ([key, url, label, timeout]) => {
    try {
      S[key] = await fetchJson(url, timeout);
      delete S.errors[key];
      if (key === 'market') S.loading = false;
      const typing = ['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName)
        && document.activeElement.closest('#view');
      if (!typing) render();
      updateSideStatus();
      return true;
    } catch (err) {
      S.errors[key] = label;
      if (key === 'market') S.loading = false;
      const typing = ['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName)
        && document.activeElement.closest('#view');
      if (!typing) render();
      updateSideStatus();
      return false;
    }
  }));
  S.loading = false;
  S.refreshing = false;
  document.body.classList.remove('is-refreshing');
  render();
  updateSideStatus();
  if (!silent) {
    if (results.every((ok) => !ok)) toast('Нет связи с источниками данных', true);
    else toast(`Данные обновлены в ${new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}`);
  }
}

/* ------------------------------------------------------------------ money math */
function depositCalc(p, at = new Date()) {
  const start = parseDate(p.date);
  const months = Math.max(1, Number(p.months) || 12);
  const end = addMonths(start, months);
  const keyRate = keyRateValue();
  const stop = at < end ? at : end;
  const years = Math.max(0, daysBetween(start, stop) / 365);
  const termYears = months / 12;
  const r = (Number(p.rate) || 0) / 100;
  const n = p.cap === 'month' ? 12 : p.cap === 'quarter' ? 4 : 0;
  const grossAt = (y) => (n ? p.amount * (Math.pow(1 + r / n, n * y) - 1) : p.amount * r * y);
  const gross = grossAt(years);
  const fullGross = grossAt(termYears);
  const tax = Math.max(0, fullGross - 1e6 * (keyRate / 100)) * 0.13;
  return {
    value: p.amount + gross,
    gross,
    fullGross,
    tax,
    net: p.amount + fullGross - tax,
    end,
    termYears,
    years,
    matured: at >= end,
  };
}

function valuation() {
  const now = new Date();
  const depRate = keyRateValue();
  const rows = (S.portfolio || []).map((p) => {
    let cur = 0;
    let prev = 0;
    let cost = 0;
    let name = p.name || 'Актив';
    let sub = '';
    let url = '';
    let metalCls = '';

    if (p.kind === 'crypto') {
      const c = findCrypto(p.assetId);
      name = c?.name || p.name || p.assetId;
      const px = c ? rub(c.price) : 0;
      cur = px ? p.qty * px : p.qty * p.buy;
      const d = c?.change24h || 0;
      prev = d !== -100 ? cur / (1 + d / 100) : cur;
      cost = p.qty * p.buy;
      sub = `${qtyText(p.qty)} ${esc(c?.symbol || '')} · покупка ${money(p.buy)}`;
      url = c?.tradeUrl || '';
    } else if (p.kind === 'metal') {
      const m = findMetal(p.assetId);
      name = m?.name || p.name || p.assetId;
      const px = m?.price || 0;
      cur = px ? p.qty * px : p.qty * p.buy;
      const d = m?.change24h || 0;
      prev = d !== -100 ? cur / (1 + d / 100) : cur;
      cost = p.qty * p.buy;
      sub = `${qtyText(p.qty)} г · покупка ${money(p.buy)}/г`;
      url = 'https://www.cbr.ru/hd_base/metall/';
      metalCls = p.assetId === 'XAU' ? 'coin--gold' : p.assetId === 'XAG' ? 'coin--silver' : 'coin--platinum';
    } else if (p.kind === 'fx') {
      const f = findFx(p.assetId);
      name = f?.name || p.name || p.assetId;
      const px = f?.value || 0;
      cur = px ? p.qty * px : p.qty * p.buy;
      const d = f?.change24h || 0;
      prev = d !== -100 ? cur / (1 + d / 100) : cur;
      cost = p.qty * p.buy;
      sub = `${qtyText(p.qty)} ${p.assetId} · покупка ${money(p.buy)}`;
      url = 'https://www.cbr.ru/currency_base/daily/';
      metalCls = 'coin--silver';
    } else {
      const d = depositCalc(p, now);
      name = p.name || 'Вклад';
      cur = d.value;
      prev = cur;
      cost = p.amount;
      sub = `${esc(p.bank || 'Банк')} · ${num(p.rate, 2)}% · ${p.months} мес · ${d.matured ? 'закрыт' : 'до ' + d.end.toLocaleDateString('ru-RU')}`;
      url = p.url || '';
      metalCls = 'coin--gold';
    }

    const pnl = cur - cost;
    return {
      p,
      name,
      sub,
      url,
      metalCls,
      cur,
      prev,
      cost,
      pnl,
      pnlPct: cost ? (pnl / cost) * 100 : 0,
      kindLabel: p.kind === 'crypto' ? 'Криптовалюта' : p.kind === 'metal' ? 'Драгметалл' : p.kind === 'fx' ? 'Валюта' : 'Вклад',
      iconText: p.kind === 'crypto' ? (findCrypto(p.assetId)?.symbol || 'C') : p.kind === 'metal' || p.kind === 'fx' ? p.assetId : '₽',
    };
  }).sort((a, b) => b.cur - a.cur);

  const value = rows.reduce((s, r) => s + r.cur, 0);
  const invested = rows.reduce((s, r) => s + r.cost, 0);
  const prevValue = rows.reduce((s, r) => s + r.prev, 0);
  const pnl = value - invested;
  const flows = [];
  rows.forEach((r) => {
    if (r.cost > 0) flows.push({ t: parseDate(r.p.date).getTime(), a: -r.cost });
  });
  if (value > 0) flows.push({ t: Date.now(), a: value });
  const irr = rows.length ? xirr(flows) : null;

  return {
    rows,
    value,
    invested,
    pnl,
    pnlPct: invested ? (pnl / invested) * 100 : 0,
    changeDay: value - prevValue,
    changePct: prevValue ? ((value - prevValue) / prevValue) * 100 : 0,
    irr,
    depositIncome: rows.filter((r) => r.p.kind === 'deposit').reduce((s, r) => s + depositCalc(r.p).gross, 0),
  };
}

function xirr(flows) {
  if (!flows || flows.length < 2) return null;
  const t0 = Math.min(...flows.map((f) => f.t));
  const f = (r) => flows.reduce((s, x) => s + x.a / Math.pow(1 + r, (x.t - t0) / YEAR), 0);
  let lo = -0.9999;
  let hi = 10;
  let flo = f(lo);
  let fhi = f(hi);
  if (!isFinite(flo) || !isFinite(fhi) || flo * fhi > 0) return null;
  for (let i = 0; i < 90; i++) {
    const mid = (lo + hi) / 2;
    const fm = f(mid);
    if (Math.abs(fm) < 1e-7) return mid;
    if (flo * fm <= 0) { hi = mid; fhi = fm; } else { lo = mid; flo = fm; }
  }
  return (lo + hi) / 2;
}

/* ------------------------------------------------------------------ templates: shared */
function sourceWarning() {
  const bad = [];
  const m = S.market;
  if (m) {
    if (m.crypto?.meta?.ok === false) bad.push('криптовалюта');
    if (m.metals?.meta?.ok === false) bad.push('драгметаллы');
    if (m.fx?.meta?.ok === false) bad.push('курсы валют');
  }
  if (S.deposits?.meta?.ok === false) bad.push('вклады');
  if (S.realty?.meta?.ok === false) bad.push('недвижимость');
  if (!bad.length) return '';
  return `<div class="alert">${icon('shield')}<div><strong>Не удалось обновить: ${bad.join(', ')}.</strong> Показаны последние сохранённые данные из кэша. <a href="#" class="link-more" data-action="refresh">Повторить</a></div></div>`;
}
function loadingView() {
  if (!S.loading) {
    return `<div class="empty-state">
      <h3>Не удалось загрузить данные</h3>
      <p>Проверьте интернет-соединение и попробуйте снова. Курсы ЦБ РФ и Bybit доступны без ключей; вклады и недвижимость парсятся с сайтов банков и площадок объявлений.</p>
      <button class="btn" data-action="refresh">Повторить</button>
    </div>`;
  }
  return `<div class="empty-state"><span class="loader"></span><p>Загружаем котировки, вклады и недвижимость…</p></div>`;
}
function sourcePill(label, meta) {
  const cls = meta?.ok === false ? 'pill--warn' : 'pill--mint';
  return `<span class="pill ${cls}"><span class="dot"></span>${esc(label)} · ${timeOf(meta?.updated)}</span>`;
}
function trendList() {
  const items = [];
  cryptoList().slice(0, 8).forEach((c) => items.push({
    name: c.name, icon: cryptoIcon(c), chg: c.change24h, value: money(rub(c.price)), href: '#/crypto',
  }));
  metalList().forEach((m) => items.push({
    name: m.name, icon: metalIcon(m.code), chg: m.change24h, value: money(m.price) + '/г', href: '#/metals',
  }));
  const fx = S.market?.fx?.items || [];
  ['USD', 'EUR', 'CNY'].forEach((code) => {
    const f = fx.find((i) => i.code === code);
    if (f) items.push({ name: code, icon: coin(code, 'coin--silver'), chg: f.change24h, value: num(f.value, 2) + ' ₽', href: '#/fx' });
  });
  return items
    .filter((i) => isFinite(i.chg))
    .sort((a, b) => Math.abs(b.chg) - Math.abs(a.chg))
    .slice(0, 5);
}

/* ------------------------------------------------------------------ pages: home */
function homePage() {
  if (!S.market) return loadingView();
  const { crypto, metals, fx } = S.market;
  const usd = fx.items.find((i) => i.code === 'USD');
  const eur = fx.items.find((i) => i.code === 'EUR');
  const cny = fx.items.find((i) => i.code === 'CNY');
  const btc = crypto.items[0];
  const xau = metals.items.find((m) => m.code === 'XAU');
  const xag = metals.items.find((m) => m.code === 'XAG');
  const xpt = metals.items.find((m) => m.code === 'XPT');
  const topDep = bestDeposit();
  const msk = S.realty?.stats?.moscow;
  const russia = S.realty?.stats?.russia;
  const v = valuation();
  const insights = [];

  if (topDep) insights.push(`Лучший вклад: <b>${esc(topDep.bank)}</b> — <b>${num(topDep.rate, 2)}%</b>${topDep.termDays ? ` на ${topDep.termDays} дн.` : ''}, от ${money(topDep.min)}.`);
  if (xau) insights.push(`Золото ${xau.change24h >= 0 ? 'выросло' : 'снизилось'} на <b>${num(Math.abs(xau.change24h), 2)}%</b> за день — <b>${money(xau.price)}</b>/г.`);
  const bestCrypto = [...crypto.items].sort((a, b) => (b.change24h || 0) - (a.change24h || 0))[0];
  if (bestCrypto) insights.push(`Лидер суток в крипте — <b>${esc(bestCrypto.name)}</b>: ${chg(bestCrypto.change24h)}.`);

  return `
  ${sourceWarning()}
  <section class="hero">
    <div class="hero-copy">
      <span class="eyebrow">Добро пожаловать, ${esc(activeProfile().name)}!</span>
      <h1>Умные решения<br>для твоего капитала</h1>
      <p>Аналитика по всем ключевым рынкам в одном месте. Выбирай, что важно именно тебе.</p>
      <div class="hero-actions">
        <a class="btn" href="#/portfolio">Перейти к анализу ${icon('arrow')}</a>
        <a class="btn btn--ghost" href="#/deposits">Вклады</a>
      </div>
      <div class="hero-source">${icon('shield')} ЦБ РФ · Bybit · банки и недвижимость — обновлено ${timeOf(fx.meta?.updated || crypto.meta?.updated)}</div>
    </div>
    <div class="hero-art" aria-hidden="true">${heroArt()}</div>
  </section>

  <div class="chips">
    <a class="chip is-active" href="#/">Все рынки</a>
    <a class="chip" href="#/deposits">${icon('bank')} Вклады</a>
    <a class="chip" href="#/crypto">${icon('crypto')} Криптовалюта</a>
    <a class="chip" href="#/metals">${icon('gold')} Драгметаллы</a>
    <a class="chip" href="#/fx">${icon('fx')} Валюта</a>
    <a class="chip" href="#/realty">${icon('building')} Недвижимость</a>
    <a class="chip" href="#/portfolio">${icon('wallet')} Портфель</a>
  </div>

  <div class="home-layout">
    <div class="home-main">
      <div class="cards">
        <article class="card card--click" data-go="#/deposits" tabindex="0" role="link">
          <div class="card-head">
            <div><h3>Банковские продукты</h3><div class="sub">${depositList().length} предложений · ${new Set(depositList().map((d) => d.bank)).size} банков</div></div>
            <span class="badge">Лучшие предложения</span>
          </div>
          <div class="metric-big">до ${topDep ? num(topDep.rate, 2) + '%' : '—'}</div>
          <div class="muted" style="font-size:11.5px">по вкладам в рублях</div>
          <div class="mini-rows">
            ${depositList().slice(0, 2).map((d) => `<div class="mini-row">${coin(d.bank[0])}<span class="name">${esc(d.bank)} · ${esc(d.name)}</span><span class="price">${num(d.rate, 2)}%</span></div>`).join('') || '<div class="muted">Нет данных</div>'}
          </div>
          <div class="card-foot"><a class="link-more" href="#/deposits">Смотреть все ${icon('arrow')}</a><a class="chev-link" href="#/deposits">${icon('chev')}</a></div>
        </article>

        <article class="card card--click" data-go="#/crypto" tabindex="0" role="link">
          <div class="card-head">
            <div><h3>Криптовалюта</h3><div class="sub">Топ активы · Bybit</div></div>
            <span class="badge">24 часа</span>
          </div>
          ${btc ? `<div style="display:flex;align-items:baseline;gap:8px">
              <div class="metric-big">${money(rub(btc.price))}</div>
              ${chg(btc.change24h)}
            </div>
            <div class="muted" style="font-size:11px">BTC · $${price(btc.price)}</div>
            <div class="spark-wrap">${sparkline(btc.spark, btc.change24h >= 0 ? '#0fa97d' : '#e8564b', 220, 48)}</div>` : '<div class="muted">Нет данных</div>'}
          <div class="card-foot"><a class="link-more" href="#/crypto">Подробнее ${icon('arrow')}</a>${btc?.tradeUrl ? `<a class="link-more" href="${esc(btc.tradeUrl)}" target="_blank" rel="noopener">Купить BTC ${icon('ext')}</a>` : ''}</div>
        </article>

        <article class="card card--click" data-go="#/fx" tabindex="0" role="link">
          <div class="card-head">
            <div><h3>Валюта</h3><div class="sub">Курсы ЦБ РФ</div></div>
            <span class="badge badge--blue">${esc(fx.date || '')}</span>
          </div>
          <div class="mini-rows">
            ${[['USD', usd, '$'], ['EUR', eur, '€'], ['CNY', cny, '¥']].map(([code, f, sym]) => f ? `<div class="mini-row">
                ${coin(sym, 'coin--silver')}<span class="name">${code}</span>
                <span class="price">${num(f.value, 2)} ₽</span><span class="chg">${chg(f.change24h)}</span>
              </div>` : '').join('')}
          </div>
          <div class="card-foot"><a class="link-more" href="#/fx">Все курсы ${icon('arrow')}</a><a class="chev-link" href="#/fx">${icon('chev')}</a></div>
        </article>

        <article class="card card--click" data-go="#/metals" tabindex="0" role="link">
          <div class="card-head">
            <div><h3>Драгметаллы</h3><div class="sub">ЦБ РФ, ₽ за грамм</div></div>
            <span class="badge badge--gold">Стабильность</span>
          </div>
          <div class="mini-rows">
            ${[[xau, 'Au'], [xag, 'Ag'], [xpt, 'Pt']].map(([m]) => m ? `<div class="mini-row">
                ${metalIcon(m.code)}<span class="name">${esc(m.name)}</span>
                <span class="price">${money(m.price)}</span><span class="chg">${chg(m.change24h)}</span>
              </div>` : '').join('')}
          </div>
          <div class="spark-wrap">${xau ? sparkline(xau.spark, xau.change24h >= 0 ? '#0fa97d' : '#e8564b', 220, 42) : ''}</div>
          <div class="card-foot"><a class="link-more" href="#/metals">Подробнее ${icon('arrow')}</a><a class="chev-link" href="#/metals">${icon('chev')}</a></div>
        </article>

        <article class="card card--click" data-go="#/portfolio" tabindex="0" role="link">
          <div class="card-head">
            <div><h3>Мой портфель</h3><div class="sub">${v.rows.length ? `${v.rows.length} позиции` : 'Пока пусто'}</div></div>
            <span class="badge ${v.pnl >= 0 ? '' : 'badge--gray'}">${v.rows.length ? chg(v.pnlPct) : 'Старт'}</span>
          </div>
          ${v.rows.length ? `
            <div class="metric-big">${money(v.value)}</div>
            <div class="muted" style="font-size:11.5px">вложено ${money(v.invested)} · ${chg(v.changePct)} за сутки</div>
            <div style="display:flex;height:8px;border-radius:99px;overflow:hidden;margin:12px 0 8px;background:#eef4f3">
              ${v.rows.slice(0, 5).map((r, i) => `<span style="width:${(r.cur / (v.value || 1)) * 100}%;background:${PALETTE[i % PALETTE.length]}"></span>`).join('')}
            </div>
            <div class="mini-rows">${v.rows.slice(0, 2).map((r) => `<div class="mini-row"><span class="name">${esc(r.name)}</span><span class="price">${money(r.cur)}</span><span class="chg">${chg(r.pnlPct)}</span></div>`).join('')}</div>
          ` : `
            <p class="muted" style="font-size:12px;margin:6px 0 12px">Добавьте криптовалюту, металл или вклад — сервис посчитает стоимость, прибыль и доходность.</p>
            <button class="btn btn--sm" data-action="open-add">Собрать портфель</button>
          `}
          <div class="card-foot"><a class="link-more" href="#/portfolio">Открыть портфель ${icon('arrow')}</a></div>
        </article>

        <article class="card card--click" data-go="#/realty" tabindex="0" role="link">
          <div class="card-head">
            <div><h3>Недвижимость</h3><div class="sub">Вся Россия · Яндекс, Авито, Циан, БН.ру</div></div>
            <span class="badge badge--blue">${realtyList().length ? realtyList().length + ' объявл.' : 'Рынок'}</span>
          </div>
          ${msk ? `<div class="metric-big" style="font-size:23px">${money(msk.avgM2)}<span class="muted" style="font-size:12px;font-weight:500">/м²</span></div>
            <div class="muted" style="font-size:11.5px">Москва · средняя квартира ${money(msk.avgPrice)}</div>` : '<p class="muted" style="font-size:12px">Загружаем средние цены…</p>'}
          <div class="mini-rows" style="margin-top:12px">
            ${russia ? `<div class="mini-row">${icon('building')}<span class="name">Россия · медиана</span><span class="price">${money(russia.median)}</span></div>` : ''}
            ${russia?.avgM2 ? `<div class="mini-row"><span class="name">Россия · цена м²</span><span class="price">${money(russia.avgM2)}</span></div>` : ''}
          </div>
          <div class="card-foot"><a class="link-more" href="#/realty">Смотреть объявления ${icon('arrow')}</a><a class="chev-link" href="#/realty">${icon('chev')}</a></div>
        </article>
      </div>

      <div class="banner">
        <div><h3>Вместе к финансовой свободе</h3><p>Монетка — ваш надёжный помощник в мире инвестиций и финансов.</p></div>
        <a class="btn btn--ghost" href="#/portfolio">Начать анализ ${icon('arrow')}</a>
      </div>
    </div>

    <aside class="rail">
      <div class="card">
        <div class="ai-head"><div class="ai-title">${icon('spark')} Монета AI</div></div>
        <p class="ai-greet">Коротко о рынке на основе живых данных:</p>
        <div class="ai-list">${insights.map((t) => `<div class="ai-item">${icon('shield')}<span>${t}</span></div>`).join('')}</div>
        <button class="btn btn--sm ai-open-btn" type="button" data-action="ai-open">${icon('spark')} Открыть чат</button>
        <div class="ai-chips"><a href="#/deposits">Вклады</a><a href="#/crypto">Крипта</a><a href="#/metals">Металлы</a><a href="#/fx">Валюты</a></div>
      </div>

      <div class="card">
        <div class="rail-title"><h3>Сейчас в тренде</h3><span class="muted" style="font-size:10px">24ч</span></div>
        <div class="trend">
          ${trendList().map((t, i) => `<a class="trend-row" href="${t.href}">
            <span class="rank">${i + 1}</span>${t.icon}
            <span class="name">${esc(t.name)}<br><small class="muted">${t.value}</small></span>
            <span class="chg ${t.chg >= 0 ? 'up' : 'down'}">${pct(t.chg)}</span>
          </a>`).join('')}
        </div>
      </div>

      <div class="card">
        <div class="rail-title"><h3>Данные</h3><button class="icon-btn" style="width:32px;height:32px;border-radius:9px" data-action="refresh" title="Обновить">${icon('refresh')}</button></div>
        <div class="data-status" style="margin-top:10px">
          ${dataStatusLine('Криптовалюта', crypto.meta)}
          ${dataStatusLine('Драгметаллы', metals.meta)}
          ${dataStatusLine('Курсы валют', fx.meta)}
          ${dataStatusLine(`Вклады · ${new Set((S.deposits?.items || []).map((d) => d.bank)).size} банков`, S.deposits?.meta)}
          ${dataStatusLine('Недвижимость', S.realty?.meta)}
        </div>
      </div>
    </aside>
  </div>`;
}

function dataStatusLine(label, meta) {
  const ok = meta?.ok !== false;
  return `<div><span>${label}</span><span class="${ok ? 'ok' : 'warn'}">${ok ? 'онлайн' : 'кэш'} · ${timeOf(meta?.updated)}</span></div>`;
}

function heroArt() {
  return `<svg viewBox="0 0 520 300" fill="none" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="chart" x1="0" y1="1" x2="1" y2="0"><stop stop-color="#14d1a3" stop-opacity=".05"/><stop offset="1" stop-color="#14d1a3" stop-opacity=".32"/></linearGradient>
      <linearGradient id="arrow" x1="0" y1="1" x2="1" y2="0"><stop stop-color="#0fb98f"/><stop offset="1" stop-color="#2fe3b5"/></linearGradient>
      <linearGradient id="gold" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#ffe38a"/><stop offset="1" stop-color="#f2b21f"/></linearGradient>
    </defs>
    <circle cx="424" cy="64" r="52" fill="#fff" opacity=".55"/>
    <circle cx="424" cy="64" r="34" fill="url(#arrow)"/>
    <text x="424" y="74" text-anchor="middle" font-family="Inter, Segoe UI, sans-serif" font-size="26" font-weight="700" fill="#fff">₿</text>
    <circle cx="366" cy="118" r="24" fill="#fff" opacity=".85"/>
    <text x="366" y="126" text-anchor="middle" font-family="Inter, Segoe UI, sans-serif" font-size="18" font-weight="700" fill="#3d7bff">%</text>
    <g transform="rotate(-7 250 170)">
      <rect x="118" y="72" width="262" height="184" rx="22" fill="#fff" opacity=".55" stroke="#fff"/>
      <rect x="118" y="72" width="262" height="184" rx="22" fill="url(#chart)" opacity=".55"/>
      <path d="M146 206c22-6 29-36 50-38s25 22 46 8 26-48 50-52 30 20 56 6" stroke="#0fb98f" stroke-width="3" stroke-linecap="round"/>
      <path d="M146 206c22-6 29-36 50-38s25 22 46 8 26-48 50-52 30 20 56 6" stroke="url(#arrow)" stroke-width="3" stroke-linecap="round"/>
      <path d="M326 108l24 4-6 23" stroke="#0fb98f" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
      <rect x="142" y="92" width="64" height="8" rx="4" fill="#fff" opacity=".9"/>
      <rect x="142" y="106" width="40" height="6" rx="3" fill="#fff" opacity=".7"/>
    </g>
    <g transform="rotate(9 420 200)">
      <rect x="356" y="148" width="122" height="86" rx="18" fill="#fff" opacity=".92"/>
      <text x="374" y="178" font-family="Inter, Segoe UI, sans-serif" font-size="11" fill="#7c899b">Золото, ₽/г</text>
      <text x="374" y="200" font-family="Inter, Segoe UI, sans-serif" font-size="16" font-weight="700" fill="#1c284a">10 870</text>
      <path d="M374 216h60" stroke="#e7efee" stroke-width="6" stroke-linecap="round"/>
      <path d="M374 216h34" stroke="#14d1a3" stroke-width="6" stroke-linecap="round"/>
    </g>
    <g transform="translate(176 238)">
      <ellipse cx="34" cy="26" rx="26" ry="8" fill="#0a9875" opacity=".18"/>
      <rect x="18" y="10" width="16" height="8" rx="3" fill="url(#gold)"/>
      <rect x="8" y="18" width="16" height="8" rx="3" fill="url(#gold)"/>
      <rect x="28" y="18" width="16" height="8" rx="3" fill="url(#gold)"/>
      <rect x="0" y="26" width="16" height="8" rx="3" fill="url(#gold)"/>
      <rect x="20" y="26" width="16" height="8" rx="3" fill="url(#gold)"/>
      <rect x="40" y="26" width="16" height="8" rx="3" fill="url(#gold)"/>
    </g>
  </svg>`;
}

/* ------------------------------------------------------------------ pages: crypto */
function cryptoPage() {
  if (!S.market) return loadingView();
  const meta = S.market.crypto.meta;
  const provider = meta?.provider || S.market.crypto.provider || 'Bybit';
  return `
  ${sourceWarning()}
  <div class="page-head">
    <div><h1>Криптовалюта</h1><p>Цены с Bybit, пересчёт в рубли по курсу ЦБ РФ, динамика за 24 часа и 7 дней. AI-прогноз строит сценарий по истории цены. Кнопка «Купить» ведёт на спотовую пару выбранной монеты.</p></div>
    <div class="head-meta">${sourcePill(provider, meta)}<button class="btn btn--ghost btn--sm" data-action="refresh">${icon('refresh')} Обновить</button></div>
  </div>
  <div class="card table-card">
    <div class="table-wrap">
      <table class="data">
        <thead><tr><th>#</th><th>Актив</th><th class="num">Цена</th><th class="num">24 часа</th><th>7 дней</th><th class="num">Оборот 24ч</th><th>Купить</th><th></th></tr></thead>
        <tbody>
        ${cryptoList().map((c, i) => {
          const rubPrice = rub(c.price);
          return `<tr class="row-click" data-chart="crypto:${esc(c.id)}">
            <td class="muted">${i + 1}</td>
            <td><div class="asset-cell">${cryptoIcon(c)}<span class="txt"><b>${esc(c.name)}</b><small>${esc(c.symbol)} · $${price(c.price)}</small></span></div></td>
            <td class="num"><b>${money(rubPrice)}</b></td>
            <td class="num">${chg(c.change24h)}</td>
            <td style="width:120px"><button class="spark-btn" type="button" data-chart="crypto:${esc(c.id)}" title="Открыть график" aria-label="Открыть график ${esc(c.name)}">${sparkline(c.spark, (c.change24h || 0) >= 0 ? '#0fa97d' : '#e8564b', 120, 34)}</button></td>
            <td class="num muted">${money(c.volume ? rub(c.volume) : null, 0)}</td>
            <td>${c.tradeUrl ? `<a class="buy-link" href="${esc(c.tradeUrl)}" target="_blank" rel="noopener">Купить ${icon('ext')}</a>` : '<span class="muted">—</span>'}</td>
            <td><div class="row-actions">
              <button class="icon-btn" data-add-crypto="${esc(c.id)}" title="В портфель" aria-label="Добавить ${esc(c.name)} в портфель">${icon('plus')}</button>
              <button class="icon-btn" data-chart="crypto:${esc(c.id)}" title="График и AI-анализ" aria-label="График и AI-анализ ${esc(c.name)}">${icon('chart')}</button>
            </div></td>
          </tr>`;
        }).join('')}
        </tbody>
      </table>
    </div>
  </div>
  <p class="muted" style="font-size:11px;margin-top:12px">Данные Bybit обновляются каждые 2 минуты, кэш — на случай недоступности API. Рублёвая цена = цена в USD × курс ЦБ РФ (${num(usdRate(), 2)} ₽). Ссылки ведут на Bybit; проверяйте комиссии и лимиты перед сделкой.</p>`;
}

/* ------------------------------------------------------------------ pages: metals */
function metalsPage() {
  if (!S.market) return loadingView();
  const meta = S.market.metals.meta;
  const date = S.market.metals.items[0]?.date || '';
  return `
  ${sourceWarning()}
  <div class="page-head">
    <div><h1>Драгметаллы</h1><p>Официальные котировки ЦБ РФ: рубли за грамм, унция и динамика за день. AI-прогноз строит сценарий по истории цены. Металлы торгуются в банках и на бирже — сравнивайте спред.</p></div>
    <div class="head-meta">${sourcePill('ЦБ РФ · ' + date, meta)}<button class="btn btn--ghost btn--sm" data-action="refresh">${icon('refresh')} Обновить</button></div>
  </div>
  <div class="metal-cards">
    ${metalList().map((m) => `<article class="card metal-card row-click" data-chart="metal:${esc(m.id)}" tabindex="0" role="button" aria-label="График и информация: ${esc(m.name)}">
      <div class="top">${metalIcon(m.code)}<b>${esc(m.name)}</b><span class="badge badge--gold" style="margin-left:auto">${esc(m.code)}</span></div>
      <div class="price">${money(m.price)}<small> /г</small></div>
      <div class="sub">₽/унция: ${money(m.ozRub)} · $/унция: ${num(m.ozUsd, 2)}</div>
      <div class="chg">${chg(m.change24h)} <span class="muted">за день</span></div>
      <button class="spark-btn" type="button" data-chart="metal:${esc(m.id)}" title="Открыть график" aria-label="Открыть график ${esc(m.name)}">${sparkline(m.spark, m.change24h >= 0 ? '#0fa97d' : '#e8564b', 240, 38)}</button>
      <div class="card-foot"><button class="link-more" data-add-metal="${esc(m.id)}" style="border:0;background:none;padding:0">В портфель ${icon('plus')}</button><button class="link-more" data-chart="metal:${esc(m.id)}" style="border:0;background:none;padding:0">График ${icon('chart')}</button>${ext('https://www.cbr.ru/hd_base/metall/', 'Котировки ЦБ РФ', 'chev-link')}</div>
    </article>`).join('')}
  </div>
  <div class="card table-card">
    <div class="table-wrap">
      <table class="data">
        <thead><tr><th>Металл</th><th class="num">₽ / грамм</th><th class="num">₽ / унция</th><th class="num">$ / унция</th><th class="num">За день</th><th>Котировка</th><th></th></tr></thead>
        <tbody>
        ${metalList().map((m) => `<tr class="row-click" data-chart="metal:${esc(m.id)}">
          <td><div class="asset-cell">${metalIcon(m.code)}<span class="txt"><b>${esc(m.name)}</b><small>${esc(m.code)}</small></span></div></td>
          <td class="num"><b>${money(m.price)}</b></td>
          <td class="num">${money(m.ozRub)}</td>
          <td class="num">$${num(m.ozUsd, 2)}</td>
          <td class="num">${chg(m.change24h)}</td>
          <td class="muted">ЦБ РФ, ${esc(m.date)}</td>
          <td><div class="row-actions"><button class="icon-btn" data-add-metal="${esc(m.id)}" title="В портфель">${icon('plus')}</button><button class="icon-btn" data-chart="metal:${esc(m.id)}" title="График и AI-анализ" aria-label="График и AI-анализ ${esc(m.name)}">${icon('chart')}</button></div></td>
        </tr>`).join('')}
        </tbody>
      </table>
    </div>
  </div>
  <p class="muted" style="font-size:11px;margin-top:12px">ЦБ РФ публикует учётные цены на драгметаллы ежедневно. В банке цена покупки/продажи отличается от учётной — уточняйте в отделении.</p>`;
}

/* ------------------------------------------------------------------ pages: fx */
function fxPage() {
  if (!S.market) return loadingView();
  const fx = S.market.fx;
  return `
  ${sourceWarning()}
  <div class="page-head">
    <div><h1>Валюта</h1><p>Официальные курсы ЦБ РФ на ${esc(fx.date || '')}. Используются для пересчёта криптовалют и металлов в портфеле. AI-прогноз доступен для основных валют.</p></div>
    <div class="head-meta">${sourcePill('ЦБ РФ', fx.meta)}<button class="btn btn--ghost btn--sm" data-action="refresh">${icon('refresh')} Обновить</button></div>
  </div>
  <div class="card table-card">
    <div class="table-wrap">
      <table class="data">
        <thead><tr><th>Валюта</th><th class="num">Курс, ₽</th><th class="num">За день</th><th class="num">Было, ₽</th><th>Номинал</th><th>Источник</th></tr></thead>
        <tbody>
        ${fx.items.map((f) => `<tr class="${['USD', 'EUR', 'CNY', 'GBP'].includes(f.code) ? 'row-click' : ''}"${['USD', 'EUR', 'CNY', 'GBP'].includes(f.code) ? ` data-chart="fx:${esc(f.code)}"` : ''}>
          <td><div class="asset-cell">${coin(f.code, 'coin--silver')}<span class="txt"><b>${esc(f.name || f.code)}</b><small>${esc(f.code)}</small></span></div></td>
          <td class="num"><b>${num(f.value, 4)}</b></td>
          <td class="num">${chg(f.change24h)}</td>
          <td class="num muted">${num(f.prev, 4)}</td>
          <td class="muted">${f.nominal} ${esc(f.code)}</td>
          <td><div class="row-actions"><button class="icon-btn" data-add-fx="${esc(f.code)}" title="В портфель" aria-label="Добавить валюту в портфель">${icon('plus')}</button>${['USD', 'EUR', 'CNY', 'GBP'].includes(f.code) ? `<button class="icon-btn" data-chart="fx:${esc(f.code)}" title="График и AI-анализ" aria-label="График и AI-анализ ${esc(f.code)}">${icon('chart')}</button>` : ''}${ext('https://www.cbr.ru/currency_base/daily/', 'Курсы ЦБ РФ')}</div></td>
        </tr>`).join('')}
        </tbody>
      </table>
    </div>
  </div>`;
}

/* ------------------------------------------------------------------ pages: deposits */
function ruPlural(n, one, few, many) {
  const m10 = n % 10, m100 = n % 100;
  return `${n} ${m10 === 1 && m100 !== 11 ? one : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? few : many}`;
}
function depositTermText(d) {
  if (d.termText) return d.termText;
  if (!d.termDays) return 'срок по условиям';
  if (d.termDays % 365 === 0) return `${d.termDays / 365} г.`;
  if (d.termDays % 30 === 0) return `${d.termDays / 30} мес.`;
  return `${d.termDays} дн.`;
}
function depositAmountText(d) {
  const min = d.min && d.min > 1 ? `от ${money(d.min)}` : '';
  const max = d.max && d.max < 100000000 ? `до ${money(d.max)}` : '';
  return [min, max].filter(Boolean).join(' · ') || 'любая сумма';
}
function depositIncome(d, amount = S.dep.amount, months = S.dep.months) {
  return Number(amount) * ((Number(d.rate) || 0) / 100) * (Number(months) / 12);
}
function depositFits(d, amount = S.dep.amount) {
  if (d.currency && d.currency !== 'RUB') return false;
  if (d.min && amount < d.min) return false;
  if (d.max && amount > d.max) return false;
  return true;
}
function depositMatches() {
  return depositList()
    .filter((d) => depositFits(d))
    .sort((a, b) => (b.rate || 0) - (a.rate || 0));
}
function ensureCalc() {
  const top = bestDeposit();
  S.calc = { amount: S.dep.amount, months: S.dep.months, rate: top ? top.rate : 14, cap: 'month' };
  return S.calc;
}

function depositRowsHtml() {
  const items = depositMatches();
  if (!items.length) return `<div class="empty-state" style="padding:40px 12px">Под эту сумму вкладов нет. Уменьшите сумму — покажем доступные предложения.</div>`;
  const shown = items.slice(0, S.dep.limit);
  const html = shown.map((d) => `<article class="offer" data-deposit="${esc(d.id)}" tabindex="0" role="button" aria-label="Подробнее о вкладе ${esc(d.name)}">
    <div class="offer-logo"><span>${esc((d.bank || 'Б')[0])}</span>${d.logo ? `<img src="${esc(d.logo)}" alt="" referrerpolicy="no-referrer" onerror="this.remove()">` : ''}</div>
    <div class="offer-main">
      <div class="offer-title"><b title="${esc(d.name)}">${esc(d.name)}</b></div>
      <div class="offer-bank">${esc(d.bank)}</div>
      <div class="offer-conditions">
        <span>${esc(depositAmountText(d))}</span>
        <span>${esc(depositTermText(d))}</span>
        <span>${num(d.rate, 2)}% годовых</span>
      </div>
      ${d.note ? `<small class="offer-note">${esc(d.note)}</small>` : ''}
    </div>
    <div class="offer-rate"><b>${num(d.rate, 2)}%</b><span>≈ ${money(depositIncome(d))} за ${S.dep.months} мес.</span></div>
    <div class="offer-actions">
      <button class="icon-btn" data-add-deposit="${esc(d.id)}" title="В портфель" aria-label="Добавить вклад в портфель">${icon('plus')}</button>
      <span class="offer-chev">${icon('chev')}</span>
    </div>
  </article>`).join('');
  const more = items.length - shown.length;
  return html + (more > 0 ? `<button class="btn btn--ghost offers-more" data-action="dep-more">Показать ещё ${Math.min(more, S.dep.limit)} из ${more}</button>` : '');
}

function calcSummaryHtml() {
  const top = bestDeposit();
  const amount = S.dep.amount;
  const months = S.dep.months;
  if (!top) return '<div class="line muted">Нет вкладов под эту сумму. Уменьшите сумму.</div>';
  const gross = depositIncome(top, amount, months);
  const tax = Math.max(0, gross - 1e6 * (keyRateValue() / 100)) * 0.13;
  return `
    <div class="line"><span>Лучшее предложение</span><b>${esc(top.bank)}</b></div>
    <div class="line"><span>Ставка</span><b>${num(top.rate, 2)}% годовых</b></div>
    <div class="line"><span>Доход за ${months} мес.</span><b>${money(gross)}</b></div>
    <div class="line"><span>НДФЛ с процентов</span><b>${tax ? '−' + money(tax) : '0 ₽'}</b></div>
    <div class="total"><span>На руки</span><b>${money(amount + gross - tax)}</b></div>`;
}

function depositsPage() {
  if (!S.deposits) return loadingView();
  ensureCalc();
  const items = depositMatches();
  const banks = new Set(items.map((d) => d.bank)).size;
  const keyRate = S.deposits.keyRate?.value;
  return `
  ${sourceWarning()}
  <div class="page-head">
    <div><h1>Вклады банков</h1><p>${ruPlural(items.length, 'предложение', 'предложения', 'предложений')} от ${banks} банков по вашей сумме. Укажите сумму и срок — покажем условия и доход по каждому вкладу.</p></div>
    <div class="head-meta">
      ${keyRate ? `<span class="pill pill--mint">${icon('bank')} Ключевая ставка ${num(keyRate, 2)}%</span>` : ''}
      <button class="btn btn--ghost btn--sm" data-action="refresh">${icon('refresh')} Обновить</button>
    </div>
  </div>

  <div class="dep-layout">
    <div>
      <div class="dep-filters">
        <label class="dep-filter"><span>Сумма, ₽</span><input id="dep-amount" type="number" min="1000" step="1000" value="${S.dep.amount}" inputmode="numeric"></label>
        <label class="dep-filter"><span>Срок, мес.</span><input id="dep-months" type="number" min="1" max="60" step="1" value="${S.dep.months}" inputmode="numeric"></label>
        <span class="dep-filter-count" id="dep-count">${ruPlural(items.length, 'вклад', 'вклада', 'вкладов')}</span>
      </div>
      <div class="offers" id="dep-list">${depositRowsHtml()}</div>
      <p class="muted" style="font-size:10.5px;margin-top:12px">Ставка и доход зависят от суммы, срока и способа выплаты процентов. Некоторые продукты доступны только новым клиентам — проверьте условия в банке.</p>
    </div>

    <aside class="card calc-card" id="dep-calc">
      <h3>Доход по лучшему вкладу</h3>
      <div class="sub" id="calc-sub">${bestDeposit() ? `${esc(bestDeposit().bank)} · ${esc(bestDeposit().name)}` : 'Нет подходящих предложений'}</div>
      <div class="calc-out" id="calc-result">${calcSummaryHtml()}</div>
      <div style="display:flex;gap:8px;margin-top:12px">
        <button class="btn btn--ghost btn--sm" style="flex:0 0 auto" data-action="calc-add">В портфель</button>
        <span class="muted" style="font-size:10px;line-height:1.35">Расчёт по ставке лучшего предложения. Проверьте условия в банке.</span>
      </div>
      <p class="calc-note">НДФЛ с процентов: 13% с суммы, превышающей 1 млн ₽ × ключевую ставку ЦБ${keyRate ? ` (${num(keyRate, 2)}%)` : ''}.</p>
    </aside>
  </div>`;
}

function updateDepositView() {
  const amount = parseNum($('#dep-amount')?.value);
  const months = parseNum($('#dep-months')?.value);
  if (amount > 0) S.dep.amount = amount;
  if (months > 0) S.dep.months = Math.min(60, Math.round(months));
  S.dep.limit = 40;
  ensureCalc();
  const list = $('#dep-list');
  if (list) list.innerHTML = depositRowsHtml();
  const count = $('#dep-count');
  if (count) count.textContent = ruPlural(depositMatches().length, 'вклад', 'вклада', 'вкладов');
  const out = $('#calc-result');
  if (out) out.innerHTML = calcSummaryHtml();
  const sub = $('#calc-sub');
  const top = bestDeposit();
  if (sub) sub.textContent = top ? `${top.bank} · ${top.name}` : 'Нет подходящих предложений';
}

function openDeposit(id) {
  const d = depositList().find((item) => item.id === id);
  const dialog = $('#deposit-dialog');
  const body = $('#deposit-body');
  if (!d || !dialog || !body) return;
  const income = depositIncome(d);
  const details = [
    ['Банк', d.bank],
    ['Сумма', depositAmountText(d)],
    ['Срок', depositTermText(d)],
    ['Ставка', `${num(d.rate, 2)}% годовых`],
    [`Доход за ${S.dep.months} мес.`, `≈ ${money(income)} до налога`],
  ].filter(([, value]) => value);
  $('#deposit-title').textContent = d.name;
  $('#deposit-sub').textContent = d.bank || 'Вклад';
  body.innerHTML = `
    <div class="deposit-detail-rate"><b>${num(d.rate, 2)}%</b><span>годовых</span></div>
    <div class="deposit-detail-grid">${details.map(([label, value]) => `<div><span>${esc(label)}</span><b>${esc(value)}</b></div>`).join('')}</div>
    ${d.note ? `<p class="deposit-note">${esc(d.note)}</p>` : ''}
    <div class="dialog-actions deposit-actions">
      <button class="btn" type="button" data-add-deposit="${esc(d.id)}">В портфель</button>
      ${d.url ? `<a class="btn btn--ghost" href="${esc(d.url)}" target="_blank" rel="noopener">Условия ${icon('ext')}</a>` : ''}
      <button class="btn btn--ghost" type="button" data-action="close-deposit">Закрыть</button>
    </div>
    <p class="dialog-hint">Ставка и доход зависят от условий банка. Проверьте сумму, срок и способ выплаты процентов перед открытием.</p>`;
  if (!dialog.open) dialog.showModal();
}

/* ------------------------------------------------------------------ pages: realty */
function realtyRowsHtml() {
  let items = realtyList();
  if (S.re.q) {
    const q = S.re.q.toLowerCase();
    items = items.filter((r) => (r.title + ' ' + r.address + ' ' + r.district + ' ' + r.metro + ' ' + r.city).toLowerCase().includes(q));
  }
  if (S.re.source !== 'all') items = items.filter((r) => r.source === S.re.source);
  if (S.re.city !== 'all') items = items.filter((r) => r.city === S.re.city);
  if (S.re.rooms === '4') items = items.filter((r) => Number(r.rooms) >= 4);
  else if (S.re.rooms !== 'all') items = items.filter((r) => String(r.rooms) === S.re.rooms);
  const sort = S.re.sort;
  items = [...items].sort((a, b) => sort === 'priceDesc' ? b.price - a.price
    : sort === 'area' ? (b.area || 0) - (a.area || 0)
    : sort === 'm2' ? (a.priceM2 || 0) - (b.priceM2 || 0)
    : a.price - b.price);
  if (!items.length) return `<div class="empty-state" style="padding:40px 12px">Ничего не найдено. Измените фильтры.</div>`;
  const shown = items.slice(0, S.re.limit);
  const html = `<div class="re-grid">${shown.map((r) => `<article class="re-card" data-realty="${esc(r.id)}" tabindex="0" role="button" aria-label="Подробнее: ${esc(r.title)}">
    <div class="re-img">${r.img ? `<img src="${esc(r.img)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : ''}<span class="re-city">${esc(r.city === 'Санкт-Петербург' ? 'СПб' : (r.city || 'Россия'))}</span></div>
    <div class="re-body">
      <div class="re-top"><b>${r.rooms === 'Студия' ? 'Студия' : esc(r.rooms) + '-комн.'}${r.area ? ` · ${num(r.area, 1)} м²` : ''}</b><span class="re-price">${money(r.price)}</span></div>
      <div class="re-addr">${esc(r.address || r.district)}</div>
      <div class="re-meta">${[r.metro, r.district].filter(Boolean).map(esc).join(' · ') || esc(r.city || 'Россия')}${r.priceM2 ? ` · ${money(r.priceM2)}/м²` : ''}</div>
      <div class="re-foot"><span class="offer-src">${esc(r.source)}</span>${ext(r.url, 'Открыть объявление')}<span class="re-chev">${icon('chev')}</span></div>
    </div>
  </article>`).join('')}</div>`;
  const more = items.length - shown.length;
  return html + (more > 0 ? `<button class="btn btn--ghost offers-more" data-action="re-more">Показать ещё ${Math.min(more, S.re.limit)} из ${more}</button>` : '');
}

function realtyCities() {
  const counts = new Map();
  realtyList().forEach((r) => { if (r.city) counts.set(r.city, (counts.get(r.city) || 0) + 1); });
  const pinned = ['Москва', 'Санкт-Петербург'];
  const rest = [...counts.keys()].filter((city) => !pinned.includes(city)).sort((a, b) => a.localeCompare(b, 'ru'));
  return [
    ...pinned.filter((city) => counts.has(city)).map((city) => ({ city, count: counts.get(city), pinned: true })),
    ...rest.map((city) => ({ city, count: counts.get(city), pinned: false })),
  ];
}

function cityPickerHtml() {
  const cities = realtyCities();
  const option = (city, count, pinned) => `<button type="button" class="city-option${S.re.city === city ? ' is-active' : ''}${pinned ? ' is-pinned' : ''}" data-city-option="${esc(city)}" role="option" aria-selected="${S.re.city === city ? 'true' : 'false'}"><span>${esc(city)}</span><small>${num(count, 0)}</small></button>`;
  return `<div class="city-select" id="re-city-select">
    <button type="button" class="city-select-btn" id="re-city-btn" aria-haspopup="listbox" aria-expanded="false"><span class="city-select-label">${S.re.city === 'all' ? 'Все города' : esc(S.re.city)}</span>${icon('chev')}</button>
    <div class="city-pop" id="re-city-pop" hidden>
      <input type="search" id="re-city-q" placeholder="Найти город…" autocomplete="off">
      <div class="city-list" id="re-city-list" role="listbox">
        <button type="button" class="city-option${S.re.city === 'all' ? ' is-active' : ''}" data-city-option="all" role="option" aria-selected="${S.re.city === 'all' ? 'true' : 'false'}"><span>Все города</span><small>${num(realtyList().length, 0)}</small></button>
        ${cities.map((c) => option(c.city, c.count, c.pinned)).join('')}
      </div>
    </div>
  </div>`;
}

function closeCityPicker() {
  const pop = $('#re-city-pop');
  if (pop) pop.hidden = true;
  $('#re-city-btn')?.setAttribute('aria-expanded', 'false');
}

function setRealtyCity(city) {
  S.re.city = city;
  S.re.limit = 24;
  const label = $('#re-city-btn .city-select-label');
  if (label) label.textContent = city === 'all' ? 'Все города' : city;
  $$('#re-city-list .city-option').forEach((btn) => {
    const active = btn.dataset.cityOption === city;
    btn.classList.toggle('is-active', active);
    btn.setAttribute('aria-selected', active ? 'true' : 'false');
  });
  closeCityPicker();
  const list = $('#re-list');
  if (list) list.innerHTML = realtyRowsHtml();
}

function filterCityOptions(query) {
  const q = query.trim().toLowerCase();
  $$('#re-city-list .city-option').forEach((btn) => {
    btn.hidden = !!q && !(btn.querySelector('span')?.textContent || '').toLowerCase().includes(q);
  });
}

function realtyPage() {
  if (!S.realty) return loadingView();
  const msk = S.realty.stats?.moscow;
  const russia = S.realty.stats?.russia;
  const sources = S.realty.sources || [];
  return `
  ${sourceWarning()}
  <div class="page-head">
    <div><h1>Недвижимость</h1><p>Средние цены по Москве и объявления со всей России: Яндекс.Недвижимость, Авито, Циан и БН.ру. Выберите город или введите адрес — ссылки ведут на первоисточник.</p></div>
    <div class="head-meta">${sources.map((s) => sourcePill(s.name, s.meta)).join('')}<button class="btn btn--ghost btn--sm" data-action="refresh">${icon('refresh')} Обновить</button></div>
  </div>

  <div class="realty-stats">
    ${msk ? `<div class="card stat-card">
      <div class="stat-head"><span class="badge badge--blue">Москва</span><a class="link-more" href="${esc(msk.url)}" target="_blank" rel="noopener">${esc(msk.source)} ${icon('ext')}</a></div>
      <div class="stat-big">${money(msk.avgPrice)}</div>
      <div class="muted">средняя цена квартиры</div>
      <div class="stat-rows">
        <div><span>Цена м²</span><b>${money(msk.avgM2)}</b></div>
        <div><span>Объявлений в базе</span><b>${num(msk.count, 0)}</b></div>
        <div><span>Диапазон</span><b>${money(msk.min)} – ${money(msk.max)}</b></div>
      </div>
    </div>` : ''}
    ${russia ? `<div class="card stat-card">
      <div class="stat-head"><span class="badge">Россия</span><a class="link-more" href="${esc(russia.url)}" target="_blank" rel="noopener">${esc(russia.source)} ${icon('ext')}</a></div>
      <div class="stat-big">${money(russia.median)}</div>
      <div class="muted">медиана в выборке объявлений</div>
      <div class="stat-rows">
        <div><span>Средняя цена м²</span><b>${money(russia.avgM2)}</b></div>
        <div><span>Объявлений в выборке</span><b>${num(russia.count, 0)}</b></div>
        <div><span>Городов в выборке</span><b>${num(russia.cities, 0)}</b></div>
      </div>
    </div>` : ''}
  </div>

  <div class="filters">
    <input type="search" id="re-search" placeholder="Город, район, метро или адрес…" value="${esc(S.re.q)}" autocomplete="off">
    ${cityPickerHtml()}
    <select id="re-source" aria-label="Источник">
      <option value="all" ${S.re.source === 'all' ? 'selected' : ''}>Все источники</option>
      ${sources.filter((s) => s.key !== 'moscow').map((s) => `<option value="${esc(s.name)}" ${S.re.source === s.name ? 'selected' : ''}>${esc(s.name)}${s.scope ? ` · ${esc(s.scope)}` : ''} · ${s.count}</option>`).join('')}
    </select>
    <select id="re-rooms" aria-label="Комнат">
      <option value="all" ${S.re.rooms === 'all' ? 'selected' : ''}>Любая комнатность</option>
      <option value="Студия" ${S.re.rooms === 'Студия' ? 'selected' : ''}>Студия</option>
      <option value="1" ${S.re.rooms === '1' ? 'selected' : ''}>1 комната</option>
      <option value="2" ${S.re.rooms === '2' ? 'selected' : ''}>2 комнаты</option>
      <option value="3" ${S.re.rooms === '3' ? 'selected' : ''}>3 комнаты</option>
      <option value="4" ${S.re.rooms === '4' ? 'selected' : ''}>4+ комнат</option>
    </select>
    <select id="re-sort" aria-label="Сортировка">
      <option value="price" ${S.re.sort === 'price' ? 'selected' : ''}>Сначала дешёвые</option>
      <option value="priceDesc" ${S.re.sort === 'priceDesc' ? 'selected' : ''}>Сначала дорогие</option>
      <option value="m2" ${S.re.sort === 'm2' ? 'selected' : ''}>Цена м²</option>
      <option value="area" ${S.re.sort === 'area' ? 'selected' : ''}>Площадь</option>
    </select>
  </div>
  <div id="re-list">${realtyRowsHtml()}</div>
  <p class="muted" style="font-size:10.5px;margin-top:12px">Объявления — выборка с Яндекса и Авито по всей России, Циана и БН.ру по Санкт-Петербургу; средние цены Москвы — оценка «Мир квартир». Цены и наличие уточняйте на сайте источника. Сервис не является оценкой недвижимости.</p>`;
}

let realtyGallery = { id: '', images: [], index: 0 };

function realtyHiRes(url) {
  return String(url || '')
    .replace(/\/minicard$/, '/main')
    .replace(/realty_minicard$/, 'realty_main')
    .replace('/s/640x480/', '/s/1280x960/');
}

function realtyGalleryHtml() {
  const images = realtyGallery.images || [];
  if (!images.length) return '<div class="realty-photo-wrap"><div class="realty-photo-empty">Нет фото</div></div>';
  const index = Math.min(realtyGallery.index, images.length - 1);
  return `<div class="realty-photo-wrap">
      <div class="realty-photo-empty">Нет фото</div>
      <img class="realty-photo" src="${esc(images[index])}" alt="" loading="eager" referrerpolicy="no-referrer" onerror="this.remove()">
      <span class="realty-photo-count">${index + 1} / ${images.length}</span>
    </div>
    ${images.length > 1 ? `<div class="realty-thumbs">${images.map((src, i) => `<button class="realty-thumb${i === index ? ' is-active' : ''}" type="button" data-realty-photo="${i}" aria-label="Фото ${i + 1}"><img src="${esc(src)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()"></button>`).join('')}</div>` : ''}`;
}

function renderRealtyGallery() {
  const box = $('#realty-gallery');
  if (box) box.innerHTML = realtyGalleryHtml();
}

function openRealty(id) {
  const item = realtyList().find((r) => r.id === id);
  const dialog = $('#realty-dialog');
  const body = $('#realty-body');
  const title = $('#realty-title');
  const sub = $('#realty-sub');
  if (!item || !dialog || !body) return;
  const rooms = item.rooms === 'Студия' ? 'Студия' : item.rooms ? `${item.rooms}-комн.` : 'Квартира';
  realtyGallery = { id: item.id, images: item.img ? [realtyHiRes(item.img)] : [], index: 0 };
  if (title) title.textContent = item.title || rooms;
  if (sub) sub.textContent = [item.city, item.source].filter(Boolean).join(' · ');
  const details = [
    ['Город', item.city],
    ['Район', item.district],
    ['Метро', item.metro],
    ['Комнат', item.rooms === 'Студия' ? 'Студия' : item.rooms],
    ['Площадь', item.area ? `${num(item.area, 1)} м²` : ''],
    ['Тип', item.sub],
  ].filter(([, value]) => value && value !== '—');
  body.innerHTML = `
    <div id="realty-gallery">${realtyGalleryHtml()}</div>
    <div class="realty-price-row">
      <div><div class="realty-price">${money(item.price)}</div>${item.priceM2 ? `<div class="muted">${money(item.priceM2)} / м²</div>` : ''}</div>
      <span class="badge badge--blue">${esc(item.source || 'Источник')}</span>
    </div>
    <div class="realty-address">${esc(item.address || item.city || '')}</div>
    <div class="realty-grid">${details.map(([label, value]) => `<div><span>${esc(label)}</span><b>${esc(value)}</b></div>`).join('')}</div>
    <div class="realty-actions">
      ${item.url ? `<a class="btn btn--ghost btn--sm" href="${esc(item.url)}" target="_blank" rel="noopener">Открыть на источнике ${icon('ext')}</a>` : ''}
      <button class="btn btn--sm" type="button" data-action="close-realty">Закрыть</button>
    </div>
    <p class="realty-note">Данные из объявления на момент сбора. Цены и наличие уточняйте у источника.</p>`;
  if (!dialog.open) dialog.showModal();
  if (item.id.startsWith('yandex:')) {
    fetch(`/api/realty-photos?id=${encodeURIComponent(item.id)}`)
      .then((res) => res.json().catch(() => ({})))
      .then((data) => {
        if (realtyGallery.id !== item.id || !data.images?.length) return;
        realtyGallery.images = data.images.map(realtyHiRes);
        realtyGallery.index = 0;
        renderRealtyGallery();
      })
      .catch(() => {});
  }
}

/* ------------------------------------------------------------------ pages: portfolio */
function portfolioPage() {
  if (!S.market) return loadingView();
  const v = valuation();
  if (!v.rows.length) {
    return `${sourceWarning()}
    <div class="page-head"><div><h1>Портфель</h1><p>Один расчёт по крипте, валютам, металлам и вкладам — с пересчётом в рубли и доходностью.</p></div>
      <div class="head-meta"><button class="btn" data-action="open-add">${icon('plus')} Добавить позицию</button><button class="btn btn--ghost" data-action="demo">Демо-портфель</button></div></div>
    <div class="card empty-card">
      <h3>Пока пусто</h3>
      <p>Добавьте актив вручную или загрузите демонстрационный портфель, чтобы увидеть расчёт стоимости, прибыли, долей и XIRR.</p>
      <div class="empty-actions"><button class="btn" data-action="open-add">Добавить позицию</button><button class="btn btn--ghost" data-action="demo">Загрузить демо</button></div>
    </div>`;
  }

  const legend = [];
  if (v.rows.length > 7) {
    const rest = v.rows.slice(6);
    legend.push(...v.rows.slice(0, 6));
    legend.push({ name: 'Другие активы', cur: rest.reduce((s, r) => s + r.cur, 0), other: true });
  } else legend.push(...v.rows);

  let acc = 0;
  const stops = legend.map((r, i) => {
    const from = (acc / (v.value || 1)) * 100;
    acc += r.cur;
    const to = (acc / (v.value || 1)) * 100;
    return `${PALETTE[i % PALETTE.length]} ${from.toFixed(2)}% ${to.toFixed(2)}%`;
  }).join(', ');

  return `${sourceWarning()}
  <div class="page-head">
    <div><h1>Портфель</h1><p>Стоимость пересчитывается по текущим котировкам. Вклады — с капитализацией и налогом на проценты; валюта — по курсу ЦБ.</p></div>
    <div class="head-meta">
      <button class="btn" data-action="open-add">${icon('plus')} Добавить</button>
      <button class="btn btn--ghost btn--sm" data-action="demo">Демо</button>
      <button class="btn btn--ghost btn--sm" data-action="clear">Очистить</button>
    </div>
  </div>

  <div class="summary">
    <div class="card card--accent">
      <div class="label">Стоимость портфеля</div>
      <div class="value">${money(v.value)}</div>
      <div class="hint">За сутки <span class="${v.changeDay >= 0 ? 'up' : 'down'}">${v.changeDay >= 0 ? '+' : ''}${money(v.changeDay)} (${pct(v.changePct)})</span></div>
    </div>
    <div class="card">
      <div class="label">Вложено</div>
      <div class="value">${money(v.invested)}</div>
      <div class="hint">${v.rows.length} позиции · ${new Set(v.rows.map((r) => r.p.kind)).size} класса</div>
    </div>
    <div class="card">
      <div class="label">Прибыль</div>
      <div class="value ${v.pnl >= 0 ? 'up' : 'down'}">${v.pnl >= 0 ? '+' : ''}${money(v.pnl)}</div>
      <div class="hint"><span class="${v.pnl >= 0 ? 'up' : 'down'}">${pct(v.pnlPct)}</span> к вложенному</div>
    </div>
    <div class="card">
      <div class="label">Доходность XIRR</div>
      <div class="value">${v.irr == null ? '—' : pct(v.irr * 100)}</div>
      <div class="hint">${v.depositIncome ? `проценты по вкладам: ${money(v.depositIncome)}` : 'годовых, по денежным потокам'}</div>
    </div>
  </div>

  <div class="portfolio-grid">
    <div class="card alloc">
      <div class="rail-title"><h3>Структура</h3><span class="pill pill--mint">${v.rows.length} поз.</span></div>
      <div class="donut-wrap">
        <div class="donut" style="background:conic-gradient(${stops || '#eef4f3 0 100%'})"></div>
        <div class="donut-center"><b>${money(v.value)}</b><span>всего</span></div>
      </div>
      <div class="legend">
        ${legend.map((r, i) => `<div class="legend-row"><span class="sw" style="background:${PALETTE[i % PALETTE.length]}"></span><span class="lname">${esc(r.name)}</span><span class="lval">${money(r.cur)}</span><span class="lshare">${num((r.cur / (v.value || 1)) * 100, 1)}%</span></div>`).join('')}
      </div>
    </div>

    <div class="card table-card" style="padding:0">
      <div class="pos-row pos-row--head">
        <div>Актив</div><div class="num">Стоимость</div><div class="num">Вложено</div><div class="num">Прибыль</div><div class="num">Доля</div><div></div>
      </div>
      <div class="pos-list">
        ${v.rows.map((r, i) => {
          const badgeCls = r.p.kind === 'crypto' ? '' : r.p.kind === 'metal' ? 'coin--gold' : 'coin--silver';
          const title = r.p.kind === 'deposit' ? `${r.name} · ${r.p.bank || ''}` : r.name;
          return `<div class="pos-row">
            <div class="pos-asset">
              <span class="coin ${badgeCls}">${esc((r.iconText || '?').slice(0, 4))}</span>
              <span class="txt"><b>${r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(title)}</a>` : esc(title)}</b><small>${r.sub}</small></span>
            </div>
            <div class="cell num"><span class="lbl">Стоимость</span>${money(r.cur)}</div>
            <div class="cell num"><span class="lbl">Вложено</span>${money(r.cost)}</div>
            <div class="cell num"><span class="lbl">Прибыль</span><span class="${r.pnl >= 0 ? 'up' : 'down'}">${r.pnl >= 0 ? '+' : ''}${money(r.pnl)}<br><small>${pct(r.pnlPct)}</small></span></div>
            <div class="cell num"><span class="lbl">Доля</span>${num((r.cur / (v.value || 1)) * 100, 1)}%</div>
            <div class="pos-actions"><button class="icon-btn" data-del="${esc(r.p.id)}" title="Удалить позицию" aria-label="Удалить позицию">${icon('trash')}</button></div>
          </div>`;
        }).join('')}
      </div>
    </div>
  </div>
  <p class="muted" style="font-size:10.5px;margin-top:12px">Налог по вкладам считается по текущей ключевой ставке${keyRateValue() ? ` (${num(keyRateValue(), 2)}%)` : ''} на весь срок; фактические суммы могут отличаться. Портфель хранится в localStorage браузера; при запросе к AI отправляется только сводка по позициям и рыночным данным.</p>`;
}

/* ------------------------------------------------------------------ pages: search */
function searchPage(params) {
  const q = (params.get('q') || '').trim();
  $('#search-input').value = q;
  if (!q) return `<div class="page-head"><div><h1>Поиск</h1><p>Введите название актива, банка или валюты. Например: «биткоин», «золото», «Альфа», «USD».</p></div></div>`;
  const needle = q.toLowerCase();
  const found = [];
  cryptoList().forEach((c) => {
    if ((c.name + ' ' + c.symbol).toLowerCase().includes(needle)) found.push({ type: 'Криптовалюта · Bybit', name: c.name, sub: c.symbol, value: money(rub(c.price)), chg: c.change24h, href: '#/crypto', url: c.tradeUrl });
  });
  metalList().forEach((m) => {
    if ((m.name + ' ' + m.code).toLowerCase().includes(needle)) found.push({ type: 'Драгметалл', name: m.name, sub: m.code, value: money(m.price) + '/г', chg: m.change24h, href: '#/metals' });
  });
  (S.market?.fx?.items || []).forEach((f) => {
    if ((f.code + ' ' + (f.name || '')).toLowerCase().includes(needle)) found.push({ type: 'Валюта', name: f.name || f.code, sub: f.code, value: num(f.value, 3) + ' ₽', chg: f.change24h, href: '#/fx' });
  });
  depositList().forEach((d) => {
    if ((d.bank + ' ' + d.name).toLowerCase().includes(needle)) found.push({ type: 'Вклад', name: d.name, sub: `${d.bank}${d.termDays ? ' · ' + d.termDays + ' дн.' : ''}`, value: num(d.rate, 2) + '%', chg: null, href: '#/deposits', url: d.url });
  });
  realtyList().forEach((r) => {
    if ((r.title + ' ' + r.address + ' ' + r.district + ' ' + r.metro + ' ' + r.city).toLowerCase().includes(needle)) found.push({ type: 'Недвижимость', name: r.title, sub: `${r.city} · ${r.district || r.address}`, value: money(r.price), chg: null, href: '#/realty', url: r.url });
  });

  return `${sourceWarning()}
  <div class="page-head"><div><h1>Результаты: «${esc(q)}»</h1><p>Найдено ${found.length} ${found.length === 1 ? 'совпадение' : 'совпадений'} по всем рынкам.</p></div></div>
  <div class="card table-card">
    ${found.length ? `
    <div class="pos-row pos-row--head"><div>Инструмент</div><div class="num">Цена</div><div class="num">Изменение</div><div></div></div>
    <div class="pos-list">
      ${found.map((f) => `<div class="pos-row" style="grid-template-columns:minmax(0,1.8fr) minmax(0,1fr) minmax(0,.8fr) 36px">
        <div class="pos-asset"><span class="coin">${esc(f.sub.slice(0, 4))}</span><span class="txt"><b>${esc(f.name)}</b><small>${esc(f.type)} · ${esc(f.sub)}</small></span></div>
        <div class="cell num">${f.value}</div>
        <div class="cell num">${chg(f.chg)}</div>
        <div class="pos-actions">${f.url ? ext(f.url, 'Открыть источник') : `<a class="chev-link" href="${f.href}">${icon('chev')}</a>`}</div>
      </div>`).join('')}
    </div>` : `<div class="empty-state">Ничего не найдено. Попробуйте другой запрос.</div>`}
  </div>`;
}

/* ------------------------------------------------------------------ router */
function route() {
  const hash = location.hash.replace(/^#\/?/, '');
  const [page, qs] = hash.split('?');
  return { page: page || 'home', params: new URLSearchParams(qs || '') };
}

function renderUser() {
  const profile = activeProfile();
  const avatar = $('#user-avatar');
  const name = $('#user-name');
  if (avatar) avatar.textContent = (profile.name || '?').trim().charAt(0).toUpperCase() || '?';
  if (name) name.textContent = profile.name;
}

function renderProfileForm() {
  const profile = activeProfile();
  const select = $('#profile-select');
  if (!select) return;
  select.innerHTML = S.profiles.items.map((p) => `<option value="${esc(p.id)}" ${p.id === profile.id ? 'selected' : ''}>${esc(p.name)}</option>`).join('');
  $('#profile-name').value = profile.name;
  $('#profile-delete').disabled = S.profiles.items.length < 2;
}

function openProfileDialog() {
  renderProfileForm();
  const dlg = $('#profile-dialog');
  if (!dlg.open) dlg.showModal();
}

function switchProfile(id) {
  if (!S.profiles.items.some((p) => p.id === id)) return;
  savePortfolio();
  S.profiles.active = id;
  saveProfiles();
  S.portfolio = loadPortfolio(id);
  renderProfileForm();
  render();
  renderUser();
  toast(`Профиль: ${activeProfile().name}`);
}

function createProfile() {
  if (S.profiles.items.length >= 10) return toast('Не больше 10 профилей', true);
  savePortfolio();
  const id = 'u' + Date.now().toString(36);
  S.profiles.items.push({ id, name: `Профиль ${S.profiles.items.length + 1}` });
  S.profiles.active = id;
  S.portfolio = [];
  saveProfiles();
  savePortfolio();
  renderProfileForm();
  render();
  renderUser();
  toast('Новый профиль создан');
}

function deleteProfile() {
  if (S.profiles.items.length < 2) return toast('Нельзя удалить единственный профиль', true);
  const profile = activeProfile();
  if (!confirm(`Удалить профиль «${profile.name}» и его портфель?`)) return;
  S.profiles.items = S.profiles.items.filter((p) => p.id !== profile.id);
  localStorage.removeItem(PORTFOLIO_PREFIX + profile.id);
  S.profiles.active = S.profiles.items[0].id;
  saveProfiles();
  S.portfolio = loadPortfolio(S.profiles.active);
  renderProfileForm();
  render();
  renderUser();
  toast('Профиль удалён');
}

function saveProfileName(e) {
  e.preventDefault();
  const input = $('#profile-name');
  const name = input.value.trim().slice(0, 24);
  if (!name) {
    input.focus();
    return toast('Введите имя профиля', true);
  }
  activeProfile().name = name;
  saveProfiles();
  renderProfileForm();
  render();
  renderUser();
  toast('Имя профиля сохранено');
}

function render() {
  const { page, params } = route();
  const view = $('#view');
  let html = '';
  let navKey = page;

  if (page === 'home') html = homePage();
  else if (page === 'crypto') html = cryptoPage();
  else if (page === 'metals') html = metalsPage();
  else if (page === 'fx') html = fxPage();
  else if (page === 'deposits') html = depositsPage();
  else if (page === 'realty') html = realtyPage();
  else if (page === 'portfolio') html = portfolioPage();
  else if (page === 'search') html = searchPage(params);
  else html = `<div class="empty-state"><h3>Страница не найдена</h3><a class="btn" href="#/">На главную</a></div>`;

  view.innerHTML = html;

  if (page === 'deposits' && params.get('calc')) navKey = 'calc';
  $$('[data-nav]').forEach((a) => a.classList.toggle('active', a.dataset.nav === navKey));

  if (page === 'deposits' && params.get('calc')) {
    setTimeout(() => $('#dep-calc')?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 80);
  }
  if (page === 'search') {
    const q = params.get('q') || '';
    const input = $('#search-input');
    if (document.activeElement !== input) input.value = q;
  }
  document.title = `${pageTitle(page)} — Монетка`;
  updateSideStatus();
  renderUser();
}

function pageTitle(page) {
  return { home: 'Главная', crypto: 'Криптовалюта', metals: 'Драгметаллы', fx: 'Валюта', deposits: 'Вклады банков', realty: 'Недвижимость', portfolio: 'Портфель', search: 'Поиск' }[page] || 'Монетка';
}

function updateSideStatus() {
  const el = $('#side-status');
  if (!el) return;
  const m = S.market;
  const ok = m && m.crypto?.meta?.ok !== false && m.fx?.meta?.ok !== false;
  const t = timeOf(m?.fx?.meta?.updated || m?.crypto?.meta?.updated);
  el.textContent = S.loading ? 'Загрузка котировок…'
    : `${ok ? 'Котировки онлайн' : 'Котировки из кэша'} · ${t}${S.deposits ? ' · вклады' : ''}${S.realty ? ' · недвижимость' : ''}`;
}

/* ------------------------------------------------------------------ add position dialog */
function openAdd(kind = 'crypto', preset = {}) {
  S.addKind = kind;
  S.addPreset = preset;
  renderAddFields();
  $('#form-error').textContent = '';
  const dlg = $('#add-dialog');
  if (!dlg.open) dlg.showModal();
}

function fieldHtml(label, inner, full = false) {
  return `<div class="field ${full ? 'field--full' : ''}"><label>${label}</label>${inner}</div>`;
}

function renderAddFields() {
  $$('#kind-seg .seg-btn').forEach((b) => b.classList.toggle('is-active', b.dataset.kind === S.addKind));
  const box = $('#add-fields');
  const today = isoDate();
  const preset = S.addPreset;

  if (S.addKind === 'crypto' || S.addKind === 'metal' || S.addKind === 'fx') {
    const isCrypto = S.addKind === 'crypto';
    const isFx = S.addKind === 'fx';
    const list = isCrypto ? cryptoList() : isFx ? fxList() : metalList();
    if (!list.length) {
      box.innerHTML = `<p class="muted" style="grid-column:1/-1">Котировки ещё не загружены. Попробуйте через минуту.</p>`;
      return;
    }
    const assetId = (a) => isFx ? a.code : a.id;
    const selected = preset.assetId || assetId(list[0]);
    const item = list.find((x) => assetId(x) === selected) || list[0];
    const unitPrice = isCrypto ? rub(item.price) : isFx ? item.value : item.price;
    box.innerHTML = `
      ${fieldHtml(isCrypto ? 'Актив' : isFx ? 'Валюта' : 'Металл', `<select id="f-asset">${list.map((a) => `<option value="${esc(assetId(a))}" ${assetId(a) === selected ? 'selected' : ''}>${esc(a.name)} · ${esc(isCrypto ? a.symbol : isFx ? a.code : '₽/г')}</option>`).join('')}</select>`, true)}
      ${fieldHtml(isCrypto || isFx ? 'Количество' : 'Граммы', `<input id="f-qty" type="number" min="0" step="any" inputmode="decimal" placeholder="${isFx ? '1000' : '0,05'}" value="${preset.qty || ''}">`)}
      ${fieldHtml(isFx ? 'Цена покупки, ₽ за единицу' : 'Цена покупки, ₽', `<input id="f-buy" type="number" min="0" step="any" inputmode="decimal" value="${preset.buy || unitPrice}">`)}
      ${fieldHtml('Дата покупки', `<input id="f-date" type="date" max="${today}" value="${preset.date || today}">`, true)}
      <div class="field field--full muted" style="font-size:10.5px">Текущая цена: ${money(unitPrice)}${isCrypto ? ` · $${price(item.price)}` : isFx ? ` за 1 ${esc(item.code)}` : '/г'}${isCrypto && item.tradeUrl ? ` · <a class="link-more" href="${esc(item.tradeUrl)}" target="_blank" rel="noopener">Купить ${esc(item.symbol)} на Bybit ${icon('ext')}</a>` : ''}.</div>`;
  } else {
    const offers = depositList();
    const top = offers[0];
    const selected = preset.offerId || (top ? top.id : '');
    box.innerHTML = `
      ${fieldHtml('Вклад из подборки', `<select id="f-offer"><option value="">Свой вклад</option>${offers.map((d) => `<option value="${esc(d.id)}" ${d.id === selected ? 'selected' : ''}>${esc(d.bank)} — ${esc(d.name)} (${num(d.rate, 2)}%)</option>`).join('')}</select>`, true)}
      ${fieldHtml('Название', `<input id="f-name" type="text" maxlength="80" value="${esc(preset.name || (top ? `${top.name}` : ''))}" placeholder="Например, Мой вклад">`, true)}
      ${fieldHtml('Сумма, ₽', `<input id="f-amount" type="number" min="1000" step="1000" value="${preset.amount || 300000}">`)}
      ${fieldHtml('Ставка, %', `<input id="f-rate" type="number" min="0" max="50" step="0.01" value="${preset.rate ?? (top ? top.rate : 14)}">`)}
      ${fieldHtml('Дата открытия', `<input id="f-date" type="date" max="${today}" value="${preset.date || today}">`)}
      ${fieldHtml('Срок, мес.', `<input id="f-months" type="number" min="1" max="60" step="1" value="${preset.months || 12}">`)}
      ${fieldHtml('Капитализация', `<select id="f-cap"><option value="month" ${preset.cap !== 'none' && preset.cap !== 'quarter' ? 'selected' : ''}>Ежемесячно</option><option value="quarter" ${preset.cap === 'quarter' ? 'selected' : ''}>Ежеквартально</option><option value="none" ${preset.cap === 'none' ? 'selected' : ''}>Без капитализации</option></select>`, true)}
      <div class="field field--full muted" style="font-size:10.5px">Ставку можно изменить вручную — например, если банк дал индивидуальные условия.</div>`;
  }
}

function handleSubmit(e) {
  e.preventDefault();
  const err = $('#form-error');
  const date = $('#f-date')?.value || isoDate();
  let pos = null;

  if (S.addKind === 'crypto' || S.addKind === 'metal' || S.addKind === 'fx') {
    const qty = parseNum($('#f-qty')?.value);
    const buy = parseNum($('#f-buy')?.value);
    if (!(qty > 0)) return void (err.textContent = 'Укажите количество больше нуля.');
    if (!(buy >= 0)) return void (err.textContent = 'Укажите цену покупки.');
    const list = S.addKind === 'crypto' ? cryptoList() : S.addKind === 'fx' ? fxList() : metalList();
    const asset = list.find((a) => (S.addKind === 'fx' ? a.code : a.id) === $('#f-asset').value);
    if (!asset) return void (err.textContent = 'Выберите актив.');
    pos = {
      id: uid(), kind: S.addKind, assetId: S.addKind === 'fx' ? asset.code : asset.id, name: asset.name,
      qty, buy, date,
    };
  } else {
    const amount = parseNum($('#f-amount')?.value);
    const rate = parseNum($('#f-rate')?.value);
    const months = parseNum($('#f-months')?.value);
    if (!(amount > 0)) return void (err.textContent = 'Укажите сумму вклада.');
    if (!(rate >= 0)) return void (err.textContent = 'Укажите ставку.');
    if (!(months > 0)) return void (err.textContent = 'Укажите срок в месяцах.');
    const offer = depositList().find((d) => d.id === $('#f-offer')?.value);
    pos = {
      id: uid(), kind: 'deposit',
      assetId: offer?.id || '',
      name: $('#f-name')?.value.trim() || offer?.name || 'Вклад',
      bank: offer?.bank || 'Банк',
      url: offer?.url || '',
      amount, rate, months, cap: $('#f-cap')?.value || 'month', date,
    };
  }

  S.portfolio.push(pos);
  savePortfolio();
  err.textContent = '';
  $('#add-dialog').close();
  render();
  toast('Позиция добавлена в портфель');
}

function addDemo() {
  if (S.portfolio.length && !confirm('Заменить текущий портфель демонстрационным?')) return;
  const now = new Date();
  const btc = findCrypto('bitcoin');
  const eth = findCrypto('ethereum');
  const gold = findMetal('XAU');
  const silver = findMetal('XAG');
  const usd = findFx('USD');
  const top = bestDeposit();
  const daysAgo = (n) => isoDate(new Date(Date.now() - n * 864e5));
  const positions = [];
  if (btc) positions.push({ id: uid(), kind: 'crypto', assetId: 'bitcoin', name: 'Bitcoin', qty: 0.05, buy: rub(btc.price) * 0.88, date: daysAgo(140) });
  if (eth) positions.push({ id: uid(), kind: 'crypto', assetId: 'ethereum', name: 'Ethereum', qty: 1.5, buy: rub(eth.price) * 0.93, date: daysAgo(90) });
  if (gold) positions.push({ id: uid(), kind: 'metal', assetId: 'XAU', name: 'Золото', qty: 30, buy: gold.price * 0.94, date: daysAgo(220) });
  if (silver) positions.push({ id: uid(), kind: 'metal', assetId: 'XAG', name: 'Серебро', qty: 500, buy: silver.price * 1.02, date: daysAgo(60) });
  if (usd) positions.push({ id: uid(), kind: 'fx', assetId: 'USD', name: 'Доллар США', qty: 1000, buy: usd.value * 0.97, date: daysAgo(120) });
  if (top) positions.push({
    id: uid(), kind: 'deposit', assetId: top.id, name: top.name, bank: top.bank, url: top.url,
    amount: 300000, rate: top.rate, months: 12, cap: 'month', date: daysAgo(95),
  });
  if (!positions.length) return toast('Нет данных для демо-портфеля', true);
  S.portfolio = positions;
  savePortfolio();
  render();
  toast('Демо-портфель загружен');
}

function aiContext() {
  const v = valuation();
  const positions = v.rows.map((r) => ({
    name: r.name,
    type: r.kindLabel,
    value: Math.round(r.cur),
    cost: Math.round(r.cost),
    pnl: Math.round(r.pnl),
    sharePct: +(r.cur / (v.value || 1) * 100).toFixed(1),
  }));
  const crypto = cryptoList().slice(0, 6).map((c) => ({
    symbol: c.symbol, name: c.name, priceUsd: c.price, change24h: c.change24h,
  }));
  const metals = metalList().map((m) => ({
    code: m.code, name: m.name, rubPerGram: m.price, change24h: m.change24h,
  }));
  const fx = fxList().map((f) => ({
    code: f.code, name: f.name, rub: f.value, change24h: f.change24h,
  }));
  const seenBanks = new Set();
  const deposits = [...depositList()]
    .sort((a, b) => b.rate - a.rate)
    .filter((d) => { if (seenBanks.has(d.bank)) return false; seenBanks.add(d.bank); return true; })
    .slice(0, 8)
    .map((d) => ({
      bank: d.bank, name: d.name, rate: d.rate, min: d.min, max: d.max, termDays: d.termDays, currency: d.currency,
    }));
  const byTypeMap = {};
  for (const p of positions) byTypeMap[p.type] = (byTypeMap[p.type] || 0) + p.value;
  const byType = Object.entries(byTypeMap).map(([type, value]) => ({
    type, value: Math.round(value), sharePct: +(value / (v.value || 1) * 100).toFixed(1),
  }));
  const moscow = S.realty?.stats?.moscow;
  const russia = S.realty?.stats?.russia;
  const best = bestDeposit();
  return JSON.stringify({
    page: (location.hash || '#/').replace(/^#\/?/, '') || 'home',
    portfolio: {
      value: Math.round(v.value),
      invested: Math.round(v.invested),
      pnl: Math.round(v.pnl),
      pnlPct: Number.isFinite(v.pnlPct) ? +v.pnlPct.toFixed(1) : 0,
      changeDay: Math.round(v.changeDay),
      changePct: Number.isFinite(v.changePct) ? +v.changePct.toFixed(2) : 0,
      irrPct: v.irr == null ? null : +(v.irr * 100).toFixed(1),
      depositIncome: Math.round(v.depositIncome),
      byType,
      positions,
    },
    market: {
      keyRate: keyRateValue(),
      crypto,
      metals,
      fx,
      bestDeposit: best ? { bank: best.bank, rate: best.rate } : null,
    },
    deposits,
    realty: {
      moscow: moscow ? { avgPrice: moscow.avgPrice, avgM2: moscow.avgM2, count: moscow.count } : null,
      russia: russia ? { median: russia.median, avgM2: russia.avgM2, count: russia.count, cities: russia.cities } : null,
    },
  });
}

const aiLog = [];
let aiBusy = false;

function formatAi(text) {
  const lines = String(text ?? '').split(/\r?\n/);
  const inline = (s) => esc(s)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
  let html = '';
  let list = '';
  const closeList = () => { if (list) { html += `</${list}>`; list = ''; } };
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) { closeList(); continue; }
    if (/^[-—_]{3,}$/.test(line)) { closeList(); html += '<hr>'; continue; }
    const heading = line.match(/^#{1,3}\s+(.+)$/);
    if (heading) { closeList(); html += `<h4>${inline(heading[1])}</h4>`; continue; }
    const bullet = line.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      if (list !== 'ul') { closeList(); html += '<ul>'; list = 'ul'; }
      html += `<li>${inline(bullet[1])}</li>`;
      continue;
    }
    const numbered = line.match(/^\d+[.)]\s+(.+)$/);
    if (numbered) {
      if (list !== 'ol') { closeList(); html += '<ol>'; list = 'ol'; }
      html += `<li>${inline(numbered[1])}</li>`;
      continue;
    }
    closeList();
    html += `<p>${inline(line)}</p>`;
  }
  closeList();
  return html;
}

function renderAiLog() {
  const log = $('#ai-log');
  if (!log) return;
  log.innerHTML = aiLog.length
    ? aiLog.map((m) => {
      const cls = `ai-msg ai-msg--${m.role === 'user' ? 'user' : m.error ? 'error' : 'bot'}${m.typing ? ' ai-msg--typing' : ''}`;
      const body = m.role === 'user' || m.error ? esc(m.text) : formatAi(m.text);
      return `<div class="${cls}">${body}</div>`;
    }).join('')
    : '<div class="ai-msg ai-msg--bot">Привет! Разберу портфель, сравню вклады, посмотрю валюты, металлы и недвижимость, посчитаю доходность. Спросите или выберите подсказку.</div>';
  log.scrollTop = log.scrollHeight;
}

function openAi(show = true) {
  const panel = $('#ai-panel');
  const fab = $('#ai-fab');
  if (!panel || !fab) return;
  panel.hidden = !show;
  fab.setAttribute('aria-expanded', show ? 'true' : 'false');
  if (show) {
    renderAiLog();
    setTimeout(() => $('#ai-question')?.focus(), 30);
  }
}

function toggleAi() {
  const panel = $('#ai-panel');
  openAi(panel ? panel.hidden : true);
}

async function askAi() {
  const input = $('#ai-question');
  if (!input || aiBusy) return;
  const question = input.value.trim();
  if (!question) {
    input.focus();
    return;
  }
  openAi(true);
  const history = aiLog.filter((m) => !m.typing && !m.error).slice(-6).map(({ role, text }) => ({ role, text }));
  input.value = '';
  aiLog.push({ role: 'user', text: question });
  aiLog.push({ role: 'assistant', text: 'Нейросеть думает…', typing: true });
  aiBusy = true;
  const send = $('#ai-send');
  if (send) send.disabled = true;
  renderAiLog();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 60000);
  try {
    const res = await fetch('/api/ai', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      body: JSON.stringify({ question, context: aiContext(), history }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Нейросеть вернула ошибку ${res.status}`);
    aiLog.pop();
    aiLog.push({ role: 'assistant', text: data.answer });
  } catch (err) {
    aiLog.pop();
    const text = err.name === 'AbortError'
      ? 'Нейросеть не ответила вовремя. Попробуйте ещё раз.'
      : (err.message || 'Не удалось получить ответ.');
    aiLog.push({ role: 'assistant', text, error: true });
  } finally {
    clearTimeout(timer);
    aiBusy = false;
    if (send) send.disabled = false;
    renderAiLog();
    input.focus();
  }
}

/* ------------------------------------------------------------------ ai forecast */
function fmtForecast(value, unit) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  if (unit === 'USD') return `$${num(number, number < 1 ? 4 : 2)}`;
  if (unit === 'RUB') return money(number);
  return `${money(number)}/г`;
}

/* ------------------------------------------------------------------ interactive chart */
const chartState = {
  seq: 0, kind: '', id: '', name: '', symbol: '', unit: '',
  range: '1m', horizon: 30, points: [], forecast: null, showForecast: true,
  view: { start: 0, end: 0 }, hover: null, dragging: false, drag: null,
  historyLoading: false, historyError: '', forecastLoading: false, forecastError: '',
};
const chartHistoryCache = new Map();
const CHART_RANGE_LABELS = { '1d': '1Д', '7d': '7Д', '1m': '1М', '3m': '3М', '1y': '1Г', all: 'Всё' };

function preferredHorizon(range) {
  if (range === '1d' || range === '7d') return 7;
  if (range === '1m') return 30;
  return 90;
}

function chartLongDate(iso) {
  const date = new Date(iso);
  return isFinite(date) ? date.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short', year: 'numeric' }) : '—';
}

function chartLabelDate(iso, range) {
  const date = new Date(iso);
  if (!isFinite(date)) return '—';
  if (range === '1y' || range === 'all') {
    return date.toLocaleDateString('ru-RU', { month: 'short', year: '2-digit' });
  }
  return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
}

function chartAllPoints() {
  const history = chartState.points || [];
  if (!history.length) return [];
  const forecast = chartState.showForecast ? (chartState.forecast?.points || []) : [];
  if (!forecast.length) return history;
  const last = new Date(history[history.length - 1].t).getTime();
  const base = isFinite(last) ? last : Date.now();
  return history.concat(forecast.map((price, index) => ({
    t: new Date(base + (index + 1) * 86400000).toISOString(),
    c: Number(price),
    forecast: true,
  })));
}

function chartToolbarHtml() {
  const ranges = chartState.kind === 'crypto' ? ['1d', '7d', '1m', '3m', '1y', 'all'] : ['7d', '1m', '3m', '1y', 'all'];
  return `<div class="chart-toolbar">
    <div class="chart-ranges">${ranges.map((range) => `<button class="chart-tab${chartState.range === range ? ' is-active' : ''}" type="button" data-chart-range="${range}">${CHART_RANGE_LABELS[range]}</button>`).join('')}</div>
    <div class="chart-ai-controls"><label class="chart-toggle"><input id="chart-ai-toggle" type="checkbox"${chartState.showForecast ? ' checked' : ''}><span>AI-прогноз</span></label><span class="chart-horizon-note">${chartState.horizon} дн.</span></div>
  </div>`;
}

function renderChartLegend() {
  const box = $('#chart-legend');
  if (!box) return;
  let ai = '';
  if (!chartState.showForecast) ai = '<span>AI-прогноз выключен</span>';
  else if (chartState.forecastLoading) ai = '<span>AI-прогноз загружается…</span>';
  else if (chartState.forecastError) ai = '<span>AI-прогноз недоступен</span>';
  else if (chartState.forecast) ai = '<span><i class="legend-line legend-line--forecast"></i>базовый прогноз</span><span><i class="legend-band"></i>диапазон</span>';
  box.innerHTML = `<span><i class="legend-line"></i>история</span>${ai}<span>вертикальная линия — сегодня</span>`;
}

function renderChartToolbar() {
  const bar = $('#chart-toolbar');
  if (bar) bar.innerHTML = chartToolbarHtml();
  renderChartLegend();
}

function chartSvg(all) {
  const width = 920, height = 380, padL = 78, padR = 22, padT = 26, padB = 44;
  if (all.length < 2) return '<div class="chart-empty">Мало данных для графика</div>';
  const start = Math.max(0, Math.min(chartState.view.start, all.length - 2));
  const end = Math.max(start + 1, Math.min(chartState.view.end, all.length - 1));
  const visible = all.slice(start, end + 1);
  const band = chartState.forecast ? Math.max(0, Number(chartState.forecast.bandPct) || 0) / 100 : 0;
  const values = visible.map((point) => Number(point.c)).filter(Number.isFinite);
  if (band) {
    for (const point of visible) {
      if (point.forecast) values.push(Number(point.c) * (1 + band), Number(point.c) * (1 - band));
    }
  }
  if (!values.length) return '<div class="chart-empty">Нет данных</div>';
  let min = Math.min(...values), max = Math.max(...values);
  const pad = (max - min) * 0.08 || Math.abs(max) * 0.02 || 1;
  min -= pad; max += pad;
  const x = (index) => padL + ((index - start) / (end - start)) * (width - padL - padR);
  const y = (value) => padT + (1 - (value - min) / (max - min)) * (height - padT - padB);
  const indexed = visible.map((point, offset) => ({ point, index: start + offset }));
  const hist = indexed.filter((item) => !item.point.forecast && Number.isFinite(Number(item.point.c)));
  const fc = indexed.filter((item) => item.point.forecast && Number.isFinite(Number(item.point.c)));
  const boundary = chartState.points.length - 1;
  const boundaryVisible = boundary >= start && boundary <= end;
  const histPath = hist.map((item, index) => `${index ? 'L' : 'M'}${x(item.index).toFixed(1)} ${y(Number(item.point.c)).toFixed(1)}`).join(' ');
  const histArea = hist.length
    ? `${histPath} L ${x(hist[hist.length - 1].index).toFixed(1)} ${(height - padB).toFixed(1)} L ${x(hist[0].index).toFixed(1)} ${(height - padB).toFixed(1)} Z`
    : '';
  const forecastPoints = [];
  if (boundaryVisible && chartState.points[boundary]) {
    forecastPoints.push({ index: boundary, c: Number(chartState.points[boundary].c) });
  }
  for (const item of fc) forecastPoints.push({ index: item.index, c: Number(item.point.c) });
  const direction = chartState.forecast?.direction;
  const color = direction === 'down' ? '#e8564b' : direction === 'up' ? '#0fa97d' : '#1c284a';
  const fill = direction === 'down' ? '#fdeceb' : direction === 'up' ? '#e8faf5' : '#eef2f8';
  let forecastPath = '', bandPoly = '', forecastEdges = '';
  if (forecastPoints.length >= 2) {
    forecastPath = forecastPoints.map((item, index) => `${index ? 'L' : 'M'}${x(item.index).toFixed(1)} ${y(item.c).toFixed(1)}`).join(' ');
    if (band) {
      const top = forecastPoints.map((item) => [x(item.index), y(item.c * (1 + band))]);
      const bottom = [...forecastPoints].reverse().map((item) => [x(item.index), y(item.c * (1 - band))]);
      bandPoly = [...top, ...bottom].map((point) => `${point[0].toFixed(1)},${point[1].toFixed(1)}`).join(' ');
      const upperPath = forecastPoints.map((item, index) => `${index ? 'L' : 'M'}${x(item.index).toFixed(1)} ${y(item.c * (1 + band)).toFixed(1)}`).join(' ');
      const lowerPath = forecastPoints.map((item, index) => `${index ? 'L' : 'M'}${x(item.index).toFixed(1)} ${y(item.c * (1 - band)).toFixed(1)}`).join(' ');
      forecastEdges = `<path d="${upperPath}" fill="none" stroke="${color}" stroke-width="1.1" stroke-dasharray="2 4" opacity=".6"/><path d="${lowerPath}" fill="none" stroke="${color}" stroke-width="1.1" stroke-dasharray="2 4" opacity=".6"/>`;
    }
  }
  const grid = [0.25, 0.5, 0.75].map((part) => {
    const gy = padT + part * (height - padT - padB);
    return `<line x1="${padL}" y1="${gy.toFixed(1)}" x2="${width - padR}" y2="${gy.toFixed(1)}" stroke="#e7eef1"/>`;
  }).join('');
  let cross = '', tip = '';
  if (chartState.hover != null && chartState.hover >= start && chartState.hover <= end && all[chartState.hover]) {
    const hover = all[chartState.hover];
    const hx = x(chartState.hover);
    const hy = y(Number(hover.c));
    cross = `<line x1="${hx.toFixed(1)}" y1="${padT}" x2="${hx.toFixed(1)}" y2="${height - padB}" stroke="#9fb0c3" stroke-dasharray="3 4"/><circle cx="${hx.toFixed(1)}" cy="${hy.toFixed(1)}" r="3.5" fill="${hover.forecast ? color : '#40536a'}"/>`;
    tip = `<div class="chart-tip" style="left:${(hx / width * 100).toFixed(2)}%;top:8px">${esc(chartLongDate(hover.t))}<br>${esc(fmtForecast(hover.c, chartState.unit))} · ${hover.forecast ? 'прогноз' : 'история'}</div>`;
  }
  return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Интерактивный график ${esc(chartState.name)}">
    ${grid}
    ${histArea ? `<path d="${histArea}" fill="${fill}" opacity=".65"/>` : ''}
    ${histPath ? `<path d="${histPath}" fill="none" stroke="#40536a" stroke-width="2.1" stroke-linejoin="round" stroke-linecap="round"/>` : ''}
    ${bandPoly ? `<polygon points="${bandPoly}" fill="${color}" opacity=".14"/>` : ''}
    ${forecastEdges}
    ${forecastPath ? `<path d="${forecastPath}" fill="none" stroke="${color}" stroke-width="2.5" stroke-dasharray="7 5" stroke-linejoin="round" stroke-linecap="round"/>` : ''}
    ${boundaryVisible ? `<line x1="${x(boundary)}" y1="${padT}" x2="${x(boundary)}" y2="${height - padB}" stroke="#cfd8e3" stroke-dasharray="3 4"/>` : ''}
    ${cross}
    <text x="${padL - 8}" y="${padT}" text-anchor="end" class="chart-label">${esc(fmtForecast(max, chartState.unit))}</text>
    <text x="${padL - 8}" y="${height - padB}" text-anchor="end" class="chart-label">${esc(fmtForecast(min, chartState.unit))}</text>
    <text x="${padL}" y="${height - 12}" class="chart-label">${esc(chartLabelDate(all[start].t, chartState.range))}</text>
    <text x="${(padL + width - padR) / 2}" y="${height - 12}" text-anchor="middle" class="chart-label">${esc(chartLabelDate(all[Math.floor((start + end) / 2)].t, chartState.range))}</text>
    <text x="${width - padR}" y="${height - 12}" text-anchor="end" class="chart-label">${esc(chartLabelDate(all[end].t, chartState.range))}</text>
    ${chartState.showForecast && chartState.forecast ? `<text x="${width - padR}" y="${padT - 8}" text-anchor="end" class="chart-end">AI-прогноз ${chartState.forecast.horizonDays} дн.</text>` : ''}
  </svg>${tip}`;
}

function renderChartStage() {
  const stage = $('#chart-stage');
  if (!stage) return;
  if (chartState.historyLoading) {
    stage.innerHTML = '<div class="chart-loading"><span class="loader"></span>Загружаем историю…</div>';
    return;
  }
  if (chartState.historyError) {
    stage.innerHTML = `<div class="chart-error">${icon('shield')}<span>${esc(chartState.historyError)}</span></div>`;
    return;
  }
  const points = chartAllPoints();
  stage.innerHTML = points.length ? chartSvg(points) : '<div class="chart-empty">Нет данных для графика</div>';
}

function updateChartSub() {
  const sub = $('#forecast-sub');
  if (!sub) return;
  const last = chartState.points[chartState.points.length - 1];
  const label = CHART_RANGE_LABELS[chartState.range] || chartState.range;
  const ai = !chartState.showForecast ? 'AI выкл.' : chartState.forecastLoading ? 'AI загрузка…' : chartState.forecastError ? 'AI недоступен' : `AI ${chartState.horizon} дн.`;
  sub.textContent = last
    ? `${label} · ${fmtForecast(last.c, chartState.unit)} · ${chartState.points.length} точек · ${ai}`
    : 'Загружаем историю…';
}

function bindChartEvents() {
  const stage = $('#chart-stage');
  if (!stage) return;
  stage.addEventListener('wheel', (event) => {
    event.preventDefault();
    const all = chartAllPoints();
    if (all.length < 3) return;
    const rect = stage.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    const start = Math.max(0, Math.min(chartState.view.start, all.length - 2));
    const end = Math.max(start + 1, Math.min(chartState.view.end, all.length - 1));
    const span = end - start;
    const minSpan = Math.min(10, all.length - 1);
    const nextSpan = Math.max(minSpan, Math.min(all.length - 1, Math.round(span * (event.deltaY > 0 ? 1.2 : 0.8))));
    const anchor = start + ratio * span;
    let nextStart = Math.round(anchor - ratio * nextSpan);
    nextStart = Math.max(0, Math.min(all.length - 1 - nextSpan, nextStart));
    chartState.view = { start: nextStart, end: nextStart + nextSpan };
    renderChartStage();
  }, { passive: false });
  stage.addEventListener('mousedown', (event) => {
    if (event.button !== 0) return;
    const all = chartAllPoints();
    if (all.length < 2) return;
    chartState.dragging = true;
    chartState.drag = { x: event.clientX, start: chartState.view.start, end: chartState.view.end };
    stage.style.cursor = 'grabbing';
    const onMove = (moveEvent) => {
      if (!chartState.dragging || !chartState.drag) return;
      const rect = stage.getBoundingClientRect();
      const span = chartState.drag.end - chartState.drag.start;
      const shift = Math.round(-(moveEvent.clientX - chartState.drag.x) / rect.width * span);
      const maxStart = Math.max(0, all.length - 1 - span);
      const nextStart = Math.max(0, Math.min(maxStart, chartState.drag.start + shift));
      chartState.view = { start: nextStart, end: nextStart + span };
      renderChartStage();
    };
    const onUp = () => {
      chartState.dragging = false;
      chartState.drag = null;
      stage.style.cursor = 'crosshair';
      window.removeEventListener('mousemove', onMove);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp, { once: true });
  });
  stage.addEventListener('mousemove', (event) => {
    if (chartState.dragging) return;
    const all = chartAllPoints();
    const rect = stage.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    const start = Math.max(0, Math.min(chartState.view.start, all.length - 2));
    const end = Math.max(start + 1, Math.min(chartState.view.end, all.length - 1));
    const index = Math.round(start + ratio * (end - start));
    if (index !== chartState.hover) {
      chartState.hover = index;
      renderChartStage();
    }
  });
  stage.addEventListener('mouseleave', () => {
    if (chartState.dragging) return;
    if (chartState.hover != null) {
      chartState.hover = null;
      renderChartStage();
    }
  });
}

async function loadChartHistory() {
  const seq = chartState.seq;
  chartState.historyLoading = true;
  chartState.historyError = '';
  renderChartToolbar();
  renderChartStage();
  updateChartSub();
  const key = `${chartState.kind}:${chartState.id}:${chartState.range}`;
  try {
    let data = chartHistoryCache.get(key);
    if (!data) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 30000);
      try {
        const res = await fetch(`/api/history?kind=${encodeURIComponent(chartState.kind)}&id=${encodeURIComponent(chartState.id)}&range=${encodeURIComponent(chartState.range)}`, { signal: controller.signal });
        const payload = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(payload.error || `Ошибка ${res.status}`);
        data = payload;
      } finally {
        clearTimeout(timer);
      }
      chartHistoryCache.set(key, data);
    }
    if (seq !== chartState.seq) return;
    if (!data.points || !data.points.length) throw new Error('Нет данных по истории');
    chartState.points = data.points;
    chartState.unit = data.unit || chartState.unit;
    chartState.name = data.name || chartState.name;
    chartState.symbol = data.symbol || chartState.symbol;
    chartState.view = { start: 0, end: Math.max(1, chartState.points.length - 1) };
    chartState.historyLoading = false;
    if (chartState.forecast) chartState.view = { start: 0, end: chartAllPoints().length - 1 };
    renderChartToolbar();
    renderChartStage();
      updateChartSub();
  } catch (err) {
    if (seq !== chartState.seq) return;
    chartState.historyLoading = false;
    chartState.historyError = err.name === 'AbortError' ? 'История не загрузилась вовремя.' : (err.message || 'Не удалось загрузить историю.');
    renderChartStage();
      updateChartSub();
  }
}

async function loadChartForecast() {
  const seq = chartState.seq;
  chartState.forecastLoading = true;
  chartState.forecastError = '';
  chartState.forecast = null;
  renderChartToolbar();
  renderChartStage();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 90000);
  try {
    const res = await fetch('/api/forecast', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      body: JSON.stringify({ kind: chartState.kind, id: chartState.id, horizon: chartState.horizon }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Ошибка ${res.status}`);
    if (seq !== chartState.seq) return;
    const atEnd = !chartState.points.length || chartState.view.end >= chartState.points.length - 1;
    chartState.forecast = data;
    chartState.forecastLoading = false;
    if (atEnd) chartState.view = { start: 0, end: chartAllPoints().length - 1 };
    renderChartToolbar();
    renderChartStage();
      updateChartSub();
  } catch (err) {
    if (seq !== chartState.seq) return;
    chartState.forecastLoading = false;
    chartState.forecastError = err.name === 'AbortError' ? 'AI-анализ не ответил вовремя.' : (err.message || 'Не удалось получить AI-анализ.');
    renderChartStage();
    } finally {
    clearTimeout(timer);
  }
}

async function openChart(kind, id) {
  const dialog = $('#forecast-dialog');
  const body = $('#forecast-body');
  const title = $('#forecast-title');
  const sub = $('#forecast-sub');
  if (!dialog || !body) return;
  const asset = kind === 'crypto' ? findCrypto(id) : kind === 'metal' ? findMetal(id) : findFx(id);
  if (!asset) { toast('Актив не найден', true); return; }
  chartState.seq += 1;
  chartState.kind = kind;
  chartState.id = id;
  chartState.name = asset.name || id;
  chartState.symbol = asset.symbol || asset.code || id;
  chartState.unit = kind === 'crypto' ? 'USD' : kind === 'metal' ? 'RUB/g' : 'RUB';
  chartState.range = '1m';
  chartState.horizon = preferredHorizon('1m');
  chartState.points = [];
  chartState.forecast = null;
  chartState.showForecast = true;
  chartState.view = { start: 0, end: 0 };
  chartState.hover = null;
  chartState.historyLoading = true;
  chartState.historyError = '';
  chartState.forecastLoading = true;
  chartState.forecastError = '';
  if (title) title.textContent = `График · ${asset.name}`;
  if (sub) sub.textContent = 'Загружаем историю…';
  body.innerHTML = '<div id="chart-toolbar"></div><div id="chart-stage" class="chart-stage"><div class="chart-loading"><span class="loader"></span>Загружаем историю…</div></div><div id="chart-legend" class="chart-legend"></div><div class="chart-hint">Колесо — зум · перетаскивание — сдвиг · пунктир — сценарий</div>';
  if (!dialog.open) dialog.showModal();
  bindChartEvents();
  renderChartToolbar();
  await Promise.allSettled([loadChartHistory(), loadChartForecast()]);
}

/* ------------------------------------------------------------------ events */
function onRoute() {
  render();
  window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
}

document.addEventListener('click', (e) => {
  const nav = e.target.closest('[data-nav]');
  if (nav) document.body.classList.remove('menu-open');

  const cityBtn = e.target.closest('#re-city-btn');
  if (cityBtn) {
    const pop = $('#re-city-pop');
    if (pop) {
      pop.hidden = !pop.hidden;
      cityBtn.setAttribute('aria-expanded', pop.hidden ? 'false' : 'true');
      if (!pop.hidden) {
        const q = $('#re-city-q');
        if (q) { q.value = ''; filterCityOptions(''); q.focus(); }
      }
    }
    return;
  }
  const cityOption = e.target.closest('[data-city-option]');
  if (cityOption) { setRealtyCity(cityOption.dataset.cityOption); return; }
  if (!e.target.closest('#re-city-select')) closeCityPicker();

  const go = e.target.closest('[data-go]');
  if (go && !e.target.closest('a,button')) { location.hash = go.dataset.go; return; }

  const addCrypto = e.target.closest('[data-add-crypto]');
  if (addCrypto) { openAdd('crypto', { assetId: addCrypto.dataset.addCrypto }); return; }
  const addMetal = e.target.closest('[data-add-metal]');
  if (addMetal) { openAdd('metal', { assetId: addMetal.dataset.addMetal }); return; }
  const addFx = e.target.closest('[data-add-fx]');
  if (addFx) { openAdd('fx', { assetId: addFx.dataset.addFx }); return; }
  const addDep = e.target.closest('[data-add-deposit]');
  if (addDep) {
    if ($('#deposit-dialog')?.open) $('#deposit-dialog').close();
    const offer = depositList().find((d) => d.id === addDep.dataset.addDeposit);
    openAdd('deposit', offer ? { offerId: offer.id, rate: offer.rate, name: offer.name, amount: S.calc?.amount || 300000, months: S.calc?.months || 12 } : {});
    return;
  }
  const depositCard = e.target.closest('[data-deposit]');
  if (depositCard) {
    openDeposit(depositCard.dataset.deposit);
    return;
  }
  const realtyPhoto = e.target.closest('[data-realty-photo]');
  if (realtyPhoto) {
    realtyGallery.index = Number(realtyPhoto.dataset.realtyPhoto) || 0;
    renderRealtyGallery();
    return;
  }
  const realtyCard = e.target.closest('[data-realty]');
  if (realtyCard) {
    if (e.target.closest('a')) return;
    openRealty(realtyCard.dataset.realty);
    return;
  }
  const chartTrigger = e.target.closest('[data-chart], [data-forecast]');
  if (chartTrigger) {
    const inner = e.target.closest('a,button');
    if (inner && inner !== chartTrigger && !inner.matches('[data-chart], [data-forecast]')) return;
    const [kind, id] = (chartTrigger.dataset.chart || chartTrigger.dataset.forecast || '').split(':');
    if (kind && id) openChart(kind, id);
    return;
  }
  const rangeTrigger = e.target.closest('[data-chart-range]');
  if (rangeTrigger) {
    const nextHorizon = preferredHorizon(rangeTrigger.dataset.chartRange);
    const needsForecast = nextHorizon !== chartState.horizon || !chartState.forecast;
    chartState.range = rangeTrigger.dataset.chartRange;
    chartState.horizon = nextHorizon;
    if (needsForecast) {
      chartState.forecast = null;
      loadChartForecast();
    }
    loadChartHistory();
    return;
  }
  const chartRetry = e.target.closest('[data-chart-retry]');
  if (chartRetry) {
    loadChartForecast();
    return;
  }
  const del = e.target.closest('[data-del]');
  if (del) {
    S.portfolio = S.portfolio.filter((p) => p.id !== del.dataset.del);
    savePortfolio();
    render();
    toast('Позиция удалена');
    return;
  }
  const seg = e.target.closest('#kind-seg .seg-btn');
  if (seg) {
    S.addKind = seg.dataset.kind;
    S.addPreset = {};
    renderAddFields();
    $('#form-error').textContent = '';
    return;
  }
  const aiPreset = e.target.closest('[data-ai]');
  if (aiPreset) {
    const input = $('#ai-question');
    if (input) input.value = aiPreset.dataset.ai;
    askAi();
    return;
  }

  const action = e.target.closest('[data-action]')?.dataset.action;
  if (!action) return;
  if (action === 'menu') document.body.classList.toggle('menu-open');
  else if (action === 'profile') openProfileDialog();
  else if (action === 'close-profile') $('#profile-dialog').close();
  else if (action === 'close-forecast') $('#forecast-dialog').close();
  else if (action === 'close-realty') $('#realty-dialog').close();
  else if (action === 'close-deposit') $('#deposit-dialog').close();
  else if (action === 'profile-new') createProfile();
  else if (action === 'profile-delete') deleteProfile();
  else if (action === 'refresh') refresh();
  else if (action === 'ai-open') openAi(true);
  else if (action === 'ai-toggle') toggleAi();
  else if (action === 'ai-close') openAi(false);
  else if (action === 'bell') toast('Уведомлений пока нет — всё под контролем');
  else if (action === 'open-add') openAdd('crypto');
  else if (action === 'close-dialog') $('#add-dialog').close();
  else if (action === 'demo') addDemo();
  else if (action === 'clear') {
    if (S.portfolio.length && confirm('Удалить все позиции портфеля?')) {
      S.portfolio = [];
      savePortfolio();
      render();
      toast('Портфель очищен');
    }
  } else if (action === 'calc-add') {
    ensureCalc();
    const c = S.calc || {};
    openAdd('deposit', { amount: c.amount, rate: c.rate, months: c.months, cap: c.cap });
  } else if (action === 'dep-more') {
    S.dep.limit += 40;
    const box = $('#dep-list');
    if (box) box.innerHTML = depositRowsHtml();
  } else if (action === 're-more') {
    S.re.limit += 24;
    const box = $('#re-list');
    if (box) box.innerHTML = realtyRowsHtml();
  }
});

document.addEventListener('change', (e) => {
  if (e.target.id === 'profile-select') switchProfile(e.target.value);
  if (e.target.id === 'f-asset') {
    const isCrypto = S.addKind === 'crypto';
    const isFx = S.addKind === 'fx';
    const list = isCrypto ? cryptoList() : isFx ? fxList() : metalList();
    const item = list.find((a) => (isFx ? a.code : a.id) === e.target.value);
    if (item) $('#f-buy').value = (isCrypto ? rub(item.price) : isFx ? item.value : item.price).toFixed(2);
  }
  if (e.target.id === 'f-offer') {
    const offer = depositList().find((d) => d.id === e.target.value);
    if (offer) {
      $('#f-rate').value = offer.rate;
      $('#f-name').value = offer.name;
    }
  }
  if (e.target.id === 're-rooms') { S.re.rooms = e.target.value; S.re.limit = 24; $('#re-list').innerHTML = realtyRowsHtml(); }
  if (e.target.id === 're-source') { S.re.source = e.target.value; S.re.limit = 24; $('#re-list').innerHTML = realtyRowsHtml(); }
  if (e.target.id === 're-sort') { S.re.sort = e.target.value; S.re.limit = 24; $('#re-list').innerHTML = realtyRowsHtml(); }
});

document.addEventListener('input', (e) => {
  if (e.target.id === 'dep-amount' || e.target.id === 'dep-months') updateDepositView();
  if (e.target.id === 're-search') {
    S.re.q = e.target.value;
    S.re.limit = 24;
    $('#re-list').innerHTML = realtyRowsHtml();
  }
  if (e.target.id === 're-city-q') filterCityOptions(e.target.value);
});

$('#search-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const q = $('#search-input').value.trim();
  location.hash = q ? `#/search?q=${encodeURIComponent(q)}` : '#/';
});

$('#add-form').addEventListener('submit', handleSubmit);
$('#profile-form').addEventListener('submit', saveProfileName);
$('#ai-form').addEventListener('submit', (e) => { e.preventDefault(); askAi(); });
$('#add-dialog').addEventListener('close', () => { $('#form-error').textContent = ''; });
$('#realty-dialog').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) e.currentTarget.close();
});
$('#deposit-dialog').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) e.currentTarget.close();
});
document.addEventListener('change', (e) => {
  if (e.target.id !== 'chart-ai-toggle') return;
  chartState.showForecast = e.target.checked;
  const all = chartAllPoints();
  chartState.view = { start: 0, end: Math.max(1, all.length - 1) };
  renderChartToolbar();
  renderChartStage();
  updateChartSub();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.body.classList.remove('menu-open');
    closeCityPicker();
    openAi(false);
  }
  if (e.key !== 'Enter' && e.key !== ' ') return;
  const card = e.target.closest('[data-deposit][role="button"], [data-realty][role="button"], [data-go][role="link"]');
  if (card && e.target === card) {
    e.preventDefault();
    card.click();
  }
});
window.addEventListener('hashchange', onRoute);

/* ------------------------------------------------------------------ boot */
(async function boot() {
  render();
  renderAiLog();
  await refresh({ silent: true });
  setInterval(() => refresh({ silent: true, marketOnly: true }), 3600000);
})();
