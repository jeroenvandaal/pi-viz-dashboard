import { getDisplay, patchDisplay } from "./display.js";

const PRESETS = [5, 10, 15, 30, 60, 120];
const burger = document.getElementById("burger");
const menu = document.getElementById("menu");
const sw = document.getElementById("cycleSw");
const secVal = document.getElementById("secVal");

const fmt = (s) => (s < 60 ? s + "s" : (s / 60) + "m");
const nearestPreset = (s) => PRESETS.reduce((a, b) => Math.abs(b - s) < Math.abs(a - s) ? b : a);

let cycle = false, interval = 10;

function render() {
  sw.classList.toggle("on", cycle);
  secVal.textContent = fmt(interval);
}

function syncBurger() { burger.classList.toggle("open", menu.classList.contains("open")); }
burger.addEventListener("click", (e) => { e.stopPropagation(); menu.classList.toggle("open"); syncBurger(); });
menu.addEventListener("click", (e) => e.stopPropagation());
document.querySelector(".carousel").addEventListener("click", () => { menu.classList.remove("open"); syncBurger(); });

sw.addEventListener("click", () => { cycle = !cycle; render(); patchDisplay({ cycle }); });
document.getElementById("secUp").addEventListener("click", () => {
  const i = Math.min(PRESETS.length - 1, PRESETS.indexOf(interval) + 1);
  interval = PRESETS[i]; render(); patchDisplay({ interval_sec: interval });
});
document.getElementById("secDown").addEventListener("click", () => {
  const i = Math.max(0, PRESETS.indexOf(interval) - 1);
  interval = PRESETS[i]; render(); patchDisplay({ interval_sec: interval });
});

// Keep the menu in sync with server state (also reflects phone changes).
async function load() {
  const d = await getDisplay(); if (!d) return;
  cycle = d.cycle; interval = nearestPreset(d.interval_sec); render();
}
load();
setInterval(load, 3000);
