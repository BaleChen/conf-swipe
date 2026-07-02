'use strict';

let papers = [];
let keywords = [];
let decisions = {};
let queue = [];
let undoStack = [];
let showDetails = false;
let view = 'swipe';
let animating = false;

const $ = id => document.getElementById(id);

async function init() {
  const [pRes, sRes] = await Promise.all([fetch('/api/papers'), fetch('/api/state')]);
  papers = await pRes.json();
  const state = await sRes.json();
  keywords = state.keywords;
  decisions = state.decisions;
  rebuildQueue();
  renderKeywords();
  renderCard();
  renderProgress();
}

function saveState() {
  fetch('/api/state', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({keywords, decisions}),
  });
}

function rebuildQueue() {
  queue = papers.filter(p => !(p.id in decisions));
}

function keywordRegex(kw) {
  const esc = kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`(^|[^A-Za-z0-9])${esc}([^A-Za-z0-9]|$)`, 'i');
}

function matchesAny(title, kws) {
  return kws.some(kw => keywordRegex(kw).test(title));
}

function addKeyword(raw) {
  const kw = raw.trim().toLowerCase();
  if (!kw || keywords.includes(kw)) return;
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
  undoStack.push(p.id);
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
  const id = undoStack.pop();
  if (!id) return;
  delete decisions[id];
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
    area.innerHTML = `<div class="card done"><h2>All done 🎉</h2>
      <p>You liked ${liked} papers. Check the Schedule tab.</p></div>`;
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
    if (d === 'filtered') continue;
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
    const key = `${p.start || '9999'}|${p.time}|${name}`;
    if (!groups.has(key)) groups.set(key, {p0: p, name, papers: []});
    groups.get(key).papers.push(p);
  }
  const sorted = [...groups.values()].sort((a, b) =>
    `${a.p0.start || '9999'}|${a.p0.time}`.localeCompare(`${b.p0.start || '9999'}|${b.p0.time}`));
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
        decisions[p.id] = 'skip';
        undoStack.push(p.id);
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
  if (e.target.tagName === 'INPUT') return;
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
$('btn-like').onclick = () => decide('like');
$('btn-skip').onclick = () => decide('skip');
$('btn-details').onclick = toggleDetails;
$('tab-swipe').onclick = () => showView('swipe');
$('tab-schedule').onclick = () => showView('schedule');

init();
