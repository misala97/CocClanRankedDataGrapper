// Barcode Scanner: camera or typed number -> /barcode/api/<code> -> card.
//
// Scanning uses the browser's own BarcodeDetector where it reads EAN-13
// (Chrome on Android). Everywhere else -- iPhone, desktop -- the same API
// comes from the zxing-wasm polyfill, fetched only when it is needed.
//
// Upstream data reaches the page as text nodes and checked attributes only:
// el() never parses markup.

const POLYFILL = 'https://cdn.jsdelivr.net/npm/barcode-detector@3.2.2/dist/es/ponyfill.min.js';
const FORMATS = ['ean_13', 'ean_8', 'upc_a'];
const SCAN_INTERVAL_MS = 120;
const RECENT_KEY = 'barcode.recent';
const RECENT_MAX = 10;

const $ = (id) => document.getElementById(id);
const video = $('cam');
const startButton = $('start');
const torchButton = $('torch');
const statusLine = $('status');
const form = $('manual');
const input = $('code');
const result = $('result');
const recentSection = $('recent-section');
const recentList = $('recent');

let stream = null;
let detector = null;
let scanning = false;
let pending = null; // the code whose answer the card is waiting for

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const setStatus = (text) => { statusLine.textContent = text; };

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : String(child));
  }
  return node;
}

// ---- codes (the server checks again; this only saves a round trip) -----------

function checksumOk(code) {
  const digits = [...code].map(Number);
  const check = digits.pop();
  const total = digits.reverse().reduce((sum, d, i) => sum + d * (i % 2 === 0 ? 3 : 1), 0);
  return (10 - (total % 10)) % 10 === check;
}

function normalize(raw) {
  const code = String(raw ?? '').replace(/[\s-]/g, '');
  if (!/^(\d{8}|\d{12}|\d{13})$/.test(code) || !checksumOk(code)) return null;
  return code.length === 12 ? `0${code}` : code;
}

// ---- camera ----------------------------------------------------------------------

async function getDetector() {
  if (detector) return detector;
  if ('BarcodeDetector' in window) {
    try {
      const supported = await window.BarcodeDetector.getSupportedFormats();
      if (supported.includes('ean_13')) {
        detector = new window.BarcodeDetector({ formats: FORMATS.filter((f) => supported.includes(f)) });
        return detector;
      }
    } catch { /* fall through to the polyfill */ }
  }
  setStatus('Scanner wird geladen …');
  const { BarcodeDetector } = await import(POLYFILL);
  detector = new BarcodeDetector({ formats: FORMATS });
  return detector;
}

function cameraError(error) {
  switch (error?.name) {
    case 'NotAllowedError':
      return 'Kamerazugriff verweigert – in den Browser-Einstellungen erlauben oder Nummer eintippen.';
    case 'NotFoundError':
    case 'OverconstrainedError':
      return 'Keine Kamera gefunden – Nummer unten eintippen.';
    case 'NotReadableError':
      return 'Kamera ist gerade belegt – andere App schließen und nochmal versuchen.';
    default:
      return 'Scanner konnte nicht starten – Nummer unten eintippen.';
  }
}

async function startCamera() {
  if (scanning || startButton.disabled) return;
  if (!navigator.mediaDevices?.getUserMedia) {
    setStatus(window.isSecureContext
      ? 'Keine Kamera verfügbar – Nummer unten eintippen.'
      : 'Die Kamera braucht HTTPS – Nummer unten eintippen.');
    return;
  }
  startButton.disabled = true;
  try {
    const scanner = await getDetector();
    stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } },
    });
    video.srcObject = stream;
    await video.play();
    document.body.classList.add('is-live');
    setStatus('Barcode in den Rahmen halten.');
    offerTorch();
    scanning = true;
    scanLoop(scanner);
  } catch (error) {
    stopCamera();
    setStatus(cameraError(error));
  } finally {
    startButton.disabled = false;
  }
}

function stopCamera() {
  scanning = false;
  for (const track of stream?.getTracks() ?? []) track.stop();
  stream = null;
  video.srcObject = null;
  document.body.classList.remove('is-live');
  torchButton.hidden = true;
  torchButton.setAttribute('aria-pressed', 'false');
  setStatus('');
}

// A code counts once it has been read twice: a check digit passes one random
// misread in ten, and the second read costs ~120 ms.
async function scanLoop(scanner) {
  let candidate = null;
  while (scanning) {
    if (video.readyState >= 2) {
      let found = [];
      try {
        found = await scanner.detect(video);
      } catch { /* a frame the detector could not use */ }
      if (!scanning) return;
      const code = found.map((item) => normalize(item.rawValue)).find(Boolean);
      if (code && code === candidate) {
        navigator.vibrate?.(60);
        stopCamera();
        lookup(code);
        return;
      }
      if (code) candidate = code;
    }
    await sleep(SCAN_INTERVAL_MS);
  }
}

function offerTorch() {
  const track = stream?.getVideoTracks()[0];
  const capabilities = track?.getCapabilities?.() ?? {};
  torchButton.hidden = !capabilities.torch;
}

torchButton.addEventListener('click', async () => {
  const track = stream?.getVideoTracks()[0];
  if (!track) return;
  const on = torchButton.getAttribute('aria-pressed') !== 'true';
  try {
    await track.applyConstraints({ advanced: [{ torch: on }] });
    torchButton.setAttribute('aria-pressed', String(on));
  } catch {
    torchButton.hidden = true;
  }
});

// ---- lookup ----------------------------------------------------------------------

async function lookup(code) {
  pending = code;
  input.value = code;
  result.replaceChildren(el('div', { class: 'card card-loading' },
    el('p', { class: 'kicker mono', text: code }),
    el('p', { class: 'loading', text: 'Suche …' })));
  let response;
  try {
    response = await fetch(`/barcode/api/${code}`, { headers: { Accept: 'application/json' } });
  } catch {
    if (pending === code) showError('Keine Verbindung – nochmal versuchen.', code);
    return;
  }
  if (pending !== code) return;
  if (response.status === 401 || response.redirected) {
    showError('Sitzung abgelaufen – bitte neu anmelden.', null, true);
    return;
  }
  let data = null;
  try {
    data = await response.json();
  } catch { /* not JSON: handled below */ }
  if (pending !== code) return;
  if (!response.ok || !data) {
    showError(data?.error || 'Unerwartete Antwort – nochmal versuchen.', response.status === 400 ? null : code);
    return;
  }
  showResult(data);
  remember(data);
}

function scanAgainButton() {
  return el('button', {
    type: 'button',
    class: 'button button-primary',
    text: 'Nächster Scan',
    onclick: () => {
      window.scrollTo({ top: 0, behavior: 'smooth' });
      startCamera();
    },
  });
}

function showCard(card) {
  result.replaceChildren(card);
  document.body.classList.add('has-result');
  startButton.textContent = 'Nächster Scan';
  result.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function showError(message, retryCode, relogin = false) {
  showCard(el('article', { class: 'card' },
    el('p', { class: 'kicker kicker-error', text: 'Fehler' }),
    el('p', { class: 'message', text: message }),
    el('div', { class: 'actions' },
      retryCode ? el('button', { type: 'button', class: 'button', text: 'Nochmal', onclick: () => lookup(retryCode) }) : null,
      relogin ? el('a', { class: 'button', href: '/login', text: 'Anmelden' }) : null,
      scanAgainButton())));
}

function showResult(data) {
  if (data.book) showCard(bookCard(data));
  else if (data.product) showCard(productCard(data));
  else showCard(missingCard(data));
}

// ---- cards -----------------------------------------------------------------------

const TYPE_LABEL = { food: 'Lebensmittel', beauty: 'Kosmetik', petfood: 'Tierfutter', product: 'Produkt' };
const NOVA_HINT = { 1: 'unverarbeitet', 2: 'Küchenzutat', 3: 'verarbeitet', 4: 'hochverarbeitet' };
const MACROS = new Set(['energy-kcal', 'proteins']);
const SPECIAL_GS1 = new Set(['ISBN (Buch)', 'ISSN (Zeitschrift)', 'Gutschein', 'Rückgabebeleg',
  'GS1 Global Office', 'Handelsinterne Nummer']);

const number = (value, digits) => new Intl.NumberFormat('de-DE', { maximumFractionDigits: digits }).format(value);
const euro = (value) => new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(value);

function amount(value, unit) {
  if (value === null || value === undefined) return '–';
  const digits = unit === 'kcal' ? 0 : value < 1 ? 2 : 1;
  return `${number(value, digits)} ${unit}`;
}

function gs1Text(label) {
  return SPECIAL_GS1.has(label) ? label : `Code vergeben in ${label}`;
}

function thumb(src, extraClass = '') {
  if (!src) return null;
  // Not lazy: the picture sits at the top of the card, and a lazy image
  // appended by script was never fetched in Chromium. `src` goes last so the
  // referrer policy already applies to the request it starts.
  return el('img', {
    class: `thumb ${extraClass}`.trim(),
    alt: '',
    referrerpolicy: 'no-referrer',
    onerror: (event) => event.target.remove(),
    onload: (event) => {
      if (event.target.naturalWidth < 8) event.target.remove();
      else event.target.classList.add('is-loaded');
    },
    src,
  });
}

function head(kicker, title, meta, image, imageClass) {
  return el('header', { class: 'card-head' },
    thumb(image, imageClass),
    el('div', { class: 'head-text' },
      el('p', { class: 'kicker', text: kicker }),
      el('h2', { text: title }),
      meta ? el('p', { class: 'meta', text: meta }) : null));
}

function footer(data, source) {
  return el('footer', { class: 'card-foot' },
    el('p', { class: 'code-line' },
      el('span', { class: 'mono', text: data.code }),
      data.gs1 ? ` · ${gs1Text(data.gs1)}` : null),
    source?.url
      ? el('a', { class: 'source', href: source.url, target: '_blank', rel: 'noopener noreferrer', text: `${source.name} ↗` })
      : source ? el('p', { class: 'source', text: source.name }) : null,
    el('div', { class: 'actions' }, scanAgainButton()));
}

function scoreBadge(label, value, tone, hint) {
  return el('div', { class: `score ${tone}` },
    el('span', { class: 'score-value', text: value }),
    el('span', { class: 'score-text' },
      el('span', { class: 'score-label', text: label }),
      hint ? el('span', { class: 'score-hint', text: hint }) : null));
}

function scoresBlock(scores) {
  const badges = [];
  if (scores.nutriscore) {
    badges.push(scoreBadge('Nutri-Score', scores.nutriscore.toUpperCase(), `grade-${scores.nutriscore}`));
  }
  if (scores.nova) badges.push(scoreBadge('NOVA', String(scores.nova), `nova-${scores.nova}`, NOVA_HINT[scores.nova]));
  if (scores.ecoscore) {
    const grade = scores.ecoscore === 'a-plus' ? 'A+' : scores.ecoscore.toUpperCase();
    badges.push(scoreBadge('Eco-Score', grade, `grade-${scores.ecoscore}`));
  }
  return badges.length ? el('div', { class: 'scores' }, badges) : null;
}

function nutritionBlock(nutrition) {
  if (!nutrition) return null;
  const perServing = nutrition.rows.some((row) => row.per_serving !== null);
  return el('section', { class: 'block' },
    el('h3', { text: 'Nährwerte' }),
    el('table', { class: 'nutrition' },
      el('thead', {}, el('tr', {},
        el('th', { scope: 'col' }, el('span', { class: 'visually-hidden', text: 'Nährstoff' })),
        el('th', { scope: 'col', text: `je ${nutrition.basis}` }),
        perServing
          ? el('th', { scope: 'col', text: nutrition.serving_size ? `Portion (${nutrition.serving_size})` : 'je Portion' })
          : null)),
      el('tbody', {}, nutrition.rows.map((row) => el('tr', {
        class: [row.sub ? 'sub' : '', MACROS.has(row.key) ? 'macro' : ''].join(' ').trim() || null,
      },
      el('th', { scope: 'row', text: row.label }),
      el('td', { text: amount(row.per_100g, row.unit) }),
      perServing ? el('td', { text: amount(row.per_serving, row.unit) }) : null)))));
}

function chip(text, tone) {
  return el('span', { class: `chip chip-${tone}`, text });
}

function traitsBlock(product) {
  const diet = product.diet || {};
  const tone = { yes: 'good', no: 'bad', maybe: 'unsure' };
  const chips = [];
  if (diet.vegan) chips.push(chip({ yes: 'vegan', no: 'nicht vegan', maybe: 'vielleicht vegan' }[diet.vegan], tone[diet.vegan]));
  if (diet.vegetarian) {
    chips.push(chip({ yes: 'vegetarisch', no: 'nicht vegetarisch', maybe: 'vielleicht vegetarisch' }[diet.vegetarian],
      tone[diet.vegetarian]));
  }
  if (diet.palm_oil_free) {
    chips.push(chip({ yes: 'ohne Palmöl', no: 'mit Palmöl', maybe: 'evtl. Palmöl' }[diet.palm_oil_free],
      tone[diet.palm_oil_free]));
  }
  if (product.deposit) chips.push(chip(product.deposit, 'info'));
  if (!chips.length) return null;
  return el('section', { class: 'block' },
    el('h3', { text: 'Merkmale' }),
    el('div', { class: 'chips' }, chips),
    product.diet ? el('p', { class: 'fine', text: 'Vegan/vegetarisch/Palmöl aus der Zutatenliste abgeleitet, nicht amtlich.' }) : null);
}

function allergensBlock(product) {
  if (product.type !== 'food' && !product.allergens.length && !product.traces.length) return null;
  return el('section', { class: 'block' },
    el('h3', { text: 'Allergene' }),
    product.allergens.length
      ? el('div', { class: 'chips' }, product.allergens.map((name) => chip(name, 'warn')))
      : el('p', { class: 'muted', text: 'Keine erfasst – im Zweifel die Packung prüfen.' }),
    product.traces.length
      ? el('p', { class: 'traces', text: `Kann Spuren enthalten: ${product.traces.join(', ')}` })
      : null);
}

function ingredientsBlock(ingredients) {
  if (!ingredients) return null;
  return el('section', { class: 'block' },
    el('h3', { text: 'Zutaten' }),
    el('p', { class: 'ingredients', text: ingredients.text }),
    ingredients.lang === 'other' ? el('p', { class: 'fine', text: 'Nur in einer anderen Sprache erfasst.' }) : null);
}

function productCard(data) {
  const product = data.product;
  const meta = [product.brand, product.quantity].filter(Boolean).join(' · ');
  return el('article', { class: 'card' },
    head(TYPE_LABEL[product.type] || 'Produkt', product.name || 'Ohne Namen', meta, product.image),
    product.generic ? el('p', { class: 'generic', text: product.generic }) : null,
    scoresBlock(product.scores),
    nutritionBlock(product.nutrition),
    traitsBlock(product),
    allergensBlock(product),
    ingredientsBlock(product.ingredients),
    footer(data, product.source));
}

function bookCard(data) {
  const book = data.book;
  const facts = [
    ['Verlag', book.publisher],
    ['Erschienen', book.year],
    ['Seiten', book.pages],
    ['Preis bei Erscheinen', book.price_de === null ? null : euro(book.price_de)],
    ['Sachgebiet', book.subject],
  ].filter(([, value]) => value !== null && value !== undefined && value !== '');
  return el('article', { class: 'card' },
    head('Buch', book.title, book.authors.join(', '), book.image, 'thumb-book'),
    facts.length
      ? el('dl', { class: 'facts' }, facts.flatMap(([term, value]) => [el('dt', { text: term }), el('dd', { text: String(value) })]))
      : null,
    footer(data, book.source));
}

function missingCard(data) {
  const instore = data.kind === 'instore';
  return el('article', { class: 'card' },
    el('p', { class: 'kicker', text: 'Nicht gefunden' }),
    el('h2', { class: 'mono', text: data.code }),
    el('p', {
      class: 'message',
      text: instore
        ? 'Handelsinterne Nummer – Eigenmarke, Frischetheke oder Waage. Solche Codes gelten nur im jeweiligen Markt.'
        : 'Weder Open Food Facts noch die Schwester-Datenbanken kennen diesen Code.',
    }),
    data.gs1 && !instore ? el('p', { class: 'muted', text: gs1Text(data.gs1) }) : null,
    el('div', { class: 'actions' },
      data.add_url
        ? el('a', { class: 'button', href: data.add_url, target: '_blank', rel: 'noopener noreferrer', text: 'Bei Open Food Facts eintragen ↗' })
        : null,
      scanAgainButton()));
}

// ---- recent scans (this device only) ----------------------------------------------

function readRecent() {
  try {
    const list = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]');
    return Array.isArray(list)
      ? list.filter((item) => item && /^\d{8,13}$/.test(item.code) && typeof item.name === 'string')
      : [];
  } catch {
    return [];
  }
}

function renderRecent(list) {
  recentSection.hidden = list.length === 0;
  recentList.replaceChildren(...list.map((item) => el('li', {},
    el('button', {
      type: 'button',
      class: 'recent-item',
      onclick: () => {
        stopCamera();
        lookup(item.code);
      },
    },
    el('span', { class: 'recent-name', text: item.name }),
    el('span', { class: 'recent-code mono', text: item.code })))));
}

function remember(data) {
  const name = data.product?.name || data.book?.title || (data.found ? 'Ohne Namen' : 'Nicht gefunden');
  const list = [{ code: data.code, name }, ...readRecent().filter((item) => item.code !== data.code)]
    .slice(0, RECENT_MAX);
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(list));
  } catch { /* private mode: the list is just not kept */ }
  renderRecent(list);
}

// ---- wiring ------------------------------------------------------------------------

startButton.addEventListener('click', startCamera);

form.addEventListener('submit', (event) => {
  event.preventDefault();
  const code = normalize(input.value);
  if (!code) {
    showError('Ungültiger Code – Länge oder Prüfziffer stimmt nicht.', null);
    return;
  }
  stopCamera();
  input.blur();
  lookup(code);
});

// A camera left running in a background tab drains the battery and keeps the
// phone's camera light on; the button brings it back.
document.addEventListener('visibilitychange', () => {
  if (document.hidden) stopCamera();
});

renderRecent(readRecent());

// Start straight away when the camera is already allowed; otherwise wait for
// the button, so the permission prompt follows a tap instead of a page load.
(async () => {
  try {
    const permission = await navigator.permissions?.query({ name: 'camera' });
    if (permission?.state === 'granted') startCamera();
  } catch { /* Safari and Firefox cannot query the camera permission */ }
})();
