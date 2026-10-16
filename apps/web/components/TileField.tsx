"use client";

import { useEffect, useRef } from "react";

const GRID = 36; // keep in sync with --grid
const SETTLE_MS = 520;

/**
 * The sketchpad grid's squares rise into 3D blocks under the mouse and sink back after it leaves.
 * Only live tiles exist in the DOM (a handful at a time); everything else is the CSS grid background.
 */
export function TileField() {
  const layer = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = layer.current;
    if (!el || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const live = new Map<string, HTMLSpanElement>();
    let current = "";

    const sink = (key: string) => {
      const t = live.get(key);
      if (!t) return;
      t.classList.remove("up");
      setTimeout(() => {
        if (!t.classList.contains("up")) {
          t.remove();
          live.delete(key);
        }
      }, SETTLE_MS);
    };

    const onMove = (e: PointerEvent) => {
      if (e.pointerType !== "mouse") return;
      const col = Math.floor((e.pageX + 1) / GRID);
      const row = Math.floor((e.pageY + 1) / GRID);
      const key = `${col}:${row}`;
      if (key === current) return;
      if (current) sink(current);
      current = key;
      let t = live.get(key);
      if (!t) {
        t = document.createElement("span");
        t.className = "tile";
        t.style.transform = `translate(${col * GRID - 1}px, ${row * GRID - 1}px)`;
        el.appendChild(t);
        live.set(key, t);
      }
      const tile = t;
      requestAnimationFrame(() => tile.classList.add("up"));
    };
    const onLeave = () => {
      if (current) sink(current);
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
