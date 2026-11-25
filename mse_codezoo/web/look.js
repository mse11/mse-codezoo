// "Look and feel" (phase 6, accessibility basics): text size, easy-to-read text, high
// contrast, less motion and big targets (bigger blocks and buttons, tap a block in the
// palette to add it). Kept in this browser only and applied as attributes on <html>, so
// every page (game, editor, teacher's screen) can follow them with CSS.

import { t } from "./i18n.js";
import { canSpeak, speak } from "./speech.js";
import { resetAllZoom } from "./zoom.js";

const KEY = "codezoo.look";
const LOCK_KEY = "codezoo.look.locked"; // the teacher's colours (early-look.js)
const DEFAULTS = {
  text: "normal", easy: false, contrast: false, motion: "system", targets: false, read: false, sounds: true,
  theme: "system", // colours: "system" (as the device), "light" or "dark"
  layout: "auto", // goal and result: "above" the stage, "side" (beside it) or "auto" (by window width)
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

export function applyLook() {
  const root = document.documentElement;
  root.dataset.text = settings.text;
  root.dataset.easy = String(settings.easy);
  root.dataset.contrast = String(settings.contrast);
  root.dataset.motion = reducedMotion() ? "reduce" : "full";
  root.dataset.targets = String(settings.targets);
  root.dataset.read = String(settings.read); // read aloud (speech.js, phase 7)
  root.dataset.layout = layout(); // style.css places the goal and result
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
  const test = el("button", { type: "button", class: "small" }, t("Try the voice"));
  test.addEventListener("click", () => speak(t("Hello! I will read the goals to you."), { force: true }));
  return el("p", { class: "hint" }, test);
}

// The dialog is built here, so every page gets the same one from a single button.
export function openLook() {
  let dialog = document.getElementById("look-dialog");
  dialog?.remove();
  dialog = el(
    "dialog",
    { id: "look-dialog", class: "dialog", "aria-labelledby": "look-title" },
    el("h2", { id: "look-title" }, t("Look and feel")),
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
    checkbox("targets", t("Big targets: bigger blocks and buttons; tap a block to add it")),
    checkbox("read", t("Read aloud: goals, hints, results and tapped blocks")),
    checkbox("sounds", t("Sounds: steps, pops and a little tune when you solve a level")),
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

systemReduce.addEventListener("change", applyLook);
wideWindow.addEventListener("change", applyLook);
applyLook();
