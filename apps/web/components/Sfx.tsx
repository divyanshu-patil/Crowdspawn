"use client";

import { useEffect, useState } from "react";
import { isMuted, onMuteChange, play, setMuted, type Sound } from "../lib/sfx";

const INTERACTIVE = "button, a[href], summary, [role=tab], [role=button], label.toggle, label.chip, g.pin";

/** Each kind of control has its own sound. */
function soundFor(el: Element): Sound {
  const label = el.getAttribute("aria-label") ?? "";
  if (el.matches("g.pin, .map-board button")) return "pin";
  if (label === "Zoom in") return "zoomIn";
  if (label === "Zoom out" || label === "Reset map view") return "zoomOut";
  if (el.matches("[role=tab]")) return "tab";
  if (el.matches(".chip button") || label.startsWith("Remove ")) return "remove";
  if (el.matches("a.cite, .textlink")) return "pop";
  if (el.matches("a[href]")) return "nav";
  if (el.matches(".btn")) return "confirm";
  return "click";
}

/** One document-level listener gives every control a sound; `data-sfx` overrides the default. */
export function SfxListener() {
  useEffect(() => {
    let hovered: Element | null = null;
    const onClick = (e: MouseEvent) => {
      const t = e.target as Element | null;
      if (t instanceof HTMLInputElement && t.closest("label")) return; // the label's synthetic re-click
      const el = t?.closest(INTERACTIVE);
      if (!el || el.matches(":disabled, [aria-disabled=true]")) return;
      const named = el.getAttribute("data-sfx") as Sound | null;
      if (named) return play(named);
      const box = el.querySelector<HTMLInputElement>("input[type=checkbox]");
      if (box) return play(box.checked ? "off" : "on"); // capture phase: state before the toggle
      if (el.matches("summary")) return play((el.parentElement as HTMLDetailsElement).open ? "back" : "select");
      play(soundFor(el));
    };
    const onOver = (e: PointerEvent) => {
      if (e.pointerType !== "mouse") return;
      const el = (e.target as Element | null)?.closest(INTERACTIVE) ?? null;
      if (el && el !== hovered && !el.matches(":disabled")) play("hover");
      hovered = el;
    };
    document.addEventListener("click", onClick, true);
    document.addEventListener("pointerover", onOver, { passive: true });
    return () => {
      document.removeEventListener("click", onClick, true);
      document.removeEventListener("pointerover", onOver);
    };
  }, []);
  return null;
}

export function SoundToggle() {
  const [muted, setState] = useState(false);
  useEffect(() => {
    setState(isMuted());
    return onMuteChange(setState);
  }, []);
  return (
    <button
      className="sfx-toggle label"
      aria-pressed={!muted}
      data-sfx="off"
      onClick={() => {
        setMuted(!muted);
        if (muted) play("on"); // the capture listener ran while still muted
      }}
      title={muted ? "Turn game sounds on" : "Turn game sounds off"}
    >
      <span className={`sfx-bars${muted ? "" : " live"}`} aria-hidden>
        <i />
        <i />
        <i />
      </span>
      Sound {muted ? "off" : "on"}
    </button>
  );
}
