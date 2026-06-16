import { BOARDS } from "./boards.js";
import { getDisplay, patchDisplay } from "./display.js";

const N = BOARDS.length;
const carousel = document.querySelector(".carousel");
const track = document.getElementById("track");
const nav = document.getElementById("nav");
const dotsEl = document.getElementById("dots");

let idx = 0, navHideT = 0;

// Build slides + dots; mount every board once.
BOARDS.forEach((board, i) => {
  const slide = document.createElement("div");
  slide.className = "board";
  track.appendChild(slide);
  board.mount(slide);
  const dot = document.createElement("span");
  dot.className = "dot" + (i === 0 ? " on" : "");
  dotsEl.appendChild(dot);
});

function showNav() {
  if (N < 2) return;
  nav.classList.add("show");
  clearTimeout(navHideT);
  navHideT = setTimeout(() => { if (!window.__cycling__) nav.classList.remove("show"); }, 1800);
}

function renderDots() {
  [...dotsEl.children].forEach((d, i) => d.classList.toggle("on", i === idx));
}

// Public hook the cycle driver overrides (Task 6).
window.__onBoardChange__ = () => {};

function go(i, { animate = true, push = true } = {}) {
  const next = (i + N) % N;
  if (next === idx) return;
  track.style.transition = animate ? "" : "none";
  idx = next;
  track.style.transform = `translateX(${-idx * 100}vw)`;
  renderDots(); showNav();
  if (push) patchDisplay({ active_board: BOARDS[idx].id });
  window.__onBoardChange__();
}
window.__go__ = go;
window.__getIdx__ = () => idx;

// All boards poll continuously (cheap; same-origin). Simpler than start/stop-on-view
// and avoids a flash of empty board on swipe. start() each once.
BOARDS.forEach((b) => b.start());

// Horizontal swipe = switch board; vertical = let the board handle it.
let down = false, sx = 0, sy = 0, horiz = null, base = 0;
carousel.addEventListener("pointerdown", (e) => {
  down = true; horiz = null; sx = e.clientX; sy = e.clientY; base = -idx * 100;
  track.style.transition = "none";
});
carousel.addEventListener("pointermove", (e) => {
  if (!down) return;
  const dx = e.clientX - sx, dy = e.clientY - sy;
  if (horiz === null && (Math.abs(dx) > 8 || Math.abs(dy) > 8)) horiz = Math.abs(dx) > Math.abs(dy);
  if (horiz) {
    e.preventDefault();
    // Rubber-band: resist dragging toward a board that doesn't exist (at an edge,
    // or always when there's a single board) so it barely moves and snaps back.
    const atStart = idx === 0, atEnd = idx === N - 1;
    const eff = ((dx > 0 && atStart) || (dx < 0 && atEnd)) ? dx / 4 : dx;
    track.style.transform = `translateX(${base + (eff / window.innerWidth) * 100}vw)`;
    showNav();
  }
});
function up(e) {
  if (!down) return;
  down = false;
  if (horiz) {
    track.style.transition = "";
    const dx = e.clientX - sx, thresh = window.innerWidth * 0.18;
    // Clamp to [0, N-1] (no wrap) and ALWAYS restore the transform: animate to the
    // new board, or snap back if the target is the current board (incl. single board).
    let target = idx;
    if (dx < -thresh) target = Math.min(N - 1, idx + 1);
    else if (dx > thresh) target = Math.max(0, idx - 1);
    if (target !== idx) go(target);
    else track.style.transform = `translateX(${-idx * 100}vw)`;  // snap back
  }
  horiz = null;
}
carousel.addEventListener("pointerup", up);
carousel.addEventListener("pointercancel", up);

document.addEventListener("keydown", (e) => {
  if (e.key === "ArrowRight") go(idx + 1);
  if (e.key === "ArrowLeft") go(idx - 1);
});

// Adopt server's active_board on load + poll for remote (phone) changes.
async function syncFromServer() {
  const d = await getDisplay();
  if (!d) return;
  const target = BOARDS.findIndex((b) => b.id === d.active_board);
  if (target >= 0 && target !== idx) go(target, { push: false });
  else if (target < 0) go(0, { push: true });  // §9: unknown board → fall back to 0 + rewrite state
  window.__applyCycleState__ && window.__applyCycleState__(d);
}
syncFromServer();
setInterval(syncFromServer, 3000);

// ---- Auto-cycle ----
const cycwrap = document.getElementById("cycwrap");
const cycbar = document.getElementById("cycbar");
let cycling = false, intervalSec = 10, cycleStart = 0, cycleRaf = 0;

function tickCycle() {
  if (!cycling) return;
  const t = (performance.now() - cycleStart) / (intervalSec * 1000);
  cycbar.style.width = Math.min(100, t * 100) + "%";
  if (t >= 1) { go(idx + 1); resetCycle(); }
  cycleRaf = requestAnimationFrame(tickCycle);
}
function resetCycle() { cycleStart = performance.now(); cycbar.style.width = "0%"; }
function startCycle() {
  if (cycling || N < 2) return;
  cycling = true; window.__cycling__ = true;
  nav.classList.add("show"); cycwrap.classList.add("on");
  resetCycle(); cancelAnimationFrame(cycleRaf); cycleRaf = requestAnimationFrame(tickCycle);
}
function stopCycle() {
  cycling = false; window.__cycling__ = false;
  cancelAnimationFrame(cycleRaf); cycbar.style.width = "0%"; cycwrap.classList.remove("on");
  showNav();  // let dots fade out normally
}

// Manual board change resets the countdown but does NOT stop cycling (spec §6).
window.__onBoardChange__ = () => { if (cycling) resetCycle(); };

// Apply server cycle state (called from syncFromServer on load + every poll).
window.__applyCycleState__ = (d) => {
  intervalSec = d.interval_sec;
  if (d.cycle && !cycling) startCycle();
  else if (!d.cycle && cycling) stopCycle();
};
