/* Drag-to-reorder for the session queue.
 *
 * Ported from the previous session screen's inline version, with three
 * changes: it moves queue ROWS rather than whole exercise cards (the rows are
 * already compact, so nothing has to be collapsed first), it reads its state
 * from window.GymReorder instead of a lock button, and it hands the finished
 * order back through the page's own performMutation refresh.
 *
 * Why pointer events and not the drag-and-drop API: this is a phone held in
 * one hand. `touch-action: none` on the handle is what stops the browser
 * claiming a vertical pan before JS sees enough movement to know it is a drag
 * -- there is no "opt in past a threshold" for a gesture the browser has
 * already recognised, so the handle is a small, always-scroll-exempt target.
 */
(function () {
  'use strict';

  var DRAG_THRESHOLD = 8;
  var SCROLL_EDGE = 80;
  var SCROLL_SPEED = 16;

  var card = null, ghost = null, handle = null;
  var pointerId = null, startY = 0, lastY = 0, grabOffset = 0, baseY = 0;
  var dragging = false, rafId = null;

  function container() { return document.getElementById('queue'); }

  function begin() {
    dragging = true;
    try { handle.setPointerCapture(pointerId); } catch (err) { /* not fatal */ }

    var rect = card.getBoundingClientRect();
    grabOffset = lastY - rect.top;
    baseY = lastY;
    card.classList.add('is-dragging');
    card.style.visibility = 'hidden';

    ghost = card.cloneNode(true);
    ghost.removeAttribute('id');
    ghost.querySelectorAll('[id]').forEach(function (el) { el.removeAttribute('id'); });
    ghost.classList.add('drag-ghost');
    ghost.setAttribute('inert', '');
    ghost.style.position = 'fixed';
    ghost.style.left = rect.left + 'px';
    ghost.style.width = rect.width + 'px';
    ghost.style.top = (lastY - grabOffset) + 'px';
    ghost.style.margin = '0';
    ghost.style.pointerEvents = 'none';
    ghost.style.visibility = 'visible';
    document.body.appendChild(ghost);

    if (!rafId) { rafId = requestAnimationFrame(autoScroll); }
  }

  function reset() {
    if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
    if (ghost) { ghost.remove(); ghost = null; }
    if (card) { card.classList.remove('is-dragging'); card.style.visibility = ''; }
    if (handle && pointerId !== null) {
      try { handle.releasePointerCapture(pointerId); } catch (err) { /* already gone */ }
    }
    card = null; handle = null; pointerId = null; dragging = false;
  }

  function move(clientY) {
    var box = container();
    if (!box || !ghost) { return; }
    ghost.style.transform = 'translateY(' + (clientY - baseY) + 'px)';

    var g = ghost.getBoundingClientRect();
    var centre = g.top + g.height / 2;
    var rows = Array.prototype.slice.call(box.children);
    var i = rows.indexOf(card);

    var next = rows[i + 1];
    if (next) {
      var nr = next.getBoundingClientRect();
      if (centre > nr.top + nr.height / 2) {
        box.insertBefore(card, next.nextElementSibling);
        return;
      }
    }
    var prev = rows[i - 1];
    if (prev) {
      var pr = prev.getBoundingClientRect();
      if (centre < pr.top + pr.height / 2) { box.insertBefore(card, prev); }
    }
  }

  function autoScroll() {
    if (!dragging || !card) { rafId = null; return; }
    var vh = window.innerHeight;
    var delta = 0;
    if (lastY < SCROLL_EDGE) {
      delta = -Math.ceil(SCROLL_SPEED * (SCROLL_EDGE - lastY) / SCROLL_EDGE);
    } else if (lastY > vh - SCROLL_EDGE) {
      delta = Math.ceil(SCROLL_SPEED * (lastY - (vh - SCROLL_EDGE)) / SCROLL_EDGE);
    }
    if (delta !== 0) { window.scrollBy(0, delta); move(lastY); }
    rafId = requestAnimationFrame(autoScroll);
  }

  function finish() {
    if (!card) { return; }
    var was = dragging;
    var box = container();
    var order = (was && box)
      ? Array.prototype.slice.call(box.children).map(function (c) { return c.dataset.seId; })
      : null;
    reset();
    if (!was || !order || !order.length || !window.GymReorder) { return; }
    fetch(window.GymReorder.url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ order: order }),
      credentials: 'same-origin',
    })
      .then(function (r) { if (!r.ok) { throw new Error('HTTP ' + r.status); } return r.text(); })
      .then(function (html) { window.GymReorder.refresh(html); })
      .catch(function (err) { console.error('Reihenfolge nicht gespeichert:', err); });
  }

  document.addEventListener('pointerdown', function (e) {
    if (!window.GymReorder || !window.GymReorder.unlocked) { return; }
    var h = e.target.closest && e.target.closest('.drag-handle');
    if (!h) { return; }
    card = h.closest('.queue__row');
    if (!card) { return; }
    handle = h;
    pointerId = e.pointerId;
    startY = lastY = e.clientY;
    dragging = false;
    e.preventDefault();
  });

  document.addEventListener('pointermove', function (e) {
    if (!card) { return; }
    lastY = e.clientY;
    if (!dragging) {
      if (Math.abs(e.clientY - startY) < DRAG_THRESHOLD) { return; }
      begin();
    }
    e.preventDefault();
    move(e.clientY);
  });

  document.addEventListener('pointerup', finish);
  document.addEventListener('pointercancel', function () { reset(); });
})();
