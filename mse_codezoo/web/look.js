// "Look and feel" (phase 6, accessibility basics): text size, easy-to-read text, high
// contrast, less motion and big targets (bigger blocks and buttons, tap a block in the
// palette to add it). Kept in this browser only and applied as attributes on <html>, so
// every page (game, editor, teacher's screen) can follow them with CSS.

import { t } from "./i18n.js";
import { canSpeak, speak } from "./speech.js";

const KEY = "codezoo.look";
const DEFAULTS = {
  text: "normal", easy: false, contrast: false, motion: "system", targets: false, read: false,
};

function read() {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || "{}") };
  } catch {
    return { ...DEFAULTS };
  }
}

let settings = read();

export function look() {
  return settings;
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
  window.dispatchEvent(new CustomEvent("codezoo-look", { detail: settings }));
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
  const input = el("input", { type: "checkbox", ...(settings[key] ? { checked: "" } : {}) });
  input.addEventListener("change", () => save({ [key]: input.checked }));
  return el("label", { class: "check" }, input, " ", el("span", {}, label));
}

function select(key, label, options) {
  const box = el("select", {}, ...options.map(([value, text]) => el("option", { value }, text)));
  box.value = settings[key];
  box.addEventListener("change", () => save({ [key]: box.value }));
  return el("label", {}, el("span", {}, label), box);
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
    checkbox("easy", t("Easy-to-read text (simple letters, more space)")),
    checkbox("contrast", t("High contrast")),
    select("motion", t("Motion"), [
      ["system", t("as this device is set")],
      ["reduce", t("less motion")],
      ["full", t("all animations")],
    ]),
    checkbox("targets", t("Big targets: bigger blocks and buttons; tap a block to add it")),
    checkbox("read", t("Read aloud: goals, hints, results and tapped blocks")),
    voiceNote(),
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

systemReduce.addEventListener("change", applyLook);
applyLook();
