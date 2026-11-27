// Read aloud (phase 7): goals, hints, results and tapped blocks, spoken with the browser's
// own speech synthesis. Nothing is recorded or sent anywhere; the voices are the device's.
// It is always on in Cub mode (with a mute button kept per browser) and an opt-in for
// everyone else in "Look and feel" (look.js sets <html data-read="true">).
// Without a voice for the page's language nothing is spoken; look.js says so to the grown-up.

import { lang, t } from "./i18n.js";

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
// Natural voices: when the optional Piper add-on is installed next to `codezoo serve`
// (voice.py), the server speaks with a real voice for the languages it has; every other
// language, the offline build and the classroom hub keep the device's own voice.
let natural = new Set();
let naturalNames = {}; // language -> the voice's file name ("sk_SK-lili-medium")
let spoken = 0; // each new line replaces the one still loading or playing
// tooltips that name the voice listen for this (the voices arrive after the page loads)
const voicesChanged = () => window.dispatchEvent(new Event("codezoo-voices"));
if (typeof window !== "undefined" && !window.CODEZOO_OFFLINE && typeof fetch !== "undefined") {
  fetch("/api/voice")
    .then((response) => (response.ok ? response.json() : { langs: [] }))
    .then((info) => {
      natural = new Set(info.langs || []);
      naturalNames = info.voices || {};
      voicesChanged();
    })
    .catch(() => {});
}

export function hasNaturalVoice(code = lang()) {
  return natural.has(code);
}

// say the words with the server's natural voice; `animal` plays it a little faster and
// higher, like the animal talking. If it fails, `fallback()` speaks with the device's voice.
// The voice settings in "Look and feel" (look.js puts them on <html>):
//   data-voice-speed: slow | normal | quick, how fast everything is spoken
//   data-animal-voice: natural | higher | squeaky, how the animals' say() sounds.
// A browser can't raise a sound's pitch without also speeding it up, so "higher" is a
// gentle 1.08x (about 1.3 semitones) and "squeaky" the old 1.3x; "natural" is the voice as it is.
const SPEED = {
  slow: { pace: 1.2, rate: 0.85 }, // Piper's length_scale (more = slower), the device's rate
  normal: { pace: 1.05, rate: 0.95 },
  quick: { pace: 0.92, rate: 1.1 },
};
const ANIMAL = {
  natural: { playback: 1, pitch: 1.15 }, // Piper's playback rate, the device voice's pitch
  higher: { playback: 1.08, pitch: 1.4 },
  squeaky: { playback: 1.3, pitch: 1.7 },
};
function voiceSetting(name, table, fallback) {
  return table[document.documentElement.dataset[name]] || table[fallback];
}
const speed = () => voiceSetting("voiceSpeed", SPEED, "normal");
const animalVoice = () => voiceSetting("animalVoice", ANIMAL, "natural");

function speakNatural(words, { animal = false, fallback }) {
  const ticket = ++spoken;
  synth?.cancel();
  playing?.pause();
  fetch("/api/speak", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: words, lang: lang(), pace: speed().pace * (cub ? 1.1 : 1) }),
  })
    .then((response) => (response.ok ? response.blob() : Promise.reject(new Error("no voice"))))
    .then((sound) => {
      if (ticket !== spoken) return; // something newer was said meanwhile
      const url = URL.createObjectURL(sound);
      playing = new Audio(url);
      const playback = animal ? animalVoice().playback : 1;
      if (playback !== 1) {
        // faster and higher together, a small animal voice (older Firefox and Safari use the
        // prefixed names; without them, it only sounds like a hurried grown-up)
        playing.preservesPitch = false;
        playing.mozPreservesPitch = false;
        playing.webkitPreservesPitch = false;
        playing.playbackRate = playback;
      }
      playing.addEventListener("ended", () => URL.revokeObjectURL(url), { once: true });
      return playing.play();
    })
    .catch(() => {
      if (ticket === spoken) fallback?.();
    });
  return true;
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

export function isCub() {
  return cub;
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
  if (document.documentElement.dataset.sounds === "false") return false; // Sounds off: all quiet
  if (cub) return !muted;
  return document.documentElement.dataset.read === "true";
}

// the device's voice for a language ("sk"), preferring one that works offline
export function voiceFor(code = lang()) {
  if (!synth) return null;
  const voices = synth.getVoices().filter((v) => v.lang.toLowerCase().replace("_", "-").split("-")[0] === code);
  return voices.find((v) => v.localService) || voices[0] || null;
}

// which voice speaks this language now, for tooltips: {engine: "piper" | "device" | null,
// name}. A Piper voice "sk_SK-lili-medium" is called "lili"; a device voice by its own name.
export function currentVoice(code = lang()) {
  if (hasNaturalVoice(code)) {
    const file = naturalNames[code] || "";
    return { engine: "piper", name: file.split("-")[1] || file || code };
  }
  const device = voiceFor(code);
  return device ? { engine: "device", name: device.name.replace(/\s+-\s+.*$/, "") } : { engine: null, name: "" };
}

// the same, as a tooltip line: "Voice: lili (Piper)", "Voice: Microsoft Filip (this computer)"
export function voiceLabel(code = lang()) {
  const { engine, name } = currentVoice(code);
  if (engine === "piper") return t("Voice: {name} (Piper)", { name });
  if (engine === "device") return t("Voice: {name} (this computer)", { name });
  return t("No voice for this language");
}

export function canSpeak(code = lang()) {
  return hasNaturalVoice(code) || Boolean(voiceFor(code));
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
  if (words && hasNaturalVoice()) return speakNatural(words, { fallback: () => deviceSpeak(words) });
  return deviceSpeak(words);
}

// the device's own speech voice (the browser's speech synthesis)
function deviceSpeak(words) {
  if (!synth) return false; // no speech voices in this browser (a recording would have played)
  const voice = voiceFor();
  if (!voice || !words) return false;
  spoken += 1;
  synth.cancel();
  playing?.pause();
  const utterance = new SpeechSynthesisUtterance(words);
  utterance.voice = voice;
  utterance.lang = voice.lang;
  utterance.rate = speed().rate * (cub ? 0.9 : 1); // a little slower for young listeners
  synth.speak(utterance);
  return true;
}

// the animal's own voice for `say("...")` in a program: the natural voice (or the device's),
// a little higher and quicker so it sounds like the animal, not the narrator. It follows the Sounds switch
// (fun.js checks it), not Read aloud; a muted Cub hears nothing. Each new line replaces the
// one still being said, so a loop of says doesn't pile up. False when nothing was spoken.
export function animalSay(text) {
  if (cub && muted) return false;
  const words = speakable(text);
  if (!words) return false;
  if (hasNaturalVoice()) return speakNatural(words, { animal: true, fallback: () => deviceAnimalSay(words) });
  return deviceAnimalSay(words);
}

function deviceAnimalSay(words) {
  const voice = voiceFor();
  if (!synth || !voice) return false;
  spoken += 1;
  synth.cancel();
  playing?.pause();
  const utterance = new SpeechSynthesisUtterance(words);
  utterance.voice = voice;
  utterance.lang = voice.lang;
  utterance.pitch = animalVoice().pitch;
  utterance.rate = speed().rate;
  synth.speak(utterance);
  return true;
}

export function stopSpeaking() {
  spoken += 1;
  synth?.cancel();
  playing?.pause();
}

// voices often arrive after the page has loaded
export function onVoices(callback) {
  synth?.addEventListener?.("voiceschanged", callback);
}

// the device's voices and the page's language change what currentVoice() says
if (typeof window !== "undefined") {
  synth?.addEventListener?.("voiceschanged", voicesChanged);
  new MutationObserver(voicesChanged).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
}
