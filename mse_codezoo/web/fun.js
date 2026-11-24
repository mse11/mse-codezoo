// The fun pass: sounds, confetti, collect combos, popping stars, a solve streak and an
// animal that likes to be poked. Nothing here changes what the engine checks or saves;
// it only reacts to the run that the engine sent back.
//
// Sounds are made on the spot with Web Audio (no files, so it works offline) and follow
// the "Sounds" switch in Look and feel. Confetti and floating texts follow "less motion".
// Nothing is recorded or sent.

import { t } from "./i18n.js";
import { isLocked, look, reducedMotion, setLook } from "./look.js";
import { EMOJI } from "./stage.js";

// --- sounds ---------------------------------------------------------------------------

let ctx = null;
function audio() {
  if (!look().sounds) return null;
  if (!ctx) {
    const Context = window.AudioContext || window.webkitAudioContext;
    if (!Context) return null;
    try {
      ctx = new Context();
    } catch {
      return null;
    }
  }
  if (ctx.state === "suspended") ctx.resume().catch(() => {});
  return ctx;
}

// one note: a frequency (optionally sliding to `to`), a wave and a short envelope
function tone({ freq, to, type = "sine", dur = 0.12, vol = 0.12, delay = 0 }) {
  const a = audio();
  if (!a) return;
  const start = a.currentTime + delay;
  const osc = a.createOscillator();
  const gain = a.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, start);
  if (to) osc.frequency.exponentialRampToValueAtTime(to, start + dur);
  gain.gain.setValueAtTime(0.0001, start);
  gain.gain.exponentialRampToValueAtTime(vol, start + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.0001, start + dur);
  osc.connect(gain).connect(a.destination);
  osc.start(start);
  osc.stop(start + dur + 0.02);
}

// a puff of filtered noise: whooshes, cracks and rustles
function puff({ dur = 0.25, vol = 0.08, from = 400, to = 2400, q = 1.5, delay = 0 }) {
  const a = audio();
  if (!a) return;
  const start = a.currentTime + delay;
  const length = Math.ceil(a.sampleRate * dur);
  const buffer = a.createBuffer(1, length, a.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < length; i++) data[i] = Math.random() * 2 - 1;
  const source = a.createBufferSource();
  source.buffer = buffer;
  const filter = a.createBiquadFilter();
  filter.type = "bandpass";
  filter.Q.value = q;
  filter.frequency.setValueAtTime(from, start);
  filter.frequency.exponentialRampToValueAtTime(to, start + dur);
  const gain = a.createGain();
  gain.gain.setValueAtTime(0.0001, start);
  gain.gain.exponentialRampToValueAtTime(vol, start + dur * 0.3);
  gain.gain.exponentialRampToValueAtTime(0.0001, start + dur);
  source.connect(filter).connect(gain).connect(a.destination);
  source.start(start);
  source.stop(start + dur + 0.02);
}

// a happy scale, so a row of collected items climbs like a little tune
const SCALE = [523, 587, 659, 784, 880, 1047, 1175, 1319, 1568, 1760, 2093];

let foot = 0;
export const sfx = {
  start() {
    tone({ freq: 330, to: 660, type: "triangle", dur: 0.12, vol: 0.07 });
  },
  step() {
    foot = 1 - foot;
    tone({ freq: foot ? 240 : 200, to: foot ? 180 : 150, type: "triangle", dur: 0.07, vol: 0.07 });
  },
  turn() {
    puff({ dur: 0.14, vol: 0.05, from: 600, to: 1800 });
  },
  grab(combo = 1) {
    const note = SCALE[Math.min(combo - 1, SCALE.length - 1)];
    tone({ freq: note * 0.75, to: note, type: "sine", dur: 0.08, vol: 0.12 });
    tone({ freq: note * 2, type: "sine", dur: 0.18, vol: 0.05, delay: 0.06 });
  },
  miss() {
    tone({ freq: 420, to: 360, type: "triangle", dur: 0.12, vol: 0.07 });
    tone({ freq: 380, to: 300, type: "triangle", dur: 0.16, vol: 0.07, delay: 0.13 });
  },
  bump() {
    tone({ freq: 260, to: 70, type: "sine", dur: 0.3, vol: 0.16 });
    tone({ freq: 140, to: 90, type: "square", dur: 0.08, vol: 0.03 });
  },
  whoosh() {
    puff({ dur: 0.35, vol: 0.09, from: 300, to: 3000, q: 2 });
  },
  build() {
    tone({ freq: 150, to: 110, type: "square", dur: 0.06, vol: 0.06 });
    tone({ freq: 150, to: 110, type: "square", dur: 0.06, vol: 0.06, delay: 0.12 });
  },
  crack() {
    puff({ dur: 0.18, vol: 0.12, from: 3000, to: 900, q: 0.8 });
  },
  hide() {
    tone({ freq: 900, to: 300, type: "sine", dur: 0.3, vol: 0.06 });
  },
  say(text = "") {
    const blips = Math.min(4, Math.max(2, Math.ceil(text.length / 6)));
    for (let i = 0; i < blips; i++) {
      tone({ freq: 700 + Math.random() * 500, type: "square", dur: 0.05, vol: 0.025, delay: i * 0.07 });
    }
  },
  sense() {
    tone({ freq: 1200, to: 1600, type: "sine", dur: 0.06, vol: 0.04 });
    tone({ freq: 1400, to: 1800, type: "sine", dur: 0.06, vol: 0.04, delay: 0.08 });
  },
  star(index) {
    const note = [1047, 1319, 1568][index] || 1568;
    tone({ freq: note, type: "triangle", dur: 0.35, vol: 0.09 });
    tone({ freq: note * 2, type: "sine", dur: 0.25, vol: 0.03, delay: 0.02 });
  },
  win(big) {
    const notes = big ? [523, 659, 784, 1047, 784, 1047, 1319] : [523, 659, 784, 1047];
    notes.forEach((freq, i) => tone({ freq, type: "triangle", dur: 0.22, vol: 0.1, delay: i * 0.09 }));
    tone({ freq: 262, type: "sine", dur: 0.5, vol: 0.08, delay: notes.length * 0.09 - 0.05 });
  },
  oops() {
    // not a buzzer: a soft, curious "boo-bwoop?"
    tone({ freq: 392, to: 330, type: "sine", dur: 0.18, vol: 0.08 });
    tone({ freq: 330, to: 440, type: "sine", dur: 0.22, vol: 0.08, delay: 0.2 });
  },
  sticker() {
    for (let i = 0; i < 8; i++) tone({ freq: 880 + i * 160, type: "sine", dur: 0.12, vol: 0.05, delay: i * 0.04 });
  },
  poke() {
    tone({ freq: 700 + Math.random() * 300, to: 1500, type: "sine", dur: 0.09, vol: 0.09 });
    tone({ freq: 1400, to: 900, type: "sine", dur: 0.12, vol: 0.07, delay: 0.09 });
  },
  secret() {
    [784, 988, 1175, 1568, 1175, 1568, 2093].forEach((freq, i) => tone({ freq, type: "square", dur: 0.1, vol: 0.04, delay: i * 0.08 }));
  },
};

// --- the layer over the page: confetti, floating texts, banners --------------------------

let layer = null;
function funLayer() {
  if (!layer || !layer.isConnected) {
    layer = document.createElement("div");
    layer.className = "fun-layer";
    layer.setAttribute("aria-hidden", "true");
    document.body.append(layer);
  }
  return layer;
}

// "+1 🍌" rising from the animal
export function floatText(point, text, kind = "") {
  if (!point) return;
  const node = document.createElement("div");
  node.className = `fun-float ${kind}`;
  node.textContent = text;
  node.style.left = `${point.x}px`;
  node.style.top = `${point.y}px`;
  funLayer().append(node);
  setTimeout(() => node.remove(), 1300);
}

// a big friendly banner across the stage ("3 levels in a row!")
export function banner(text, near) {
  const node = document.createElement("div");
  node.className = "fun-banner";
  node.textContent = text;
  if (near) {
    const box = near.getBoundingClientRect();
    node.style.left = `${box.left + box.width / 2}px`;
    node.style.top = `${box.top + Math.min(box.height * 0.3, 140)}px`;
  }
  funLayer().append(node);
  setTimeout(() => node.remove(), 2600);
}

const COLORS = ["#ffcf33", "#ff6b6b", "#4dabf7", "#69db7c", "#b197fc", "#ff922b", "#f783ac"];

// confetti from a point on the screen; some pieces are the level's own emoji
export function confetti(origin, { count = 90, emoji = [] } = {}) {
  if (reducedMotion()) return;
  const canvas = document.createElement("canvas");
  canvas.className = "fun-confetti";
  const scale = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = innerWidth * scale;
  canvas.height = innerHeight * scale;
  funLayer().append(canvas);
  const g = canvas.getContext("2d");
  if (!g) return canvas.remove();
  g.scale(scale, scale);
  const pieces = Array.from({ length: count }, (_, i) => {
    const angle = -Math.PI / 2 + (Math.random() - 0.5) * Math.PI * 1.2;
    const speed = 6 + Math.random() * 9;
    return {
      x: origin.x, y: origin.y,
      vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed,
      spin: Math.random() * Math.PI, vs: (Math.random() - 0.5) * 0.4,
      size: 6 + Math.random() * 7,
      color: COLORS[i % COLORS.length],
      emoji: emoji.length && i % 6 === 0 ? emoji[i % emoji.length] : null,
    };
  });
  const started = performance.now();
  let last = started;
  const frame = (now) => {
    const age = now - started;
    // move by the time that passed (in 60 fps ticks), so slow tablets see the same burst
    const ticks = Math.min(Math.round((now - last) / 16.7), 40);
    last = now;
    g.clearRect(0, 0, innerWidth, innerHeight);
    for (const p of pieces) {
      for (let k = 0; k < ticks; k++) {
        p.vy += 0.28;
        p.vx *= 0.985;
        p.x += p.vx;
        p.y += p.vy;
        p.spin += p.vs;
      }
      g.save();
      g.globalAlpha = Math.max(0, 1 - age / 2600);
      g.translate(p.x, p.y);
      g.rotate(p.spin);
      if (p.emoji) {
        g.font = `${p.size * 3}px system-ui, "Segoe UI Emoji", "Apple Color Emoji", sans-serif`;
        g.textAlign = "center";
        g.textBaseline = "middle";
        g.fillText(p.emoji, 0, 0);
      } else {
        g.fillStyle = p.color;
        g.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2);
      }
      g.restore();
    }
    if (age < 2600) requestAnimationFrame(frame);
    else canvas.remove();
  };
  requestAnimationFrame(frame);
}

// --- poking the animal --------------------------------------------------------------

// each line is its own t() call, so the Slovak check finds it
const POKES = [
  () => t("Hee hee, that tickles!"),
  () => t("Boop!"),
  () => t("Let's write some code!"),
  () => t("Wheee!"),
  () => t("Again! Again!"),
  () => t("Hello, programmer!"),
  () => t("Psst… blocks can go inside a loop!"),
  () => t("I'm ready when you are!"),
  () => t("Do I have something on my nose?"),
  () => t("Ready, steady… Run!"),
];
const SECRET_POKES = 10;

// --- the conductor: app.js tells it what happens -----------------------------------------

export class Fun {
  constructor({ getStage, stageBox }) {
    this.getStage = getStage; // the stage on screen (2D or 3D)
    this.stageBox = stageBox; // the stage's element, for banners and confetti
    this.combo = 0;
    this.solvedToday = new Set(); // levels solved since the page opened (not saved)
    this.pokes = 0;
    this.lastPokeLine = -1;
  }

  pack() {
    return this.getStage()?.level?.pack;
  }

  itemEmoji(tile) {
    const noun = this.pack()?.items?.[tile];
    return EMOJI[noun] || "⭐";
  }

  where() {
    try {
      return this.getStage()?.animalPoint?.() || null;
    } catch {
      return null;
    }
  }

  runStarted() {
    this.combo = 0;
    sfx.start();
  }

  // one world event, just before the stage plays it
  event(event) {
    switch (event.type) {
      case "move":
        if (event.slide) sfx.whoosh();
        else sfx.step();
        break;
      case "turn":
        sfx.turn();
        break;
      case "grab":
        if (event.item) {
          this.combo += 1;
          sfx.grab(this.combo);
          // the animal is where the item was, except for the octopus's long arms
          const point = event.arm === undefined ? this.where() : null;
          floatText(point, `+1 ${this.itemEmoji(event.item)}`);
          if (this.combo >= 3 && point) {
            setTimeout(() => floatText({ x: point.x + 34, y: point.y - 18 }, `×${this.combo}!`, "combo"), 120);
          }
        } else {
          this.combo = 0;
          sfx.miss();
        }
        break;
      case "bump":
        this.combo = 0;
        sfx.bump();
        floatText(this.where(), "💫", "bonk");
        break;
      case "fly":
      case "swing":
        sfx.whoosh();
        break;
      case "climb":
        sfx.sense();
        break;
      case "build":
        sfx.build();
        break;
      case "crack":
        sfx.crack();
        break;
      case "hide":
        sfx.hide();
        break;
      case "say":
        sfx.say(event.text);
        break;
      case "sense":
        sfx.sense();
        break;
      default:
    }
  }

  // the run is over and the result is on screen
  finished(run, resultNode) {
    const solved = Boolean(run.check?.solved);
    const earned = run.check ? run.check.stars.filter((s) => s.earned).length : 0;
    this.popStars(resultNode, earned);
    if (!solved) {
      sfx.oops();
      return;
    }
    const big = earned >= 3;
    sfx.win(big);
    const box = this.stageBox.getBoundingClientRect();
    const origin = this.where() || { x: box.left + box.width / 2, y: box.top + box.height / 2 };
    const pack = this.pack();
    const emoji = [
      ...new Set([pack?.emoji || EMOJI[pack?.animal], ...Object.values(pack?.items || {}).map((n) => EMOJI[n]), "⭐"].filter(Boolean)),
    ];
    confetti(origin, { count: big ? 140 : 70, emoji: big ? emoji : ["⭐"] });
    if (big) setTimeout(() => confetti({ x: box.left + box.width * 0.15, y: box.bottom }, { count: 50, emoji }), 350);
    if (big) setTimeout(() => confetti({ x: box.left + box.width * 0.85, y: box.bottom }, { count: 50, emoji }), 600);

    const level = run.level || this.getStage()?.level?.id;
    const fresh = level && !this.solvedToday.has(level);
    if (level) this.solvedToday.add(level);
    const n = this.solvedToday.size;
    if (fresh && n >= 2) {
      setTimeout(() => banner(t("🔥 {n} levels solved! You're on fire!", { n }), this.stageBox), 900);
    } else if (big) {
      setTimeout(() => banner(t("⭐ ⭐ ⭐ Perfect!"), this.stageBox), 700);
    }
    if (run.newStickers?.length) setTimeout(() => sfx.sticker(), 1300);
  }

  // the result's stars appear one by one, each with a ding
  popStars(resultNode, earned) {
    const stars = resultNode?.querySelector(".stars");
    if (!stars) return;
    const text = stars.textContent;
    stars.replaceChildren(
      ...[...text].map((ch, i) => {
        const span = document.createElement("span");
        span.className = `star ${ch === "★" ? "earned" : "empty"}`;
        span.style.animationDelay = `${0.25 + i * 0.28}s`;
        span.textContent = ch;
        return span;
      }),
    );
    for (let i = 0; i < earned; i++) setTimeout(() => sfx.star(i), 250 + i * 280);
  }

  // a tap on the animal while nothing is running
  poke() {
    const stage = this.getStage();
    if (!stage?.poke) return;
    this.pokes += 1;
    sfx.poke();
    if (this.pokes % SECRET_POKES === 0) {
      sfx.secret();
      stage.poke(t("🎉 You found my secret dance!"), { dance: true });
      const point = this.where();
      if (point) confetti(point, { count: 40, emoji: ["🎉", "💃", "🕺", "⭐"] });
      return;
    }
    let line;
    do line = Math.floor(Math.random() * POKES.length);
    while (line === this.lastPokeLine && POKES.length > 1);
    this.lastPokeLine = line;
    stage.poke(POKES[line]());
    floatText(this.where(), ["💛", "✨", "😆", "💚", "🎈"][this.pokes % 5], "heart");
  }
}

// the 🎵 button in the header: sounds on or off (the same switch as in Look and feel)
export function setupSoundButton(button) {
  const show = () => {
    const on = look().sounds;
    button.hidden = isLocked("sounds"); // the teacher decides for the class
    button.textContent = on ? "🎵" : "🔇";
    button.setAttribute("aria-pressed", String(on));
    const label = on ? t("Sounds on") : t("Sounds off");
    button.title = label;
    button.setAttribute("aria-label", label);
  };
  button.addEventListener("click", () => {
    if (isLocked("sounds")) return;
    setLook({ sounds: !look().sounds });
    if (look().sounds) sfx.poke();
  });
  window.addEventListener("codezoo-look", show);
  show();
  return show;
}
