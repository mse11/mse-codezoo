// Read aloud (phase 7): goals, hints, results and tapped blocks, spoken with the browser's
// own speech synthesis. Nothing is recorded or sent anywhere; the voices are the device's.
// It is always on in Cub mode (with a mute button kept per browser) and an opt-in for
// everyone else in "Look and feel" (look.js sets <html data-read="true">).
// Without a voice for the page's language nothing is spoken; look.js says so to the grown-up.

import { lang } from "./i18n.js";

const MUTE_KEY = "codezoo.mute";

// Recorded voices: voices/<lang>/manifest.json maps a sentence (as it is spoken) to a sound
// file next to it ({"Help the monkey collect every banana.": "goal-bananas.mp3"}). A
// sentence with a recording plays it; every other sentence uses the device's own voice.
// The manifests ship empty: see voices/README.md for how to add recordings.
const recordings = new Map(); // lang -> Map(sentence -> url), or null while loading
let playing = null;

function loadRecordings(code) {
  if (recordings.has(code) || typeof fetch === "undefined") return;
  recordings.set(code, null);
  fetch(`voices/${code}/manifest.json`)
    .then((response) => (response.ok ? response.json() : {}))
    .then((manifest) => {
      const found = new Map();
      for (const [sentence, file] of Object.entries(manifest || {})) {
        if (typeof file === "string" && /^[\w.-]+\.(mp3|ogg|m4a|wav)$/.test(file)) found.set(speakable(sentence), `voices/${code}/${file}`);
      }
      recordings.set(code, found);
    })
    .catch(() => recordings.set(code, new Map()));
}

// the recording for these words in this language, if someone recorded them
export function recordingFor(words, code = lang()) {
  loadRecordings(code);
  return recordings.get(code)?.get(words) || null;
}
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
  if ((!force && !readAloudOn()) || (force && cub && muted)) return false;
  const words = speakable(text);
  const recorded = words ? recordingFor(words) : null;
  if (recorded && typeof Audio !== "undefined") {
    synth?.cancel();
    playing?.pause();
    playing = new Audio(recorded);
    playing.play().catch(() => {});
    return true;
  }
  if (!synth) return false; // no speech voices in this browser (a recording would have played)
  const voice = voiceFor();
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
  playing?.pause();
}

// voices often arrive after the page has loaded
export function onVoices(callback) {
  synth?.addEventListener?.("voiceschanged", callback);
}
