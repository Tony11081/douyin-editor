// 口碑墙模板共用：卡片 HTML、缓动函数、随机数。两个风格（wall.html / vortex.html）都用它。
// 内容来自 window.SPEC（render.py 注入；直接打开 html 时用 example.json 的内容兜底）。
(function () {
  const STAR =
    '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 1.5l2.6 5.6 6.1.7-4.5 4.2 1.2 6L10 15l-5.4 3 1.2-6L1.3 7.8l6.1-.7z"/></svg>';
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  // 文案里用 [[关键词]] 标绿色高亮，其余一律转义。
  const rich = (s) => esc(s).replace(/\[\[(.+?)\]\]/g, "<b>$1</b>");
  const initial = (who) => {
    const w = String(who || "").trim();
    if (!w) return "·";
    return /^[A-Za-z]/.test(w) ? w[0].toUpperCase() : w.slice(-1);
  };

  function cardHTML(c, opts = {}) {
    const glow = opts.glow ? " glow" : "";
    const tag = `<div class="tag"><span>${esc(c.group || "")}</span>${c.sample ? '<span class="ex">示例</span>' : ""}</div>`;
    const who = c.who
      ? `<div class="who"><div class="av">${esc(initial(c.who))}</div><div><b>${esc(c.who)}</b><small>${esc(c.meta || "")}</small></div></div>`
      : "";
    const res = c.result ? `<div class="res">${esc(c.result)}</div>` : "";
    const stars = (n) => `<div class="stars">${STAR.repeat(Math.max(1, Math.min(5, n || 5)))}</div>`;
    let body = "";
    switch (c.kind) {
      case "review":
        body = `${stars(c.stars)}<div class="q">${rich(c.text)}</div>${who}${res}`;
        break;
      case "number":
        body = `<strong class="big">${esc(c.value)}</strong><p>${esc(c.text)}</p>`;
        break;
      case "chat":
        body = `<div class="chat"><div class="bar">${esc(c.bar || "")}</div>${(c.msgs || [])
          .map(([me, t]) => `<div class="m${me ? " me" : ""}"><i></i><p>${esc(t)}</p></div>`)
          .join("")}</div>${who}${res}`;
        break;
      default:
        body = `<div class="q">${rich(c.text)}</div>${who}${res}`;
    }
    return `<div class="card k-${esc(c.kind || "quote")}${glow}">${tag}${body}</div>`;
  }

  // 可复现的随机数：同一个种子每次渲染结果一样，逐帧截图不抖。
  function rng(seed) {
    let s = seed >>> 0 || 1;
    return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
  }

  const cl = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const E = {
    cl,
    lerp: (a, b, p) => a + (b - a) * p,
    out: (x) => 1 - Math.pow(1 - cl(x), 3),
    out5: (x) => 1 - Math.pow(1 - cl(x), 5),
    inOut: (x) => { x = cl(x); return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; },
    in3: (x) => Math.pow(cl(x), 3),
    back: (x, c = 1.6) => { x = cl(x); return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2); },
    bell: (x) => Math.sin(Math.PI * cl(x)),
  };

  window.TW = { cardHTML, rng, E, esc, rich, STAR };
})();
