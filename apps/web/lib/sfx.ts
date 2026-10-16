// 8-bit sound effects synthesised with the Web Audio API: no audio files, so nothing to license.
// Browsers only allow audio after a user gesture; every sound here follows a click or key press.

type Wave = OscillatorType;
type Note = { f: number; to?: number; at?: number; len: number; wave?: Wave; vol?: number };

const SOUNDS = {
  // UI
  hover: [{ f: 2400, len: 0.018, wave: "sine", vol: 0.025 }],
  click: [{ f: 660, to: 990, len: 0.05, wave: "square", vol: 0.05 }],
  back: [{ f: 520, to: 330, len: 0.07, wave: "square", vol: 0.045 }],
  on: [
    { f: 523, len: 0.05, wave: "square", vol: 0.05 },
    { f: 784, at: 0.05, len: 0.07, wave: "square", vol: 0.05 },
  ],
  off: [
    { f: 784, len: 0.05, wave: "square", vol: 0.045 },
    { f: 392, at: 0.05, len: 0.08, wave: "square", vol: 0.045 },
  ],
  nav: [{ f: 330, to: 990, len: 0.11, wave: "triangle", vol: 0.12 }],
  confirm: [
    { f: 523, len: 0.06, wave: "square", vol: 0.05 },
    { f: 659, len: 0.06, wave: "square", vol: 0.04 },
    { f: 1047, at: 0.06, len: 0.12, wave: "square", vol: 0.05 },
  ],
  pop: [{ f: 1400, to: 700, len: 0.045, wave: "sine", vol: 0.12 }],
  tab: [
    { f: 880, len: 0.035, wave: "triangle", vol: 0.1 },
    { f: 1175, at: 0.035, len: 0.05, wave: "triangle", vol: 0.1 },
  ],
  remove: [{ f: 700, to: 180, len: 0.12, wave: "sawtooth", vol: 0.04 }],
  pin: [
    { f: 1568, len: 0.05, wave: "triangle", vol: 0.1 },
    { f: 2093, at: 0.05, len: 0.16, wave: "sine", vol: 0.08 },
  ],
  zoomIn: [{ f: 400, to: 1200, len: 0.09, wave: "square", vol: 0.035 }],
  zoomOut: [{ f: 1200, to: 400, len: 0.09, wave: "square", vol: 0.035 }],
  // Game moments
  coin: [
    { f: 988, len: 0.06, wave: "square", vol: 0.05 },
    { f: 1319, at: 0.06, len: 0.18, wave: "square", vol: 0.05 },
  ],
  select: [{ f: 440, to: 1760, len: 0.12, wave: "triangle", vol: 0.09 }],
  tick: [{ f: 1200, len: 0.03, wave: "triangle", vol: 0.05 }],
  level: [
    { f: 392, len: 0.07, wave: "square", vol: 0.05 },
    { f: 523, at: 0.07, len: 0.07, wave: "square", vol: 0.05 },
    { f: 659, at: 0.14, len: 0.12, wave: "square", vol: 0.05 },
  ],
  win: [
    { f: 523, len: 0.09, wave: "square", vol: 0.05 },
    { f: 659, at: 0.09, len: 0.09, wave: "square", vol: 0.05 },
    { f: 784, at: 0.18, len: 0.09, wave: "square", vol: 0.05 },
    { f: 1047, at: 0.27, len: 0.3, wave: "square", vol: 0.055 },
    { f: 1047, at: 0.27, len: 0.3, wave: "triangle", vol: 0.08 },
  ],
  error: [
    { f: 196, len: 0.12, wave: "sawtooth", vol: 0.05 },
    { f: 147, at: 0.12, len: 0.22, wave: "sawtooth", vol: 0.05 },
  ],
} satisfies Record<string, Note[]>;

export type Sound = keyof typeof SOUNDS;

const KEY = "crowdspawn:sfx";
let ctx: AudioContext | null = null;
let out: GainNode | null = null;
let muted: boolean | null = null;
const listeners = new Set<(m: boolean) => void>();

export function isMuted(): boolean {
  if (muted === null) {
    try {
      muted = localStorage.getItem(KEY) === "off";
    } catch {
      muted = false;
    }
  }
  return muted;
}

export function setMuted(m: boolean) {
  muted = m;
  try {
    localStorage.setItem(KEY, m ? "off" : "on");
  } catch {
    /* storage blocked: keep the choice for this page only */
  }
  listeners.forEach((l) => l(m));
}

export function onMuteChange(l: (m: boolean) => void): () => void {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

function audio(): { c: AudioContext; o: GainNode } | null {
  if (typeof window === "undefined" || !("AudioContext" in window)) return null;
  if (!ctx) {
    ctx = new AudioContext();
    const soften = ctx.createBiquadFilter(); // take the harsh edge off square waves
    soften.type = "lowpass";
    soften.frequency.value = 5200;
    out = ctx.createGain();
    out.gain.value = 2.6; // notes are written quiet; this sets the overall loudness
    out.connect(soften).connect(ctx.destination);
  }
  return { c: ctx, o: out! };
}

let lastHover = 0;

export function play(sound: Sound) {
  if (isMuted()) return;
  if (sound === "hover") {
    const now = performance.now();
    if (now - lastHover < 60) return;
    lastHover = now;
  }
  const a = audio();
  if (!a) return;
  if (a.c.state !== "running") {
    if (sound !== "hover") void a.c.resume().then(() => schedule(a, sound));
    return;
  }
  schedule(a, sound);
}

function schedule(a: { c: AudioContext; o: GainNode }, sound: Sound) {
  const t0 = a.c.currentTime + 0.005;
  for (const n of SOUNDS[sound] as Note[]) {
    const osc = a.c.createOscillator();
    const env = a.c.createGain();
    const start = t0 + (n.at ?? 0);
    osc.type = n.wave ?? "square";
    osc.frequency.setValueAtTime(n.f, start);
    if (n.to) osc.frequency.exponentialRampToValueAtTime(n.to, start + n.len);
    env.gain.setValueAtTime(0.0001, start);
    env.gain.exponentialRampToValueAtTime(n.vol ?? 0.05, start + 0.004);
    env.gain.exponentialRampToValueAtTime(0.0001, start + n.len);
    osc.connect(env).connect(a.o);
    osc.start(start);
    osc.stop(start + n.len + 0.02);
  }
}

