"use client";

import { useEffect, useRef } from "react";

const GRID = 36; // keep in sync with --grid
const SETTLE_MS = 520;
const NEAR = [-1, 0, 1].flatMap((dx) => [-1, 0, 1].map((dy) => [dx, dy] as const)).filter(([x, y]) => x || y);

const SOLID = "img, svg, canvas, video, input, textarea, select, button, a, label, figure, details, table";
const clearCache = new WeakMap<Element, boolean>();

/** True when an element is bare background: transparent, no text of its own, not content. */
function isBackground(el: Element | null): boolean {
  if (!el) return true;
  const known = clearCache.get(el);
  if (known !== undefined) return known;
  const ownText = [...el.childNodes].some((n) => n.nodeType === Node.TEXT_NODE && n.textContent?.trim());
  const bg = getComputedStyle(el).backgroundColor;
  const clear =
    el === document.body ||
    el === document.documentElement ||
    (!ownText && !el.matches(SOLID) && (bg === "transparent" || bg === "rgba(0, 0, 0, 0)"));
  clearCache.set(el, clear);
  return clear;
}

/** A square may rise only if nothing but empty layout sits over its centre and corners. */
function squareIsEmpty(col: number, row: number): boolean {
  const x0 = col * GRID - scrollX;
  const y0 = row * GRID - scrollY;
  const pts = [
    [GRID / 2, GRID / 2],
    [4, 4],
    [GRID - 4, 4],
    [4, GRID - 4],
    [GRID - 4, GRID - 4],
  ];
  return pts.every(([dx, dy]) => isBackground(document.elementFromPoint(x0 + dx!, y0 + dy!)));
}

/**
 * The sketchpad grid's empty squares rise into 3D blocks under the mouse (neighbours lift a little)
 * and sink back after it leaves. Squares behind text or content stay flat.
 * Only live tiles exist in the DOM (a handful at a time); everything else is the CSS grid background.
 */
export function TileField() {
  const layer = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = layer.current;
    if (!el || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const live = new Map<string, HTMLSpanElement>();
    let raised: string[] = [];

    const tile = (col: number, row: number) => {
      const key = `${col}:${row}`;
      let t = live.get(key);
      if (!t) {
        t = document.createElement("span");
        t.className = "tile";
        t.style.transform = `translate(${col * GRID - 1}px, ${row * GRID - 1}px)`;
        el.appendChild(t);
        live.set(key, t);
      }
      return t;
    };

    const sink = (key: string) => {
      const t = live.get(key);
      if (!t) return;
      t.classList.remove("up", "near");
      setTimeout(() => {
        if (!t.classList.contains("up") && !t.classList.contains("near")) {
          t.remove();
          live.delete(key);
        }
      }, SETTLE_MS);
    };

    let current = "";
    const onMove = (e: PointerEvent) => {
      if (e.pointerType !== "mouse") return;
      const col = Math.floor((e.pageX + 1) / GRID);
      const row = Math.floor((e.pageY + 1) / GRID);
      const key = `${col}:${row}`;
      if (key === current) return;
      current = key;
      // The hovered square rises fully; its 8 neighbours lift a little. Squares under content stay flat.
      const cells = [[col, row] as const, ...NEAR.map(([dx, dy]) => [col + dx, row + dy] as const)].map(
        ([c, r], i) => ({ c, r, key: `${c}:${r}`, main: i === 0 }),
      );
      const free = squareIsEmpty(col, row) ? cells.filter((x) => squareIsEmpty(x.c, x.r)) : [];
      const next = free.map((x) => x.key);
      raised.filter((k) => !next.includes(k)).forEach(sink);
      const els = free.map((x) => [tile(x.c, x.r), x.main] as const);
      raised = next;
      requestAnimationFrame(() =>
        els.forEach(([t, main]) => {
          t.classList.toggle("up", main);
          t.classList.toggle("near", !main);
        }),
      );
    };
    const onLeave = () => {
      raised.forEach(sink);
      raised = [];
      current = "";
    };

    window.addEventListener("pointermove", onMove, { passive: true });
    document.documentElement.addEventListener("pointerleave", onLeave);
    return () => {
      window.removeEventListener("pointermove", onMove);
      document.documentElement.removeEventListener("pointerleave", onLeave);
      live.forEach((t) => t.remove());
    };
  }, []);

  return <div ref={layer} className="tile-field" aria-hidden />;
}
