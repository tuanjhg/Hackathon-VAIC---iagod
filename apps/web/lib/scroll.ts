/** Smoothly animate an element's scrollLeft via rAF. Reliable even where
 *  scrollBy({behavior:"smooth"}) is unsupported; honours reduced-motion. */
export function animateScrollLeft(el: HTMLElement, target: number, duration = 450) {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    el.scrollLeft = target;
    return;
  }
  const start = el.scrollLeft;
  const dist = target - start;
  let t0: number | null = null;
  const step = (ts: number) => {
    if (t0 === null) t0 = ts;
    const p = Math.min(1, (ts - t0) / duration);
    const ease = 1 - Math.pow(1 - p, 3); // easeOutCubic
    el.scrollLeft = start + dist * ease;
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

/** Slide a horizontal scroller by ~85% of its width, looping at the end. */
export function slideRail(el: HTMLElement, dir: 1 | -1) {
  const max = el.scrollWidth - el.clientWidth;
  const stepBy = el.clientWidth * 0.85;
  let target = el.scrollLeft + dir * stepBy;
  if (dir === 1 && el.scrollLeft >= max - 4) target = 0;
  else target = Math.max(0, Math.min(max, target));
  animateScrollLeft(el, target);
}
