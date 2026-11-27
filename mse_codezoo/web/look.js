// "Look and feel" (phase 6, accessibility basics): text size, easy-to-read text, high
// contrast, less motion and big targets (bigger blocks and buttons, tap a block in the
// palette to add it). Kept in this browser only and applied as attributes on <html>, so
// every page (game, editor, teacher's screen) can follow them with CSS.

import { t } from "./i18n.js";
import { icon } from "./icons.js";
import { animalSay, canSpeak, isCub, isMuted, setMuted, speak, voiceLabel } from "./speech.js";
import { resetAllZoom } from "./zoom.js";

const KEY = "codezoo.look";
const LOCK_KEY = "codezoo.look.locked"; // the teacher's colours (early-look.js)
const DEFAULTS = {
  text: "normal", easy: false, contrast: false, motion: "system", targets: false, read: false, sounds: true,
  theme: "system", // colours: "system" (as the device), "light" or "dark"
  layout: "auto", // goal and result: "above" the stage, "side" (beside it) or "auto" (by window width)
  graphics: "auto", // 3D detail: "high", "medium", "low" or "auto" (guessed, lowered when it runs slowly)
  sayVoice: true, // the animals speak their say("...") lines aloud (with Sounds on)
  voiceSpeed: "normal", // how fast reading aloud and say() speak: "slow", "normal", "quick"
  animalVoice: "natural", // how the animals' say() sounds: "natural", "higher", "squeaky"
};

function read() {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || "{}") };
  } catch {
    return { ...DEFAULTS };
  }
}

let settings = read();
// settings a classroom's teacher decides for this device (`sounds`, `theme`): they win
// over the child's own choice, and Look and feel shows them as set by the teacher
let locked = {};

export function look() {
  return { ...settings, ...locked };
}

// a value locks that setting; null unlocks it (the child's own choice again)
export function lockLook(next) {
  const merged = { ...locked, ...next };
  locked = Object.fromEntries(Object.entries(merged).filter(([, value]) => value !== null && value !== undefined));
  // the teacher's colours are remembered on this device, so early-look.js can put them on
  // the next page before it is drawn (no flash of the child's own colours first). Pages
  // from the hub have the hub's own address, so this never reaches the child's own zoo.
  try {
    if (locked.theme) localStorage.setItem(LOCK_KEY, JSON.stringify({ theme: locked.theme }));
    else localStorage.removeItem(LOCK_KEY);
  } catch {
    // storage blocked: the lock comes a moment after the page loads, as before
  }
  applyLook();
}

export function isLocked(key) {
  return key in locked;
}

// "automatic" layout: the goal and result beside the stage once the window is this wide,
// or on a landscape window from 1000px (a laptop or a tablet held sideways: height is short, so the goal
// goes to the side and the stage keeps its height)
const wideWindow = window.matchMedia("(min-width: 1300px), (min-width: 1000px) and (min-aspect-ratio: 4/3)");
export function layout() {
  const chosen = look().layout;
  if (chosen === "above" || chosen === "side") return chosen;
  return wideWindow.matches ? "side" : "above";
}

// less motion: the setting here, or the system's "reduce motion"
const systemReduce = window.matchMedia("(prefers-reduced-motion: reduce)");
export function reducedMotion() {
  return settings.motion === "reduce" || (settings.motion === "system" && systemReduce.matches);
}

// 3D detail. "auto" starts from what the device reports (cores, memory) and the 3D stage
// lowers it by a step when frames come slowly (lowerGraphics), for the rest of the visit.
const GRAPHICS = ["low", "medium", "high"];
let slowSteps = 0;
function guessGraphics() {
  const cores = navigator.hardwareConcurrency || 4;
  const memory = navigator.deviceMemory || 4; // gigabytes, only some browsers say
  if (cores <= 2 || memory <= 2) return "low";
  if (cores <= 4 || memory <= 4) return "medium";
  return "high";
}
export function graphics() {
  const chosen = look().graphics;
  if (GRAPHICS.includes(chosen)) return chosen;
  return GRAPHICS[Math.max(0, GRAPHICS.indexOf(guessGraphics()) - slowSteps)];
}
// true when it went down a step (only in "auto", and not below "low")
export function lowerGraphics() {
  if (GRAPHICS.includes(look().graphics) || graphics() === "low") return false;
  slowSteps += 1;
  applyLook();
  return true;
}

export function applyLook() {
  const root = document.documentElement;
  root.dataset.text = settings.text;
  root.dataset.easy = String(settings.easy);
  root.dataset.contrast = String(settings.contrast);
  root.dataset.motion = reducedMotion() ? "reduce" : "full";
  root.dataset.targets = String(settings.targets);
  root.dataset.read = String(settings.read); // read aloud (speech.js, phase 7)
  root.dataset.sounds = String(look().sounds); // Sounds off: everything quiet, voices too (speech.js)
  root.dataset.layout = layout(); // style.css places the goal and result
  root.dataset.graphics = graphics(); // stage3d.js picks its detail
  root.dataset.voiceSpeed = settings.voiceSpeed; // speech.js reads both voice settings
  root.dataset.animalVoice = settings.animalVoice;
  // colours: style.css and the blocks follow data-theme; without it, the device's own
  const theme = look().theme;
  if (theme === "light" || theme === "dark") root.dataset.theme = theme;
  else delete root.dataset.theme;
  window.dispatchEvent(new CustomEvent("codezoo-look", { detail: settings }));
}

export function setLook(next) {
  save(next);
}

function save(next) {
  settings = { ...settings, ...next };
  try {
    localStorage.setItem(KEY, JSON.stringify(settings));
  } catch {
    // storage blocked: the setting lasts until the page is closed
  }
  applyLook();
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  node.append(...children.filter((child) => child !== null && child !== undefined));
  return node;
}

function checkbox(key, label) {
  const on = look()[key];
  const input = el("input", { type: "checkbox", ...(on ? { checked: "" } : {}), ...(isLocked(key) ? { disabled: "" } : {}) });
  input.addEventListener("change", () => save({ [key]: input.checked }));
  const note = isLocked(key) ? el("span", { class: "note" }, ` (${t("set by the teacher")})`) : null;
  return el("label", { class: "check" }, input, " ", el("span", {}, label), note);
}

function select(key, label, options) {
  const box = el("select", isLocked(key) ? { disabled: "" } : {}, ...options.map(([value, text]) => el("option", { value }, text)));
  box.value = look()[key];
  box.addEventListener("change", () => save({ [key]: box.value }));
  const note = isLocked(key) ? el("span", { class: "note" }, ` (${t("set by the teacher")})`) : null;
  return el("label", {}, el("span", {}, label), box, note);
}

// Read aloud uses the device's own voices; say so when there is none for this language
function voiceNote() {
  if (!("speechSynthesis" in window)) {
    return el("p", { class: "hint" }, t("This browser can't read aloud."));
  }
  if (!canSpeak()) {
    return el("p", { class: "hint" }, t("This device has no voice for this language, so nothing is read aloud. A voice can be added in the device's settings (speech or text-to-speech)."));
  }
  const test = el("button", { type: "button", class: "small", title: voiceLabel() }, t("Try the voice"));
  test.addEventListener("click", () => speak(t("Hello! I will read the goals to you."), { force: true }));
  return el("p", { class: "hint" }, test, " ", el("span", { class: "voice-name" }, voiceLabel()));
}

// The dialog is built here, so every page gets the same one from a single button.
// `advanced`: what the "🔒 Advanced" button at the end opens (the grown-ups' area, behind its
// grown-up check); left out where there is none (the teacher's screen, a classroom hub)
export function openLook({ advanced = null } = {}) {
  let dialog = document.getElementById("look-dialog");
  dialog?.remove();
  dialog = el(
    "dialog",
    { id: "look-dialog", class: "dialog", "aria-labelledby": "look-title" },
    el("h2", { id: "look-title" }, `⚙️ ${t("Settings")}`),
    select("text", t("Text size"), [
      ["normal", t("normal")],
      ["large", t("large")],
      ["larger", t("larger")],
    ]),
    select("theme", t("Colours"), [
      ["system", t("as this device is set")],
      ["light", t("☀️ light")],
      ["dark", t("🌙 dark")],
    ]),
    select("layout", t("Goal and result"), [
      ["auto", t("automatic: beside the stage on a wide screen")],
      ["above", t("above the stage")],
      ["side", t("beside the stage")],
    ]),
    checkbox("easy", t("Easy-to-read text (simple letters, more space)")),
    checkbox("contrast", t("High contrast")),
    select("motion", t("Motion"), [
      ["system", t("as this device is set")],
      ["reduce", t("less motion")],
      ["full", t("all animations")],
    ]),
    select("graphics", t("3D detail"), [
      ["auto", t("automatic: lower when the computer is slow")],
      ["high", t("high: smooth and shiny")],
      ["medium", t("medium")],
      ["low", t("low: for older computers")],
    ]),
    checkbox("targets", t("Big targets: bigger blocks and buttons; tap a block to add it")),
    checkbox("read", t("Read aloud: goals, hints, results and tapped blocks")),
    checkbox("sounds", t("Sounds: steps, pops and a little tune when you solve a level")),
    checkbox("sayVoice", t("Animal voice: the animals say their say() lines aloud")),
    select("voiceSpeed", t("Speaking speed"), [
      ["slow", t("slow")],
      ["normal", t("normal pace")],
      ["quick", t("quick")],
    ]),
    select("animalVoice", t("The animal's voice in say()"), [
      ["natural", t("natural")],
      ["higher", t("a bit higher")],
      ["squeaky", t("squeaky")],
    ]),
    voiceNote(),
    el(
      "p",
      { class: "hint" },
      el("button", { type: "button", class: "small", onclick: resetAllZoom }, t("Everything back to normal size")),
      " ",
      t("(Ctrl + mouse wheel zooms the part under the mouse)"),
    ),
    el("p", { class: "hint" }, t("These settings are kept in this browser only.")),
    el(
      "div",
      { class: "dialog-buttons" },
      advanced
        ? el("button", {
            type: "button",
            class: "advanced-button",
            title: t("For grown-ups: players, time limits and more"),
            onclick: () => {
              dialog.close();
              advanced();
            },
          }, `🔒 ${t("Advanced")}`)
        : null,
      el("button", { type: "button", class: "primary", onclick: () => dialog.close() }, t("Done")),
    ),
  );
  document.body.append(dialog);
  dialog.showModal();
}

// the ☀️/🌙 button in a page's header: switch between light and dark (the same setting as
// "Colours" above); hidden when a classroom's teacher picked the colours for everyone
const systemDark = window.matchMedia("(prefers-color-scheme: dark)");
export function isDark() {
  const theme = look().theme;
  return theme === "dark" || (theme !== "light" && systemDark.matches);
}

export function setupThemeButton(button) {
  if (!button) return;
  const show = () => {
    const dark = isDark();
    button.textContent = dark ? "🌙" : "☀️";
    button.hidden = isLocked("theme");
    const label = dark ? t("Dark colours: switch to light") : t("Light colours: switch to dark");
    button.title = label;
    button.setAttribute("aria-label", label);
  };
  button.addEventListener("click", () => {
    if (!isLocked("theme")) save({ theme: isDark() ? "light" : "dark" });
  });
  window.addEventListener("codezoo-look", show);
  systemDark.addEventListener("change", show);
  show();
}

// the small "3D detail" switch in a page's top bar (the same setting as in Look and feel):
// Auto, then low, medium and high drawn as signal bars, with a sliding knob like the modes
const DETAIL_LEVELS = { low: 1, medium: 2, high: 3 };
function detailLabel(level) {
  if (level === "low") return t("3D detail: low, for older computers");
  if (level === "medium") return t("3D detail: medium");
  if (level === "high") return t("3D detail: high, smooth and shiny");
  return t("3D detail: automatic, lower when the computer is slow");
}

export function setupGraphicsSwitch(holder, { name = true } = {}) {
  if (!holder) return;
  holder.className = "detail-switch";
  holder.setAttribute("role", "radiogroup");
  const buttons = ["auto", "low", "medium", "high"].map((value) => {
    const button = el("button", { type: "button", role: "radio", "data-level": value });
    if (value === "auto") button.textContent = "Auto";
    else {
      const bars = el("span", { class: "bars", "data-n": String(DETAIL_LEVELS[value]), "aria-hidden": "true" });
      bars.append(el("i"), el("i"), el("i"));
      button.append(bars);
    }
    button.addEventListener("click", () => save({ graphics: value }));
    return button;
  });
  const tag = name ? el("span", { class: "detail-name", "aria-hidden": "true" }, "3D") : null;
  holder.replaceChildren(...[tag, ...buttons].filter(Boolean));
  const show = () => {
    const chosen = look().graphics;
    holder.setAttribute("aria-label", t("3D detail"));
    for (const button of buttons) {
      const value = button.dataset.level;
      const on = value === chosen || (value === "auto" && !(chosen in DETAIL_LEVELS));
      button.setAttribute("aria-checked", String(on));
      // while Auto is on, it says which detail it picked for this computer
      const picked = detailLabel(graphics()).split(": ")[1] ?? graphics();
      const label = value === "auto" && on ? `${detailLabel("auto")} (${t("now")}: ${picked})` : detailLabel(value);
      button.title = label;
      button.setAttribute("aria-label", label);
    }
  };
  window.addEventListener("codezoo-look", show);
  new MutationObserver(show).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
  show();
}

// the sound button in a page's top bar: one button for everything you hear. Its picture
// shows what is on: 🎵 sounds (crossed out when everything is quiet), a little "say" bubble
// when the animals speak their say() lines, 🗣️ when the guide reads goals and hints aloud.
// A click opens a panel with those three switches and the voice settings (which voice,
// speaking speed, the animal's voice) and a button to hear them.
const VOICE_CHOICES = {
  voiceSpeed: [["slow", "🐢", "slow"], ["normal", "▶", "normal pace"], ["quick", "🐇", "quick"]],
  animalVoice: [["natural", "♪", "natural"], ["higher", "♪♪", "a bit higher"], ["squeaky", "♪♪♪", "squeaky"]],
};

// the guide voice: "Read aloud" in Look and feel; in Cub mode it is on unless muted
function guideOn() {
  return isCub() ? !isMuted() : Boolean(look().read);
}
function setGuide(on) {
  if (isCub()) {
    setMuted(!on);
    applyLook(); // the page redraws what depends on it (the goal's 🔈 button)
  } else {
    save({ read: on });
  }
}

export function setupSoundButton(button, { onSoundsOn = null } = {}) {
  if (!button) return null;
  button.classList.add("sound-button");
  // the button's picture: the note, then a badge for each voice that is on
  const note = icon("note");
  const sayBadge = el("span", { class: "snd-say", "aria-hidden": "true" }, "say");
  const guideBadge = icon("guide");
  button.replaceChildren(note, sayBadge, guideBadge);

  const panel = el("div", { class: "voice-panel sound-panel", popover: "auto", role: "dialog" });
  document.body.append(panel);
  // a switch row: its icon, its name and a small explanation; on/off like a light switch
  const toggle = (icon, onClick) => {
    const row = el("button", { type: "button", role: "switch", class: "snd-toggle" });
    const name = el("span", { class: "snd-toggle-name" });
    const hint = el("span", { class: "snd-toggle-hint" });
    row.append(el("span", { class: "snd-toggle-icon", "aria-hidden": "true" }, icon), el("span", { class: "snd-toggle-text" }, name, hint), el("span", { class: "snd-toggle-knob", "aria-hidden": "true" }));
    row.addEventListener("click", onClick);
    return { row, name, hint };
  };
  const sounds = toggle(icon("note"), () => {
    if (isLocked("sounds")) return;
    save({ sounds: !look().sounds });
    if (look().sounds) onSoundsOn?.();
  });
  const sayVoice = toggle(el("span", { class: "snd-say" }, "say"), () => save({ sayVoice: !look().sayVoice }));
  const guide = toggle(icon("guide"), () => setGuide(!guideOn()));
  const locked = el("p", { class: "hint" });

  const choice = (key) => {
    const group = el("span", { class: "detail-switch", role: "radiogroup" });
    for (const [value, icon, word] of VOICE_CHOICES[key]) {
      const option = el("button", { type: "button", role: "radio", "data-value": value }, icon);
      option.addEventListener("click", () => save({ [key]: value }));
      option.dataset.word = word;
      group.append(option);
    }
    return group;
  };
  const speed = choice("voiceSpeed");
  const animal = choice("animalVoice");
  const name = el("p", { class: "voice-name" });
  const speedLabel = el("span");
  const animalLabel = el("span");
  const tryIt = el("button", { type: "button", class: "small" });
  tryIt.addEventListener("click", () => animalSay(t("Hello! I am your animal. Listen to me.")));
  const voices = el("div", { class: "snd-voices" }, name, el("div", { class: "voice-row" }, speedLabel, speed), el("div", { class: "voice-row" }, animalLabel, animal), tryIt);
  panel.append(sounds.row, sayVoice.row, guide.row, locked, voices);

  const show = () => {
    const on = Boolean(look().sounds);
    const say = on && look().sayVoice;
    const reads = on && guideOn();
    // the picture
    button.classList.toggle("is-off", !on);
    sayBadge.hidden = !say;
    guideBadge.hidden = !reads;
    button.setAttribute("aria-pressed", String(on));
    const parts = [on ? t("Sounds on") : t("Sounds off")];
    if (say) parts.push(t("the animal speaks"));
    if (reads) parts.push(t("the guide reads aloud"));
    const label = parts.join(" · ");
    button.title = on && (say || reads) ? `${label}\n${voiceLabel()}` : label;
    button.setAttribute("aria-label", `${t("Sounds and voices")}: ${label}`);
    // the panel
    panel.setAttribute("aria-label", t("Sounds and voices"));
    const set = (item, checked, title, hint, disabled = false) => {
      item.row.setAttribute("aria-checked", String(checked));
      item.row.disabled = disabled;
      item.name.textContent = title;
      item.hint.textContent = hint;
    };
    set(sounds, on, t("Sounds"), t("steps, pops, a tune when you solve a level"), isLocked("sounds"));
    set(sayVoice, Boolean(look().sayVoice), t("Animal voice"), t("the animal says its say() lines"), !on);
    set(guide, guideOn(), t("Guide voice"), t("reads goals, hints and results"), !on);
    locked.textContent = isLocked("sounds") ? t("Sounds are set by the teacher.") : "";
    locked.hidden = !locked.textContent;
    voices.hidden = !(say || reads);
    name.textContent = voiceLabel();
    speedLabel.textContent = t("Speaking speed");
    animalLabel.textContent = t("The animal's voice in say()");
    tryIt.textContent = `▶ ${t("Try the voice")}`;
    for (const [key, group] of [["voiceSpeed", speed], ["animalVoice", animal]]) {
      group.setAttribute("aria-label", key === "voiceSpeed" ? t("Speaking speed") : t("The animal's voice in say()"));
      for (const option of group.children) {
        const word = t(option.dataset.word);
        option.title = word;
        option.setAttribute("aria-label", word);
        option.setAttribute("aria-checked", String(settings[key] === option.dataset.value));
      }
    }
  };
  // the button opens and closes the panel itself (a click outside closes it too)
  button.popoverTargetElement = panel;
  panel.addEventListener("beforetoggle", (event) => {
    if (event.newState !== "open") return;
    show();
    const box = button.getBoundingClientRect();
    panel.style.top = `${box.bottom + 6}px`;
    panel.style.left = `${box.left}px`;
    // keep it inside the window once its width is known (it is drawn right after this)
    requestAnimationFrame(() => {
      panel.style.left = `${Math.max(8, Math.min(box.left, innerWidth - panel.offsetWidth - 8))}px`;
    });
  });
  window.addEventListener("codezoo-look", show);
  window.addEventListener("codezoo-voices", show);
  show();
  return show;
}

// the stage button in a page's top bar: shows "2D" or "3D"; a click opens a small panel to
// switch the stage view and pick the 3D detail (like the 🗣️ voice panel). The page owns the
// view itself: `onPick("2d" | "3d")` asks for one, and the page tells the button what it
// shows with update({view, can3d, locked}) (no WebGL: no 3D; a teacher's single view: locked).
export function setupStageButton(button, { onPick }) {
  if (!button) return null;
  const now = { view: "2d", can3d: true, locked: null };
  const panel = el("div", { class: "voice-panel stage-panel", popover: "auto", role: "dialog" });
  document.body.append(panel);
  const views = el("span", { class: "detail-switch", role: "radiogroup" });
  const options = ["2d", "3d"].map((view) => {
    const option = el("button", { type: "button", role: "radio", "data-view": view }, view.toUpperCase());
    option.addEventListener("click", () => onPick(view));
    return option;
  });
  views.append(...options);
  const detail = el("span");
  setupGraphicsSwitch(detail, { name: false }); // the row already says "3D detail"
  const viewLabel = el("span");
  const detailLabelNode = el("span");
  const viewRow = el("div", { class: "voice-row" }, viewLabel, views);
  const detailRow = el("div", { class: "voice-row" }, detailLabelNode, detail);
  const note = el("p", { class: "hint" });
  panel.append(viewRow, detailRow, note);

  const show = () => {
    const name = t("Stage view");
    button.textContent = now.view.toUpperCase();
    button.title = `${name}: ${now.view.toUpperCase()}\n${detailLabel(look().graphics)}`;
    button.setAttribute("aria-label", `${name}: ${now.view.toUpperCase()}`);
    panel.setAttribute("aria-label", name);
    views.setAttribute("aria-label", name);
    viewLabel.textContent = name;
    detailLabelNode.textContent = t("3D detail");
    for (const option of options) {
      option.setAttribute("aria-checked", String(option.dataset.view === now.view));
      option.disabled = option.dataset.view === "3d" && !now.can3d;
    }
    viewRow.hidden = Boolean(now.locked); // the teacher picked the view for the class
    detailRow.hidden = now.view !== "3d" && !now.can3d;
    note.textContent = !now.can3d
      ? t("This device can't draw 3D, so the stage stays flat.")
      : now.locked
        ? t("The teacher picked the stage view for the class.")
        : "";
    note.hidden = !note.textContent;
    // nothing to choose (one view set by the teacher and no 3D detail to pick): no button
    button.hidden = Boolean(now.locked) && now.view === "2d";
  };
  button.classList.add("stage-button");
  button.popoverTargetElement = panel;
  panel.addEventListener("beforetoggle", (event) => {
    if (event.newState !== "open") return;
    show();
    const box = button.getBoundingClientRect();
    panel.style.top = `${box.bottom + 6}px`;
    panel.style.left = `${box.left}px`;
    requestAnimationFrame(() => {
      panel.style.left = `${Math.max(8, Math.min(box.left, innerWidth - panel.offsetWidth - 8))}px`;
    });
  });
  window.addEventListener("codezoo-look", show);
  new MutationObserver(show).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
  show();
  return {
    update(next) {
      Object.assign(now, next);
      show();
    },
  };
}

systemReduce.addEventListener("change", applyLook);
wideWindow.addEventListener("change", applyLook);
applyLook();
