// Paste into the browser console (or run through a browser tool) on a signed-in Tandem page, at the phone size you
// care about (375x667 and 375x812). It visits each page and reports anything that would be cut off by the fixed
// screen: content running past the bottom of <main>, or past an overflow-hidden box inside it. Lists that are meant
// to scroll (overflow-y: auto) are fine. It prints "fits" for a page that fits.
//
//   await tandemFit(["/", "/trips", "/assistant"])
window.tandemFit = async (paths) => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const go = (p) => { history.pushState({}, "", p); dispatchEvent(new PopStateEvent("popstate")); };
  const check = () => {
    const main = document.querySelector("main");
    if (!main) return ["no <main>"];
    const mainBottom = main.getBoundingClientRect().bottom;
    // The page fades in with a small slide; measure as if it had settled.
    const wrap = main.firstElementChild?.firstElementChild;
    const shift = wrap ? new DOMMatrix(getComputedStyle(wrap).transform).f || 0 : 0;
    const bad = [];
    main.querySelectorAll("*").forEach((el) => {
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      if (!r.height || !r.width || cs.display === "none" || cs.visibility === "hidden" || (el.closest("svg") && el.tagName !== "svg")) return;
      let scrolls = false;
      let hiddenChecked = false;
      for (let p = el.parentElement; p && p !== main; p = p.parentElement) {
        const o = getComputedStyle(p).overflowY;
        if (o === "auto" || o === "scroll") { scrolls = true; break; }
        if (o === "hidden" && cs.position !== "absolute" && !el.closest("[data-state]") && !hiddenChecked) {
          hiddenChecked = true; // only the nearest clipping box matters
          if (r.bottom > p.getBoundingClientRect().bottom + 1.5) bad.push(`${el.tagName}.${String(el.className).slice(0, 50)} past its box by ${Math.round(r.bottom - p.getBoundingClientRect().bottom)}px`);
        }
      }
      if (!scrolls && !el.closest("[data-state]") && r.bottom - shift > mainBottom + 1) bad.push(`${el.tagName}.${String(el.className).slice(0, 50)} past the screen`);
    });
    return bad;
  };
  const out = {};
  for (const p of paths) {
    go(p);
    await sleep(1600);
    const bad = check();
    out[p] = bad.length ? bad.slice(0, 5) : "fits";
  }
  return out;
};
