'use strict';

let papers = [];
let keywords = [];
let decisions = {};
let excludedSessions = new Set();
let queue = [];
let undoStack = [];
let showDetails = false;
let view = 'swipe';
let animating = false;
let loaded = false;

const $ = id => document.getElementById(id);

async function init() {
  try {
    const [pRes, sRes] = await Promise.all([fetch('/api/papers'), fetch('/api/state')]);
    if (!pRes.ok || !sRes.ok) throw new Error('bad response');
    papers = await pRes.json();
    const state = await sRes.json();
    keywords = state.keywords;
    decisions = state.decisions;
    excludedSessions = new Set(state.excludedSessions || []);
    loaded = true;
  } catch (err) {
    const card = document.createElement('div');
    card.className = 'card done';
    const h = document.createElement('h2');
    h.textContent = 'Could not load papers';
    const msg = document.createElement('p');
    msg.textContent = 'Check that papers.json exists (run: python3 prepare_data.py) and that the server is running, then reload.';
    card.append(h, msg);
    $('card-area').replaceChildren(card);
    return;
  }
  rebuildQueue();
  renderSessions();
  renderKeywords();
  renderCard();
  renderProgress();
}

function saveState() {
  if (!loaded) return;
  fetch('/api/state', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({keywords, decisions, excludedSessions: [...excludedSessions]}),
  }).then(r => {
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
  }).catch(() => {
    $('kw-hint').textContent = '⚠ Could not save progress — is the server running?';
  });
}

function rebuildQueue() {
  queue = papers.filter(p => !(p.id in decisions) && !excludedSessions.has(sessionTheme(p)));
}

function sessionTheme(p) {
  // "Oral Session B: Resources and Evaluation 2" -> "Resources and Evaluation"
  // "Poster Session C" stays as-is (posters have no theme; each letter is one slot)
  const n = p.sessionName || p.session || 'Unknown session';
  const m = n.match(/^Orals?\s+Session\s+\w+:\s*(.+?)\s*\d*$/i);
  return m ? m[1] : (n.replace(/\s*\d+$/, '') || 'Unknown session');
}

function renderSessions() {
  const list = $('session-list');
  const groups = new Map();  // theme -> {count, slots: Set("date · time")}
  for (const p of papers) {
    const theme = sessionTheme(p);
    if (!groups.has(theme)) groups.set(theme, {count: 0, slots: new Set()});
    const g = groups.get(theme);
    g.count++;
    g.slots.add(`${p.date} ${p.time}`);
  }
  const posters = [...groups.keys()].filter(t => /^poster/i.test(t)).sort();
  const others = [...groups.keys()].filter(t => !/^poster/i.test(t)).sort();
  list.replaceChildren();
  for (const theme of [...posters, ...others]) {
    const g = groups.get(theme);
    const label = document.createElement('label');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = !excludedSessions.has(theme);
    cb.onchange = e => {
      if (e.target.checked) excludedSessions.delete(theme);
      else excludedSessions.add(theme);
      e.target.blur();
      afterMutation();
    };
    const span = document.createElement('span');
    span.textContent = theme;
    if (g.slots.size === 1) {
      const slot = document.createElement('span');
      slot.className = 'slot';
      slot.textContent = ` ${[...g.slots][0]}`;
      span.append(slot);
    }
    const count = document.createElement('span');
    count.className = 'count';
    count.textContent = g.count;
    label.append(cb, span, count);
    list.append(label);
  }
}

function keywordRegex(kw) {
  const prefix = kw.endsWith('*');  // "biolog*" matches biology, biological, ...
  const base = prefix ? kw.slice(0, -1) : kw;
  const esc = base.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`(^|[^A-Za-z0-9])${esc}` + (prefix ? '' : '([^A-Za-z0-9]|$)'), 'i');
}

function matchesAny(title, kws) {
  return kws.some(kw => keywordRegex(kw).test(title));
}

function addKeyword(raw) {
  if (!loaded) return;
  const kw = raw.trim().toLowerCase();
  if (!kw.replace(/\*/g, '') || keywords.includes(kw)) return;
  keywords.push(kw);
  let n = 0;
  for (const p of papers) {
    if (!(p.id in decisions) && keywordRegex(kw).test(p.title)) {
      decisions[p.id] = 'filtered';
      n++;
    }
  }
  $('kw-hint').textContent = `"${kw}" filtered out ${n} papers`;
  afterMutation();
}

function removeKeyword(kw) {
  keywords = keywords.filter(k => k !== kw);
  let n = 0;
  for (const p of papers) {
    if (decisions[p.id] === 'filtered' && !matchesAny(p.title, keywords)) {
      delete decisions[p.id];
      n++;
    }
  }
  $('kw-hint').textContent = `removed "${kw}", ${n} papers back in the deck`;
  afterMutation();
}

function afterMutation() {
  rebuildQueue();
  saveState();
  renderKeywords();
  renderCard();
  renderProgress();
  if (view === 'schedule') renderSchedule();
}

function decide(action) {  // 'like' | 'skip'
  const p = queue[0];
  if (!p || animating) return;
  animating = true;
  decisions[p.id] = action;
  undoStack.push({id: p.id});
  const card = document.getElementById('card');
  if (card) card.classList.add(action === 'like' ? 'out-right' : 'out-left');
  setTimeout(() => {
    animating = false;
    queue.shift();
    saveState();
    renderCard();
    renderProgress();
  }, 180);
}

function undo() {
  if (animating) return;
  const last = undoStack.pop();
  if (!last) return;
  if (last.prev === undefined) delete decisions[last.id];
  else decisions[last.id] = last.prev;
  afterMutation();
}

function toggleDetails() {
  showDetails = !showDetails;
  renderCard();
}

function renderCard() {
  const area = $('card-area');
  const p = queue[0];
  if (!p) {
    const liked = papers.filter(x => decisions[x.id] === 'like').length;
    const done = document.createElement('div');
    done.className = 'card done';
    const h = document.createElement('h2');
    h.textContent = 'All done 🎉';
    const msg = document.createElement('p');
    msg.textContent = `You liked ${liked} papers. Check the Schedule tab.`;
    done.append(h, msg);
    area.replaceChildren(done);
    return;
  }
  const card = document.createElement('div');
  card.className = 'card';
  card.id = 'card';
  const chip = document.createElement('div');
  chip.className = 'chip';
  chip.textContent = `${p.date} · ${p.time}` + (p.sessionName ? ` · ${p.sessionName}` : '');
  const title = document.createElement('h2');
  title.textContent = p.title;
  card.append(chip, title);
  if (showDetails) {
    const det = document.createElement('div');
    det.className = 'details';
    const auth = document.createElement('p');
    auth.className = 'authors';
    auth.textContent = p.authors;
    const abs = document.createElement('p');
    abs.textContent = p.abstract;
    det.append(auth, abs);
    card.append(det);
  }
  area.replaceChildren(card);
}

function renderProgress() {
  let done = 0, total = 0, liked = 0;
  for (const p of papers) {
    const d = decisions[p.id];
    if (d === 'like') liked++;
    if (d === 'filtered' || excludedSessions.has(sessionTheme(p))) continue;
    total++;
    if (d === 'like' || d === 'skip') done++;
  }
  $('progress').textContent = `${done.toLocaleString()} / ${total.toLocaleString()}`;
  $('liked-count').textContent = liked;
}

function renderKeywords() {
  const ul = $('kw-list');
  ul.replaceChildren();
  for (const kw of keywords) {
    const li = document.createElement('li');
    const span = document.createElement('span');
    span.textContent = kw;
    const btn = document.createElement('button');
    btn.textContent = '✕';
    btn.title = 'remove keyword';
    btn.onclick = () => removeKeyword(kw);
    li.append(span, btn);
    ul.append(li);
  }
}

function renderSchedule() {
  const container = $('schedule');
  const liked = papers.filter(p => decisions[p.id] === 'like');
  container.replaceChildren();
  if (!liked.length) {
    const p = document.createElement('p');
    p.className = 'hint';
    p.textContent = 'No liked papers yet — go swipe!';
    container.append(p);
    return;
  }
  const groups = new Map();
  for (const p of liked) {
    const name = p.sessionName || p.session || 'Unknown session';
    const key = `${p.start || '9999-' + p.date}|${p.time}|${name}`;
    if (!groups.has(key)) groups.set(key, {p0: p, name, papers: []});
    groups.get(key).papers.push(p);
  }
  const sorted = [...groups.values()].sort((a, b) =>
    `${a.p0.start || '9999-' + a.p0.date}|${a.p0.time}`.localeCompare(
      `${b.p0.start || '9999-' + b.p0.date}|${b.p0.time}`));
  for (const g of sorted) {
    const sec = document.createElement('section');
    sec.className = 'session';
    const h = document.createElement('h3');
    h.textContent = `${g.p0.date} · ${g.p0.time} — ${g.name}`;
    sec.append(h);
    if (!g.p0.start) {
      const warn = document.createElement('p');
      warn.className = 'warn';
      warn.textContent = '⚠ Unrecognized session time — not included in the .ics export';
      sec.append(warn);
    }
    const ul = document.createElement('ul');
    for (const p of g.papers) {
      const li = document.createElement('li');
      const btn = document.createElement('button');
      btn.textContent = '✕';
      btn.title = 'remove from schedule';
      btn.onclick = () => {
        undoStack.push({id: p.id, prev: 'like'});
        decisions[p.id] = 'skip';
        saveState();
        renderSchedule();
        renderProgress();
      };
      const span = document.createElement('span');
      span.textContent = `${p.title} — ${p.room} (${p.id})`;
      li.append(btn, span);
      ul.append(li);
    }
    sec.append(ul);
    container.append(sec);
  }
}

function showView(v) {
  view = v;
  $('swipe-view').hidden = v !== 'swipe';
  $('schedule-view').hidden = v !== 'schedule';
  $('tab-swipe').classList.toggle('active', v === 'swipe');
  $('tab-schedule').classList.toggle('active', v === 'schedule');
  if (v === 'schedule') renderSchedule();
}

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'BUTTON') return;
  if (e.key === 'z' || e.key === 'Z') { undo(); return; }
  if (view !== 'swipe') return;
  if (e.key === 'ArrowRight') decide('like');
  else if (e.key === 'ArrowLeft') decide('skip');
  else if (e.key === ' ') { e.preventDefault(); toggleDetails(); }
});

$('kw-form').addEventListener('submit', e => {
  e.preventDefault();
  addKeyword($('kw-input').value);
  $('kw-input').value = '';
});
$('btn-like').onclick = e => { decide('like'); e.currentTarget.blur(); };
$('btn-skip').onclick = e => { decide('skip'); e.currentTarget.blur(); };
$('btn-undo').onclick = e => { undo(); e.currentTarget.blur(); };
$('btn-details').onclick = e => { toggleDetails(); e.currentTarget.blur(); };
$('tab-swipe').onclick = () => showView('swipe');
$('tab-schedule').onclick = () => showView('schedule');

init();
