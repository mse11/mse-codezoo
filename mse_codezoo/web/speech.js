// Read aloud (phase 7): goals, hints, results and tapped blocks, spoken with the browser's
// own speech synthesis. Nothing is recorded or sent anywhere; the voices are the device's.
// It is always on in Cub mode (with a mute button kept per browser) and an opt-in for
// everyone else in "Look and feel" (look.js sets <html data-read="true">).
// Without a voice for the page's language nothing is spoken; look.js says so to the grown-up.

import { lang } from "./i18n.js";

const MUTE_KEY = "codezoo.mute";
const synth = typeof window !== "undefined" ? window.speechSynthesis : undefined;
let cub = false;
let muted = readMuted();

function readMuted() {
  try {
    return localStorage.getItem(MUTE_KEY) === "true";
  } catch {
    return false;
  }
}

export function setCub(on) {
  cub = Boolean(on);
}

export function isMuted() {
  return muted;
}

export function setMuted(on) {
  muted = Boolean(on);
  try {
    localStorage.setItem(MUTE_KEY, String(muted));
  } catch {
    // storage blocked: muted until the page is closed
  }
  if (muted) synth?.cancel();
}

// Cub mode reads aloud unless muted; the main course only when Look and feel asks for it
export function readAloudOn() {
  if (!synth) return false;
  if (cub) return !muted;
  return document.documentElement.dataset.read === "true";
}

// the device's voice for a language ("sk"), preferring one that works offline
export function voiceFor(code = lang()) {
  if (!synth) return null;
  const voices = synth.getVoices().filter((v) => v.lang.toLowerCase().replace("_", "-").split("-")[0] === code);
  return voices.find((v) => v.localService) || voices[0] || null;
}

export function canSpeak(code = lang()) {
  return Boolean(voiceFor(code));
}

// emoji and stars are read out as their names ("banana, star, star"): leave them out
const PICTURES = /[\p{Extended_Pictographic}☀-➿⭐★☆️‍]/gu;
export function speakable(text) {
  return String(text || "")
    .replace(PICTURES, " ")
    .replace(/[_()]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// speak now, replacing whatever was being said; `force` for the "read it to me" button
export function speak(text, { force = false } = {}) {
  if (!synth || (!force && !readAloudOn()) || (force && cub && muted)) return false;
  const voice = voiceFor();
  const words = speakable(text);
  if (!voice || !words) return false;
  synth.cancel();
  const utterance = new SpeechSynthesisUtterance(words);
  utterance.voice = voice;
  utterance.lang = voice.lang;
  utterance.rate = cub ? 0.85 : 0.95; // a little slower for young listeners
  synth.speak(utterance);
  return true;
}

export function stopSpeaking() {
  synth?.cancel();
}

// voices often arrive after the page has loaded
export function onVoices(callback) {
  synth?.addEventListener?.("voiceschanged", callback);
}
