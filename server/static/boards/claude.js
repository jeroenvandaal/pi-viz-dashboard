// The Claude usage + feature-log board, as a self-contained module.
export function createClaudeBoard() {
  const QUOTA_MS = 60000, FEATURES_MS = 30000;
  const WINDOW_ORDER = ["five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet", "credits"];
  let timers = [];

  function band(p) { return p > 85 ? "red" : p >= 60 ? "amber" : "green"; }
  function valColor(p) { return p > 85 ? "#f85149" : p >= 60 ? "#f0883e" : "#3fb950"; }
  function esc(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }
  function rel(iso) {
    if (!iso) return "";
    const s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (s < 3600) return Math.max(1, Math.round(s / 60)) + "m";
    if (s < 86400) return Math.round(s / 3600) + "h";
    return Math.round(s / 86400) + "d";
  }
  function untilStr(iso) {
    if (!iso) return "";
    const s = (new Date(iso).getTime() - Date.now()) / 1000;
    if (s <= 0) return "resetting";
    if (s < 3600) return "resets in " + Math.max(1, Math.round(s / 60)) + "m";
    if (s < 86400) return "resets in " + Math.round(s / 3600) + "h";
    return "resets in " + Math.round(s / 86400) + "d";
  }

  const HTML = `
    <section class="q">
      <div class="hd">⚡ <b>Claude</b> Usage</div>
      <div class="metrics"></div>
      <div class="clock"><span class="updated"></span><span class="sep">|</span><span class="live">● live</span></div>
    </section>
    <section class="f">
      <div class="hd"><div class="t">✅ <b>Features</b> &nbsp;Claude &amp; me</div>
        <div class="counts"></div></div>
      <div class="scrollwrap">
        <div class="list"></div>
        <div class="sbthumb"></div>
      </div>
    </section>`;

  function mount(root) {
    root.classList.add("board-claude");
    root.innerHTML = HTML;
    const $ = (s) => root.querySelector(s);

    async function refreshQuota() {
      try {
        const q = await (await fetch("/api/quota")).json();
        const box = $(".metrics"); box.innerHTML = "";
        const data = q.data || {};
        for (const key of WINDOW_ORDER) {
          const w = data[key]; if (!w) continue;
          const pct = Math.round(w.pct);
          const sub = w.detail || untilStr(w.resets_at);
          const el = document.createElement("div"); el.className = "metric";
          el.innerHTML = `<div class="top"><span class="name">${esc(w.label)}</span>
            <span class="val" style="color:${valColor(pct)}">${pct}%</span></div>
            <div class="track"><div class="fill ${band(pct)}" style="width:${pct}%"></div></div>
            <div class="sub">${esc(sub)}</div>`;
          box.appendChild(el);
        }
        $(".updated").textContent = q.updated_at ? "updated " + rel(q.updated_at) + " ago" : "";
        $(".clock").classList.toggle("stale", !!q.stale);
      } catch (e) { $(".clock").classList.add("stale"); }
    }

    async function refreshFeatures() {
      try {
        const { features } = await (await fetch("/api/features")).json();
        const list = $(".list"); list.innerHTML = "";
        let active = 0, done = 0;
        for (const f of features) {
          const ip = f.status === "in_progress"; ip ? active++ : done++;
          const row = document.createElement("div"); row.className = "row" + (ip ? " active" : "");
          row.innerHTML = `<div class="badge ${ip ? "ip" : "dn"}"><span class="pip"></span>${ip ? "In&nbsp;prog" : "Done"}</div>
            <div class="meta"><div class="title">${esc(f.title)}</div><div class="desc">${esc(f.summary || "")}</div></div>
            <div class="proj">${esc(f.project)}</div><div class="when">${rel(f.updated_at)}</div>`;
          list.appendChild(row);
        }
        $(".counts").innerHTML =
          `<span class="a">${active} in progress</span> · <span class="d">${done} done</span>`;
        updateThumb();
      } catch (e) {}
    }

    // overlay scrollbar + drag-to-scroll (touch panel registers as a mouse)
    const wrap = $(".scrollwrap"), listEl = $(".list"), thumb = $(".sbthumb");
    let hideT;
    function updateThumb() {
      const ratio = listEl.clientHeight / listEl.scrollHeight;
      if (ratio >= 1) { thumb.style.opacity = 0; return; }
      const h = Math.max(24, listEl.clientHeight * ratio);
      const top = (listEl.scrollTop / (listEl.scrollHeight - listEl.clientHeight)) * (listEl.clientHeight - h);
      thumb.style.height = h + "px"; thumb.style.top = top + "px";
    }
    listEl.addEventListener("scroll", () => {
      updateThumb(); wrap.classList.add("scrolling");
      clearTimeout(hideT); hideT = setTimeout(() => wrap.classList.remove("scrolling"), 1000);
    });
    let dragging = false, startY = 0, startTop = 0, lastY = 0, lastT = 0, vel = 0, raf = 0;
    listEl.addEventListener("pointerdown", (e) => {
      dragging = true; startY = e.clientY; startTop = listEl.scrollTop;
      lastY = e.clientY; lastT = e.timeStamp; vel = 0;
      cancelAnimationFrame(raf);
      try { listEl.setPointerCapture(e.pointerId); } catch (_) {}
    });
    listEl.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      listEl.scrollTop = startTop - (e.clientY - startY);
      const dt = e.timeStamp - lastT;
      if (dt > 0) vel = (e.clientY - lastY) / dt;
      lastY = e.clientY; lastT = e.timeStamp;
    });
    function releaseDrag() {
      if (!dragging) return;
      dragging = false;
      let v = vel * 16;
      (function momentum() {
        if (Math.abs(v) < 0.4) return;
        listEl.scrollTop -= v; v *= 0.92;
        raf = requestAnimationFrame(momentum);
      })();
    }
    listEl.addEventListener("pointerup", releaseDrag);
    listEl.addEventListener("pointercancel", releaseDrag);
    window.addEventListener("resize", updateThumb);

    this._refreshQuota = refreshQuota;
    this._refreshFeatures = refreshFeatures;
  }

  return {
    id: "claude",
    label: "Claude",
    mount,
    start() {
      this._refreshQuota(); this._refreshFeatures();
      timers.push(setInterval(() => this._refreshQuota(), QUOTA_MS));
      timers.push(setInterval(() => this._refreshFeatures(), FEATURES_MS));
    },
    stop() { timers.forEach(clearInterval); timers = []; },
  };
}
