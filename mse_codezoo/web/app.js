// CodeZoo web client: three panes (stage, blocks, code) over one program.
//
// Blocks change -> IR from blocks -> engine prints Python -> code pane.
// Code typed    -> engine parses -> IR -> blocks rebuilt (if the code parses).
// Run           -> engine runs the code in the world shown -> steps animate the stage and
//                  light up line + block; the engine also checks the level's other worlds.
//                  With a player chosen, the engine saves the result to their progress.

import { api, setPython } from "./api.js";
import { createWorkspace, describeBlock } from "./blocks.js";
import { Classroom } from "./classroom.js";
import { CodeView } from "./code.js";
import { deviceLang, fillLangSelect, initialLang, lang, setLang, t, translatePage, urlLang } from "./i18n.js";
import { setupSplitters } from "./layout.js";
import { lockLook, openLook, setupThemeButton } from "./look.js";
import { Pilot } from "./pilot.js";
import { Players } from "./players.js";
import { decodeShare } from "./share.js";
import { canSpeak, isMuted, onVoices, readAloudOn, setCub, setMuted, speak } from "./speech.js";
import { describeGoal } from "./goals.js";
import { Fun, setupSoundButton } from "./fun.js";
import { EMOJI, Stage } from "./stage.js";
import { keepPageZoom, resetAllZoom, setupBlocksZoom, setupZoom } from "./zoom.js";

const $ = (id) => document.getElementById(id);
const HEARTBEAT_SECONDS = 30;
const VIEW_KEY = "codezoo.view";
const ANIMAL_KEY = "codezoo.animal";
const PYTHON_KEY = "codezoo.python";

setLang(initialLang(), { save: false });

const state = {
  levels: [],
  level: null,
  variant: 0, // which world of the level is on the stage
  text: "",
  sourceMap: {}, // statement id -> {line, ...} in the current text
  run: null, // last run result from the engine
  stepIndex: 0,
  playing: false,
  token: 0, // bumps to cancel playback
  hintsShown: 0,
  player: null, // profile, or null for a guest
  progress: {}, // level id -> {stars, solved}
  over: false, // daily limit reached
  animals: [], // every animal pack
  animal: null, // the animal chosen for core levels (null: the level's own)
  outfit: "", // what the animal wears, from the player's habitat
  stack: [], // the call stack while a run plays: one burrow per function call
  cub: false, // Cub mode (ages 6-8, phase 7): the player's setting, from their progress
  guess: null, // a "predict" cub level: the square the child tapped, [x, y]
  tinted: new Set(), // statement ids whose code lines were tinted last time (new ones glow)
};

const stage2d = new Stage($("stage"));
let stage3d = null;
let stage = stage2d;

const code = new CodeView({
  textarea: $("code"),
  gutter: $("gutter"),
  mark: $("line-mark"),
  onInput: (text) => debounce("parse", 350, () => codeChanged(text)),
  onLineTap: (line) => lineTapped(line),
});
const blocks = createWorkspace($("blockly"), () => debounce("print", 150, blocksChanged));
blocks.onTap((block) => speak(describeBlock(block)));
// −, + and reset for each part of the page, and Ctrl + wheel over it (zoom.js)
setupBlocksZoom({ pane: document.querySelector(".blocks-pane"), workspace: blocks.workspace });
for (const [selector, name] of [[".code-pane", "code"], [".console-pane", "console"]]) {
  const pane = document.querySelector(selector);
  setupZoom({
    area: pane,
    place: pane.querySelector(".pane-title"),
    name,
    onChange: () => {
      code.positionMark();
      code.positionTints();
    },
  });
}
// the whole stage pane, so the stage can't shrink out from under the mouse; the goal
// inside it has its own zoom
setupZoom({
  area: document.querySelector(".stage-pane"),
  target: document.querySelector(".stage-pane"),
  place: document.querySelector(".stage-tools"),
  name: "stage",
  variable: "--stage-zoom",
  label: "Zoom the stage",
});
setupZoom({
  area: document.querySelector(".stage-head"),
  place: document.querySelector(".stage-head"),
  name: "head",
  variable: "--head-zoom",
  label: "Zoom the goal and result",
});
// the pane titles: Ctrl + wheel over any of them zooms all of them, so they always match
setupZoom({ area: document.querySelectorAll(".pane-title"), target: $("panes"), name: "titles", variable: "--title-zoom" });
// the top bar: Ctrl + wheel only
setupZoom({ area: document.querySelector("header.bar"), name: "bar", variable: "--bar-zoom" });
keepPageZoom();
const players = new Players({ onChoose: playerChosen, onSettingsChanged: checkToday });
// on a classroom hub (`codezoo class serve`); stays unused at home
const classroom = new Classroom({
  players,
  onLevelsChanged: refreshLevels,
  onPause: stopPlayback,
  onViews: applyViews,
  // sounds the teacher allows: both lets the child switch, one is set for everyone
  onSounds: (sounds) => lockLook({ sounds: sounds.length === 1 ? sounds[0] === "on" : null }),
  // colours the teacher allows: both lets the child switch, one is set for everyone
  onThemes: (themes) => lockLook({ theme: themes.length === 1 ? themes[0] : null }),
  // the teacher picked a language for the class or for this child (null: the device's own)
  onLang: (code) => {
    const next = code || deviceLang();
    if (next !== lang()) changeLanguage(next, { save: false });
  },
  onPlayProgram: playSharedProgram,
  onPlayLevel: playSharedLevel,
});
let inClass = false;
// sounds, confetti, combos and a pokeable animal (the fun pass); only reacts to runs
const fun = new Fun({ getStage: () => stage, stageBox: $("stage") });
setupSoundButton($("sounds"));
setupThemeButton($("theme"));
$("stage").addEventListener("click", (event) => {
  if (state.playing || !stage.hitAnimal?.(event)) return;
  fun.poke();
});
// pilot readiness (phase 6): checks, smiley and error counts, only when the pilot is on
const pilotUI = new Pilot({ getPlayer: () => state.player });

// --- small helpers -----------------------------------------------------------------

const timers = {};
function debounce(key, ms, fn) {
  clearTimeout(timers[key]);
  timers[key] = setTimeout(fn, ms);
}

let sequence = 0; // ignore answers to requests that a newer edit has replaced

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else node.setAttribute(key, value);
  }
  node.append(...children.filter((child) => child !== null && child !== undefined));
  return node;
}

function readSetting(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function saveSetting(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // storage blocked: the default is used next time
  }
}

function showDiagnostics(diagnostics) {
  $("diagnostics").replaceChildren(
    ...diagnostics.map((d) => el("li", { class: d.severity }, t("line {line}: {message}", d))),
  );
}

function blockAtLine(line) {
  for (const [id, span] of Object.entries(state.sourceMap)) {
    if (span.line === line && blocks.workspace.getBlockById(id)) return id;
  }
  return null;
}

const starText = (n) => (n ? "★".repeat(n) + "☆".repeat(3 - n) : "");
const currentWorld = () => state.level.worlds[state.variant] || state.level.world;
const currentGoal = () => state.level.goals?.[state.variant] || state.level.goal;

// --- sync --------------------------------------------------------------------------

async function blocksChanged() {
  const mine = ++sequence;
  const program = blocks.toProgram(state.level.pack.actions);
  try {
    const printed = await api.print(program);
    if (mine !== sequence) return;
    state.text = printed.text;
    state.sourceMap = printed.sourceMap;
    code.setText(printed.text);
    renderTints();
    showDiagnostics([]);
    invalidateRun();
  } catch (error) {
    showDiagnostics([{ line: 0, severity: "error", message: error.message }]);
    pilotUI.error(); // blocks that couldn't become code: a sync problem for the pilot metrics
  }
}

async function codeChanged(text) {
  const mine = ++sequence;
  state.text = text;
  invalidateRun();
  const parsed = await api.parse(text);
  if (mine !== sequence) return;
  showDiagnostics(parsed.diagnostics);
  if (!parsed.ok) return; // keep the last good blocks; the error is listed under the code
  state.sourceMap = parsed.positions;
  blocks.load(parsed.program, state.level.pack.actions, text, parsed.positions);
  renderTints();
}

async function loadProgram(text) {
  state.tinted = new Set(); // a new program: nothing glows as "new"
  if (!text) {
    code.setText("");
    state.sourceMap = {};
    blocks.load({ type: "Program", id: "program", body: [] }, state.level.pack.actions, "", {});
    renderTints();
    return;
  }
  const parsed = await api.parse(text);
  state.text = text;
  code.setText(text);
  if (parsed.ok) {
    state.sourceMap = parsed.positions;
    blocks.load(parsed.program, state.level.pack.actions, text, parsed.positions);
  }
  renderTints();
  showDiagnostics(parsed.diagnostics);
}

// --- Cub mode (ages 6-8, phase 7) ----------------------------------------------------
// Same game, a different face: picture blocks, everything read aloud, its own levels
// (predict, fix, make), code lines in their block's colour. A grown-up turns it on per player.

// Each block's lines in its colour, so a child sees the code grow as they build.
function renderTints() {
  if (!state.cub) {
    code.setTints([]);
    return;
  }
  const tints = [];
  const now = new Set();
  for (const [id, span] of Object.entries(state.sourceMap)) {
    const family = blocks.familyOf(id);
    if (!family || !span?.line) continue;
    now.add(id);
    const fresh = state.tinted.size > 0 && !state.tinted.has(id);
    tints.push({ line: span.line, endLine: span.end_line || span.line, family, fresh });
  }
  // a loop's tint first, so the lines inside it are drawn on top
  tints.sort((a, b) => a.line - b.line || b.endLine - a.endLine);
  // lines inside a loop sit a little to the right, so the loop's own bar stays in sight
  for (const tint of tints) {
    tint.depth = tints.filter((o) => o !== tint && o.line <= tint.line && o.endLine >= tint.endLine && (o.line < tint.line || o.endLine > tint.endLine)).length;
  }
  state.tinted = now.size ? now : new Set(["-"]); // "-": the program was empty, so all is new
  code.setTints(tints);
}

// a tap on a code line: its block wiggles and is read aloud
function lineTapped(line) {
  const id = blockAtLine(line);
  if (!id) return;
  blocks.wiggle(id);
  const block = blocks.workspace.getBlockById(id);
  if (block) speak(describeBlock(block));
}

// main-course players never see cub levels and cubs see only theirs, except the teacher's
// picks for today, which everyone sees (and every level, if nothing else is left)
function visibleLevels() {
  // the teacher's picks for today show for everyone, whichever course they are in
  const mine = state.levels.filter((l) => Boolean(l.cub) === state.cub || l.assigned);
  return mine.length ? mine : state.levels;
}

async function applyCub(on) {
  const changed = state.cub !== Boolean(on);
  state.cub = Boolean(on);
  document.documentElement.dataset.cub = String(state.cub);
  setCub(state.cub);
  const relabelled = blocks.setCub(state.cub);
  if (!changed && !relabelled) return;
  renderLevelOptions();
  if (!state.level) return;
  if (!state.shared && !visibleLevels().some((l) => l.id === state.level.id)) {
    const next = visibleLevels().find((l) => !state.progress[l.id]?.solved) || visibleLevels()[0];
    if (next) await loadLevel(next.id);
    return;
  }
  renderGoal();
  await loadProgram(state.text);
}

// the cub level strip: big numbered buttons with stars, instead of a list to read
function renderCubLevels() {
  const strip = $("cub-levels");
  if (!state.cub) {
    strip.replaceChildren();
    return;
  }
  const modules = new Map();
  for (const level of visibleLevels()) {
    if (!modules.has(level.module)) modules.set(level.module, []);
    modules.get(level.module).push(level);
  }
  const groups = [...modules.values()].map((levels, m) =>
    el(
      "div",
      { class: "cub-module", role: "group", "aria-label": t("Part {n}", { n: m + 1 }) },
      el("span", { class: "cub-module-icon", "aria-hidden": "true" }, m === 0 ? "🐾" : "🔂"),
      ...levels.map((level, i) => {
        const stars = state.progress[level.id]?.stars || 0;
        const starsText = stars ? `, ${t("{n} of 3 stars", { n: stars })}` : "";
        const button = el(
          "button",
          {
            type: "button",
            class: `cub-level${level.assigned ? " today" : ""}`,
            "aria-label": `${i + 1}. ${level.title}${starsText}`,
            ...(state.level?.id === level.id ? { "aria-current": "true" } : {}),
          },
          el("span", { class: "cub-number" }, String(i + 1)),
          el("span", { class: "cub-stars", "aria-hidden": "true" }, stars ? "★".repeat(stars) : "·"),
        );
        button.addEventListener("click", () => loadLevel(level.id));
        return button;
      }),
    ),
  );
  strip.replaceChildren(...groups);
}

// what Cub mode says the goal is: short, and read aloud
function cubGoalText(level) {
  const animal = level.pack.animalName || level.pack.animal;
  if (level.cub === "predict") return t("Where will the {animal} stop? Tap a square, then press Run.", { animal });
  if (level.cub === "fix") return t("Oops! One block is wrong. Watch, then fix it.");
  return `${describeGoal(level, currentGoal())}.`;
}

// "predict": a small picture grid of the world; the child taps where the animal will stop
function predictGrid(level) {
  const world = currentWorld();
  const [width, height] = world.size;
  const walls = new Set((world.walls || []).map(([x, y]) => `${x},${y}`));
  const items = new Map((world.items || []).map(([x, y, tile]) => [`${x},${y}`, tile]));
  const arrows = { north: "⬆", east: "➡", south: "⬇", west: "⬅" };
  const grid = el("div", {
    class: "predict-grid",
    role: "group",
    "aria-label": t("Where will it stop?"),
    style: `grid-template-columns: repeat(${width}, minmax(0, 4.5rem))`,
  });
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const key = `${x},${y}`;
      const start = world.position[0] === x && world.position[1] === y;
      const tile = items.get(key);
      let picture = "";
      if (walls.has(key)) picture = "🪨";
      else if (start) picture = `${EMOJI[level.pack.animal] || "🐾"}${arrows[world.facing] || ""}`;
      else if (tile) picture = EMOJI[level.pack.items[tile]] || "•";
      const guessed = Boolean(state.guess && state.guess[0] === x && state.guess[1] === y);
      const cell = el(
        "button",
        {
          type: "button",
          class: `predict-cell${guessed ? " guessed" : ""}`,
          "aria-label": t("Square {x}, {y}", { x: x + 1, y: y + 1 }) + (start ? `, ${t("start")}` : ""),
          "aria-pressed": String(guessed),
          "data-x": String(x),
          "data-y": String(y),
          ...(walls.has(key) ? { disabled: "" } : {}),
        },
        el("span", { "aria-hidden": "true" }, guessed ? `🤔${start ? picture : ""}` : picture),
      );
      cell.addEventListener("click", () => {
        state.guess = [x, y];
        renderGoal();
        updateButtons();
        speak(t("You think it stops here. Press Run to see!"));
      });
      grid.append(cell);
    }
  }
  return grid;
}

// after a "predict" run: was the guess right? Never a score, just a look at what happened.
function predictFeedback(run) {
  if (state.level?.cub !== "predict" || !state.guess || !run.world) return null;
  const [x, y] = run.world.position;
  const right = state.guess[0] === x && state.guess[1] === y;
  const cell = document.querySelector(`.predict-cell[data-x="${x}"][data-y="${y}"]`);
  if (cell) {
    cell.classList.add("actual");
    cell.append(el("span", { class: "actual-star", "aria-hidden": "true" }, "⭐"));
    cell.setAttribute("aria-label", `${cell.getAttribute("aria-label")}, ${t("it stopped here")}`);
  }
  return right ? t("You guessed right! 🎉") : t("Good guess! It stopped on another square: look for the star.");
}

function readAloudButtons() {
  if (!(state.cub || readAloudOn()) || !canSpeak()) return null;
  const again = el("button", { type: "button", class: "small speak-again", "aria-label": t("Read it to me"), title: t("Read it to me") }, "🔊");
  again.addEventListener("click", () => speak(goalSpeech(), { force: true }));
  if (!state.cub) return again;
  const mute = el(
    "button",
    { type: "button", class: "small", "aria-pressed": String(isMuted()) },
    isMuted() ? t("🔇 Quiet") : t("🔈 Talking"),
  );
  mute.addEventListener("click", () => {
    setMuted(!isMuted());
    renderGoal();
  });
  return el("span", { class: "speak-buttons" }, again, mute);
}

function goalSpeech() {
  const level = state.level;
  if (!level) return "";
  const short = state.cub || level.cub === "predict"; // predict: never say where it stops
  return `${level.title}. ${short ? cubGoalText(level) : `${describeGoal(level, currentGoal())}.`}`;
}

// a predict level's flag would give the answer away
const stageGoal = () => (state.level?.cub === "predict" ? { type: "none" } : currentGoal());

onVoices(() => state.level && renderGoal());


// --- players and the daily limit ----------------------------------------------------

// Play as another animal: the menu, or a player's own animal when they start. Each player
// keeps the animal they last picked; a new player starts as their picture, when their
// picture is one of the zoo's animals.
function switchAnimal(animal) {
  state.animal = animal;
  saveSetting(ANIMAL_KEY, animal);
  if (state.player) saveSetting(`${ANIMAL_KEY}.${state.player.id}`, animal);
  if (!state.animals) return; // still starting: the levels load with this animal
  api.levels(animal).then((levels) => {
    state.levels = levels; // titles name this animal's items
    renderLevelOptions();
  });
  if (state.shared) loadShared(location.hash.slice(6));
  else if (state.level) loadLevel(state.level.id);
}

function playerAnimal(profile) {
  if (!profile) return null;
  const kept = readSetting(`${ANIMAL_KEY}.${profile.id}`);
  const zoo = (state.animals || []).map((a) => a.id);
  if (kept && (!zoo.length || zoo.includes(kept))) return kept;
  return zoo.includes(profile.picture) ? profile.picture : null;
}

async function playerChosen(profile) {
  state.player = profile;
  const animal = playerAnimal(profile);
  if (animal && animal !== state.animal) switchAnimal(animal);
  state.progress = {};
  state.over = false;
  state.outfit = "";
  if (!profile) {
    pilotUI.setProgress(null);
    await applyCub(false); // a guest plays the main course
  }
  if (profile) {
    const progress = await api.progress(profile.id);
    state.progress = progress.levels;
    applyToday(progress.today);
    pilotUI.setProgress(progress);
    await applyCub(progress.cub);
    if (state.level && !state.shared) pilotUI.opened(state.level);
    try {
      const habitat = await api.habitat(profile.id);
      state.outfit = habitat.outfits.find((o) => o.id === habitat.outfit)?.emoji || "";
    } catch {
      // no habitat yet
    }
  }
  stage.setOutfit?.(state.outfit);
  $("zoo").hidden = !profile;
  renderLevelOptions();
  updateButtons();
}

function applyToday(today) {
  state.over = Boolean(today?.over);
  updateButtons();
  if (state.over && !state.playing) players.showGoodbye(state.level?.pack);
}

async function checkToday() {
  if (!state.player) {
    state.over = false;
    updateButtons();
    return;
  }
  try {
    const progress = await api.progress(state.player.id);
    applyToday(progress.today);
    const wasOn = pilotUI.on;
    pilotUI.setProgress(progress); // a grown-up may have turned the pilot on or off
    await applyCub(progress.cub); // ... or Cub mode
    if (pilotUI.on && !wasOn && state.level && !state.shared) pilotUI.opened(state.level);
  } catch {
    // the player was removed by a grown-up: ask who is playing
    players.choose();
  }
}

setInterval(async () => {
  if (!state.player || document.visibilityState !== "visible" || document.querySelector("dialog[open]")) return;
  try {
    applyToday(await api.addTime(state.player.id, HEARTBEAT_SECONDS));
  } catch {
    // server stopped or player removed; nothing to count
  }
}, HEARTBEAT_SECONDS * 1000);

// --- level -------------------------------------------------------------------------

function renderLevelOptions() {
  const select = $("level-select");
  renderCubLevels();
  const option = (l) => {
    const stars = starText(state.progress[l.id]?.stars || 0);
    const only = l.signature ? `${animalEmoji(l.animal)} ` : "";
    const island = l.minPython ? ` [${l.locked ? "🔒 " : ""}Python ${l.minPython}]` : "";
    return el("option", { value: l.id }, `${l.id} · ${only}${l.title}${island}${stars ? `  ${stars}` : ""}`);
  };
  const levels = [...visibleLevels()];
  // a level opened by its link that isn't in this player's list still shows in the menu
  const open = state.levels.find((l) => l.id === state.level?.id);
  if (open && !levels.includes(open)) levels.unshift(open);
  // in a class: the teacher's picks for today first, then every other level
  const today = levels.filter((l) => l.assigned);
  if (today.length && today.length < levels.length) {
    select.replaceChildren(
      el("optgroup", { label: t("⭐ Today") }, ...today.map(option)),
      el("optgroup", { label: t("All levels") }, ...levels.filter((l) => !l.assigned).map(option)),
    );
  } else {
    select.replaceChildren(...levels.map(option));
  }
  if (state.level) select.value = state.level.id;
}

const MUST_USE = {
  For: "for", While: "while", If: "if", Compare: "== <", BoolOp: "and / or", UnaryOp: "not",
  FString: 'f"…"', MethodCall: ".method()", Subscript: "[ ]", Assign: "x = …",
  AugAssign: "x += …", BinOp: "+ * /", Comment: "#", Break: "break", Continue: "continue",
  FunctionDef: "def", Return: "return", Try: "try / except", Raise: "raise", Assert: "assert",
  Import: "import", List: "[…]", Tuple: "(a, b)", Dict: "{key: value}", Set: "{a, b}",
  Global: "global", Comprehension: "[… for …]", Recursion: t("a function that calls itself"),
  Lambda: "lambda", Yield: "yield", YieldFrom: "yield from", Generator: "yield",
  GeneratorExp: "(… for …)", ClassDef: "class", Inheritance: "class A(B)", Decorator: "@decorator",
  With: "with", Match: "match / case", AsyncFunction: "async def", Await: "await",
  AnnAssign: "x: int", TString: 't"…"', TypeAlias: "type X = …",
};

const animalEmoji = (id) => state.animals.find((a) => a.id === id)?.emoji || "🐾";


function renderGoal() {
  const level = state.level;
  const rules = [];
  if (level.constraints.maxLines) rules.push(t("{n} lines or fewer", { n: level.constraints.maxLines }));
  if (level.constraints.mustUse?.length) {
    rules.push(t("use {what}", { what: level.constraints.mustUse.map((n) => MUST_USE[n] || n).join(", ") }));
  }
  const hintButton = el("button", { type: "button", class: "small" }, t("Hint"));
  const hint = el("span", { class: "hint", "aria-live": "polite" }); // read out when shown
  const showHint = () => {
    hint.textContent = level.hints[state.hintsShown - 1] || "";
    hintButton.disabled = state.hintsShown >= level.hints.length;
  };
  hintButton.addEventListener("click", () => {
    if (state.hintsShown < level.hints.length) state.hintsShown += 1;
    showHint();
    speak(hint.textContent);
  });
  showHint();
  hintButton.disabled = level.hints.length === 0 || state.hintsShown >= level.hints.length;
  if (state.cub) {
    const cubParts = [el("h2", {}, level.title, " ", readAloudButtons()), el("p", { class: "cub-goal" }, cubGoalText(level))];
    if (level.cub === "predict") cubParts.push(predictGrid(level));
    cubParts.push(el("div", { class: "hint-row" }, hintButton, hint));
    $("goal").replaceChildren(...cubParts.filter(Boolean));
    return;
  }
  // a predict level shows its program: the goal ("reach square (2, 1)") would give the answer
  const predict = level.cub === "predict";
  const parts = [
    el("h2", {}, level.title, " ", readAloudButtons()),
    el("p", {}, predict ? cubGoalText(level) : `${describeGoal(level, currentGoal())}.`),
    predict ? predictGrid(level) : null,
    el("p", {}, t("Stars for: {rules}", { rules: rules.length ? rules.join("; ") : t("just solving it") })),
  ];
  if (level.starter) parts.push(el("p", {}, t("This program has a bug. Run it, watch, then fix it!")));
  if (level.locked) parts.push(el("p", { class: "message err" }, `🔒 ${level.locked}`));
  parts.push(el("div", { class: "hint-row" }, hintButton, hint));
  $("goal").replaceChildren(...parts.filter(Boolean));
}

function renderWorlds() {
  const worlds = state.level.worlds || [state.level.world];
  if (worlds.length < 2) {
    $("worlds").replaceChildren();
    return;
  }
  const buttons = worlds.map((_, index) => {
    const button = el("button", { type: "button", "aria-pressed": String(index === state.variant) }, `${t("World")} ${index + 1}`);
    button.addEventListener("click", () => chooseWorld(index));
    return button;
  });
  $("worlds").replaceChildren(...buttons, el("span", { class: "note" }, t("Your program must work in every world. Try them all!")));
}

function chooseWorld(index) {
  if (index === state.variant) return;
  state.variant = index;
  invalidateRun();
  renderWorlds();
  renderGoal();
  stage.load(state.level, currentWorld(), stageGoal());
  describeStage();
}

function renderAnimals() {
  const select = $("animal-select");
  select.replaceChildren(
    ...state.animals.map((a) => el("option", { value: a.id }, `${a.emoji} ${a.animalName}`)),
  );
  const level = state.level;
  if (!level) return;
  select.value = level.pack.id;
  select.disabled = level.signature || level.animals.length < 2;
  select.title = level.signature ? t("Only the {animal} can play this level.", { animal: level.pack.animalName }) : "";
}

function renderFiles() {
  const files = Object.entries(state.level.files || {});
  $("files").replaceChildren(
    ...files.map(([name, text]) =>
      el("details", {}, el("summary", {}, t("Helper file {name}.py (import it)", { name })), el("pre", {}, text)),
    ),
  );
}

async function loadLevel(id) {
  stopPlayback();
  state.shared = null;
  const level = await api.level(id, state.animal);
  location.hash = id;
  $("level-select").value = id;
  await showLevel(level);
  pilotUI.opened(level);
}

// A level from the editor or a share link (index.html#play=...): checked by the engine like
// a level file, played like any other, but nothing is saved to a player's progress.
async function loadShared(link) {
  try {
    return await playSharedLevel(decodeShare(link).level, { quiet: false });
  } catch (error) {
    $("result").replaceChildren(el("div", { class: "message err" }, t("This shared level can't be played: {message}", { message: error.message })));
    return false;
  }
}

async function playSharedLevel(level, { quiet = true } = {}) {
  stopPlayback();
  try {
    state.shared = level;
    $("level-select").value = "";
    await showLevel(await api.previewLevel(level, state.animal));
  } catch (error) {
    state.shared = null;
    if (!quiet) throw error;
    $("result").replaceChildren(el("div", { class: "message err" }, t("This shared level can't be played: {message}", { message: error.message })));
    return false;
  }
  return true;
}

async function showLevel(level) {
  state.level = level;
  code.setCommands(level.pack.actions); // the animal's own command names, in their blocks' colours
  state.variant = 0;
  state.hintsShown = 0;
  state.guess = null;
  state.text = "";
  state.sourceMap = {};
  invalidateRun();

  renderGoal();
  renderWorlds();
  renderAnimals();
  renderFiles();
  if (!state.shared) renderLevelOptions(); // also the cub strip; marks the open level
  stage.load(level, currentWorld(), stageGoal());
  describeStage();
  stage.setOutfit?.(state.outfit);
  showDiagnostics([]);
  const typing = level.mode === "both_editable" || level.mode === "code_first";
  $("edit-code").checked = typing;
  code.setEditable(typing);
  blocks.setPalette(level.unlockedBlocks);
  await loadProgram(level.cub === "predict" ? level.predict : level.starter);
  blocks.resize();
  updateButtons();
  speak(goalSpeech());
}

// A classmate's program from the class gallery: their level with their code in the panes.
async function playSharedProgram(payload) {
  try {
    await loadLevel(payload.level);
    await loadProgram(payload.source);
  } catch (error) {
    $("result").replaceChildren(el("div", { class: "message err" }, error.message));
  }
}

// The teacher picked other levels (or unlocked all of them): show the new list.
async function refreshLevels() {
  state.levels = await api.levels(state.animal);
  renderLevelOptions();
  if (state.shared || !state.levels.length) return;
  // the teacher picked today's levels: go to the first one (unless already on one of them)
  const today = visibleLevels().filter((l) => l.assigned);
  if (today.length && !today.some((l) => l.id === state.level?.id)) {
    await loadLevel(today[0].id);
  } else if (!visibleLevels().some((l) => l.id === state.level?.id)) {
    await loadLevel(visibleLevels()[0].id);
  }
}

// For screen readers: the world in words (the stage itself is a picture).
const DIRECTIONS = { north: "up", east: "right", south: "down", west: "left" };
function describeStage() {
  const world = currentWorld();
  const pack = state.level.pack;
  const items = (world.items || []).map(([x, y, tile]) =>
    t("{item} at ({x}, {y})", { item: pack.itemNames?.[tile]?.one || pack.items?.[tile] || tile, x, y }),
  );
  const parts = [
    t("{width} by {height} squares.", { width: world.size[0], height: world.size[1] }),
    t("The {animal} is at ({x}, {y}), facing {direction}.", {
      animal: pack.animalName || pack.animal,
      x: world.position[0],
      y: world.position[1],
      direction: t(DIRECTIONS[world.facing] || world.facing),
    }),
    items.length ? `${items.join(", ")}.` : "",
    world.walls?.length ? t("Rocks: {list}.", { list: world.walls.map(([x, y]) => `(${x}, ${y})`).join(", ") }) : "",
  ];
  $("stage-description").textContent = parts.filter(Boolean).join(" ");
}

// --- stage view: 2D or 3D -----------------------------------------------------------

// The teacher can allow only one stage view for the class (a slow tablet: 2D only). Then the
// 3D switch goes away and the child's own choice is kept for later; with both allowed it's back.
let classViews = null;
async function applyViews(views) {
  classViews = views.length === 1 ? views[0] : null;
  $("view-3d").closest("label").hidden = Boolean(classViews);
  const want3d = classViews ? classViews === "3d" : readSetting(VIEW_KEY) !== "2d";
  $("view-3d").checked = want3d;
  if (want3d !== (stage !== stage2d)) await useView(want3d, { save: false });
}

async function useView(want3d, { save = true } = {}) {
  stopPlayback();
  let next = stage2d;
  if (want3d) {
    try {
      const module = await import("./stage3d.js");
      if (!module.webglAvailable()) throw new Error("no WebGL");
      stage3d ??= new module.Stage3D($("stage"));
      next = stage3d;
      next.setOutfit?.(state.outfit);
    } catch {
      $("view-3d").checked = false;
      $("view-3d").disabled = true; // this device can't draw 3D; the 2D stage works everywhere
      next = stage2d;
    }
  }
  if (next !== stage) stage.detach();
  stage = next;
  stage.setOutfit?.(state.outfit);
  stage.setSpeed(Number($("speed").value));
  if (save && !classViews) saveSetting(VIEW_KEY, stage === stage2d ? "2d" : "3d");
  if (state.level) {
    invalidateRun();
    stage.load(state.level, currentWorld(), stageGoal());
    describeStage();
  }
}

// --- language ------------------------------------------------------------------------

function renderLanguages() {
  fillLangSelect($("lang")); // a drawn flag and "SK"; the full name on hover
}

async function changeLanguage(code, { save = true } = {}) {
  stopPlayback();
  setLang(code, { save });
  translatePage();
  players.relabel();
  updateButtons();
  state.levels = await api.levels(state.animal);
  state.animals = await api.animals();
  renderLevelOptions();
  if (!state.level) return;
  const level = state.shared
    ? await api.previewLevel(state.shared, state.animal)
    : await api.level(state.level.id, state.animal);
  state.level = level;
  code.setCommands(level.pack.actions); // the animal's own command names, in their blocks' colours
  renderGoal();
  renderWorlds();
  renderAnimals();
  renderFiles();
  invalidateRun();
  stage.load(level, currentWorld(), stageGoal());
  describeStage();
  blocks.redefine();
  blocks.setPalette(level.unlockedBlocks);
  const text = state.text;
  if (text) {
    const parsed = await api.parse(text);
    if (parsed.ok) blocks.load(parsed.program, level.pack.actions, text, parsed.positions);
  } else {
    blocks.load({ type: "Program", id: "program", body: [] }, level.pack.actions, "", {});
  }
  renderTints();
}

// --- the console: what print() writes, as the run reaches each print() ----------------

const MAX_CONSOLE = 20000; // characters kept; older text scrolls away

function printToConsole(text, glow) {
  const box = $("console");
  const piece = el("span", glow ? { class: "fresh" } : {}, text);
  box.append(piece);
  while (box.textContent.length > MAX_CONSOLE && box.firstChild !== piece) box.firstChild.remove();
  box.scrollTop = box.scrollHeight;
  if (glow) setTimeout(() => piece.classList.remove("fresh"), 50);
}

// An error that stopped the run, like Python prints it: where it happened (from the outside
// in), then the line and what went wrong. A program Python can't read shows its first
// problem. In red, after what was printed before it.
function problemsToConsole(run) {
  const lines = [];
  const error = run.error;
  if (error) {
    const trace = error.traceback || [];
    if (trace.length > 1) {
      lines.push(t("Where it happened, from the outside in:"));
      for (const frame of trace.slice(-8)) {
        lines.push(`  ${frame.function === "<program>" ? t("line {line}, in the program", frame) : t("line {line}, in {function}()", frame)}`);
      }
    }
    lines.push((error.line ? t("Line {line}: ", { line: error.line }) : "") + error.message);
  } else {
    const problem = (run.diagnostics || []).find((d) => d.severity === "error");
    if (problem) lines.push(t("line {line}: {message}", problem));
  }
  if (!lines.length) return;
  const box = $("console");
  box.append(el("span", { class: "console-error" }, `${lines.join("\n")}\n`));
  box.scrollTop = box.scrollHeight;
}

function clearConsole() {
  $("console").replaceChildren();
}

// --- running -----------------------------------------------------------------------

function invalidateRun() {
  stopPlayback();
  state.run = null;
  state.stepIndex = 0;
  renderLanes(null);
  $("result").replaceChildren();
  $("feeling").replaceChildren();
  clearConsole();
  state.stack = [];
  renderStack();
  code.highlight(0);
  blocks.highlight(null);
}

// The call stack as nested burrows: one box for every function that is still running.
function renderStack() {
  $("callstack").replaceChildren(
    ...state.stack.map((frame, i) =>
      el(
        "div",
        { class: `frame${i === state.stack.length - 1 ? " active" : ""}`, style: `margin-left:${i * 14}px` },
        `${frame.name}(${frame.args.join(", ")})`,
      ),
    ),
  );
}

function stopPlayback() {
  state.token += 1;
  state.playing = false;
  updateButtons();
}

function updateButtons() {
  $("run").textContent = state.playing ? t("⏸ Pause") : t("▶ Run");
  // a predict level: first tap where the animal will stop
  const guessFirst = state.level?.cub === "predict" && !state.guess && !state.playing;
  $("run").disabled = (state.over && !state.playing) || guessFirst;
  $("run").title = guessFirst ? t("Tap a square first: where will it stop?") : "";
  $("step").disabled = state.over;
}

// --- lanes: tasks and threads that run at the same time, on a simulated clock ---------------

const LANE_COLOURS = ["#4C97FF", "#59C059", "#FFAB19", "#CF63CF", "#5CB1D6", "#FF8C1A", "#995BA5", "#D65C5C"];
const lanes = { marks: [], rows: new Map(), cursor: null, end: 1 };

function renderLanes(run) {
  const box = $("lanes");
  lanes.marks = [];
  lanes.rows = new Map();
  if (!run?.lanes?.length || !run.steps) {
    box.hidden = true;
    box.replaceChildren();
    $("timeline").hidden = true;
    return;
  }
  lanes.end = Math.max(run.time || 0, 1);
  const rows = run.lanes.map((name, i) => {
    const track = el("div", { class: "lane-track" });
    track.style.setProperty("--lane", LANE_COLOURS[i % LANE_COLOURS.length]);
    const row = el("div", { class: "lane" }, el("span", { class: "lane-name", title: name }, name), track);
    lanes.rows.set(name, { row, track });
    return row;
  });
  const waitingSince = new Map(); // lane -> the tick it started waiting
  run.steps.forEach((step, index) => {
    const lane = lanes.rows.get(step.lane || "main");
    if (!lane) return;
    const waiting = step.note === t("waiting");
    const since = waitingSince.get(step.lane);
    if (since !== undefined && step.time > since) {
      // a bar for the time this lane waited while the others went on
      const bar = el("span", { class: "lane-span" });
      bar.style.left = `${(since / lanes.end) * 100}%`;
      bar.style.width = `${((step.time - since) / lanes.end) * 100}%`;
      lane.track.append(bar);
    }
    if (waiting) waitingSince.set(step.lane, step.time);
    else waitingSince.delete(step.lane);
    const mark = el("span", { class: `lane-mark${waiting ? " wait" : ""}`, title: `${step.lane} @ ${step.time}` });
    mark.style.left = `${((step.time || 0) / lanes.end) * 100}%`;
    lane.track.append(mark);
    lanes.marks[index] = mark;
  });
  lanes.cursor = el("span", { class: "lane-cursor" });
  rows[0].querySelector(".lane-track").append(lanes.cursor);
  box.replaceChildren(el("div", { class: "note" }, t("At the same time (done by tick {n}):", { n: run.time })), ...rows);
  box.hidden = false;
  const slider = $("timeline-range");
  slider.max = String(run.steps.length);
  slider.value = "0";
  $("timeline").hidden = false;
}

function markLanes(index) {
  const run = state.run;
  if (!run?.lanes?.length) return;
  lanes.marks.forEach((mark, i) => mark?.classList.toggle("done", i < index));
  const step = run.steps[Math.max(index - 1, 0)];
  for (const [name, { row }] of lanes.rows) row.classList.toggle("active", name === step?.lane);
  if (lanes.cursor) lanes.cursor.style.left = `${((step?.time || 0) / lanes.end) * 100}%`;
  $("timeline-range").value = String(index);
}

// Jump to a moment on the timeline: replay the steps up to it without waiting.
async function seek(index) {
  const run = state.run;
  if (!run?.steps) return;
  stopPlayback();
  const token = state.token;
  stage.reset();
  clearConsole();
  state.stack = [];
  renderStack();
  const saved = stage.duration;
  stage.duration = 0;
  for (let i = 0; i < index && token === state.token; i++) await playStep(run.steps[i]);
  stage.duration = saved;
  state.stepIndex = index;
  markLanes(index);
}

async function ensureRun() {
  if (state.run) return state.run;
  stage.reset();
  const result = state.shared
    ? await api.runLevelData(state.shared, state.text, state.variant)
    : await api.run(state.level.id, state.text, state.player?.id, state.variant, { animal: state.level.pack.id, hints: state.hintsShown });
  state.run = result;
  state.stepIndex = 0;
  renderLanes(result);
  showDiagnostics(result.diagnostics || []);
  if (result.progress) {
    state.progress[state.level.id] = result.progress;
    renderLevelOptions();
  }
  return result;
}

async function playStep(step) {
  code.highlight(step.line, step.error ? "error" : "run");
  blocks.highlight(blockAtLine(step.line));
  for (const event of step.events) {
    if (event.type === "call") {
      state.stack.push(event);
      renderStack();
    } else if (event.type === "return") {
      state.stack.pop();
      renderStack();
    } else if (event.type === "print") {
      printToConsole(event.text, stage.duration > 0);
    } else {
      if (stage.duration > 0) fun.event(event);
      await stage.play(event);
    }
  }
}

async function play({ single = false } = {}) {
  if (state.over) return players.showGoodbye(state.level?.pack);
  let run;
  try {
    run = await ensureRun();
  } catch (error) {
    // e.g. the teacher paused the class, or picked other levels for today
    $("result").replaceChildren(el("div", { class: "message err" }, error.message));
    if (error.status !== 423 && error.status !== 403) pilotUI.error();
    return;
  }
  if (!run.steps) {
    showResult(run);
    problemsToConsole(run);
    return;
  }
  const token = ++state.token;
  if (state.stepIndex === 0) fun.runStarted();
  state.playing = !single;
  updateButtons();
  while (state.stepIndex < run.steps.length) {
    // steps of different lanes at the same tick happen together: play them together
    const first = run.steps[state.stepIndex];
    const batch = [first];
    while (
      !single && run.lanes?.length && state.stepIndex + batch.length < run.steps.length &&
      batch.length < 16 && run.steps[state.stepIndex + batch.length].time === first.time
    ) {
      batch.push(run.steps[state.stepIndex + batch.length]);
    }
    state.stepIndex += batch.length;
    await Promise.all(batch.map((step) => playStep(step)));
    markLanes(state.stepIndex);
    if (token !== state.token) return;
    if (single) break;
    await new Promise((resolve) => setTimeout(resolve, stage.duration / 2));
    if (token !== state.token) return;
  }
  state.playing = false;
  updateButtons();
  if (state.stepIndex >= run.steps.length) finish(run);
}

function finish(run) {
  // a run without print events (made by an older engine): show its output at the end
  if (run.output?.length && !$("console").textContent) printToConsole(`${run.output.join("\n")}\n`, false);
  problemsToConsole(run);
  if (!run.error) {
    code.highlight(0);
    blocks.highlight(null);
  }
  showResult(run);
  stage.showFeeling(run.feeling);
  fun.finished(run, $("result"));
  if (state.over) setTimeout(() => players.showGoodbye(state.level?.pack), 1500); // let them see the result first
}

function showFeeling(feeling) {
  if (!feeling) {
    $("feeling").replaceChildren();
    return;
  }
  $("feeling").replaceChildren(
    el("span", { class: "face", "aria-hidden": "true" }, feeling.face),
    el("span", {}, feeling.text),
  );
}

function showResult(run) {
  const parts = [];
  showFeeling(run.feeling);
  if (!run.check) {
    parts.push(el("div", { class: "message err" }, t("Python can't read this program yet. Look under the code.")));
  } else {
    const earned = run.check.stars.filter((s) => s.earned).length;
    const prefix = run.error && run.error.line ? t("Line {line}: ", { line: run.error.line }) : "";
    parts.push(
      el("div", { class: "stars", "aria-label": t("{n} of 3 stars", { n: earned }) }, "★".repeat(earned) + "☆".repeat(3 - earned)),
      el("div", { class: `message ${run.check.solved ? "ok" : "err"}` }, prefix + run.check.message),
      el("ul", {}, ...run.check.stars.map((s) => el("li", {}, `${s.earned ? "✓" : "–"} ${s.label}`))),
    );
    let trace = run.error?.traceback || [];
    if (trace.length > 6) {
      // deep recursion: the start and the end tell the story
      trace = [...trace.slice(0, 3), { gap: trace.length - 5 }, ...trace.slice(-2)];
    }
    if (trace.length > 1) {
      parts.push(
        el("p", {}, t("Where it happened, from the outside in:")),
        el(
          "ol",
          { class: "traceback" },
          ...trace.map((f) =>
            el("li", {}, f.gap ? t("… {n} more …", { n: f.gap }) : f.function === "<program>" ? t("line {line}, in the program", f) : t("line {line}, in {function}()", f)),
          ),
        ),
      );
    }
    const files = Object.entries(run.files || {});
    if (files.length) {
      parts.push(
        el(
          "div",
          { class: "files-written" },
          ...files.map(([name, text]) => el("details", {}, el("summary", {}, `📄 ${name}`), el("pre", {}, text))),
        ),
      );
    }
  }
  for (const sticker of run.newStickers || []) {
    parts.push(el("div", { class: "sticker-new" }, `${sticker.emoji} ${t("New sticker: {name}", sticker)}`));
  }
  if (run.suggestion) {
    const go = el("button", { type: "button", class: "small" }, t("Practise first"));
    go.addEventListener("click", () => loadLevel(run.suggestion.level));
    parts.push(
      el(
        "div",
        { class: "suggestion" },
        t("Tricky one! Want to practise {concept} on “{title}” first? You can come back any time.", run.suggestion),
        " ",
        go,
      ),
    );
  }
  if (run.savedRun) {
    const story = el("button", { type: "button", class: "small" }, t("📖 Make a storybook"));
    story.addEventListener("click", () => openStory(run.savedRun));
    const save = el("button", { type: "button", class: "small" }, t("💾 Save this run"));
    save.addEventListener("click", () => download(`${run.level}.run.json`, JSON.stringify(run.savedRun)));
    const tools = el("div", { class: "result-tools" }, story, save);
    if (inClass && !state.shared && state.player) {
      const share = el("button", { type: "button", class: "small" }, t("🙋 Share with the class"));
      share.addEventListener("click", async () => {
        share.disabled = true;
        const message = await classroom.shareProgram(state.level, state.text, state.level.pack.id);
        tools.append(el("span", { class: "note" }, message));
      });
      tools.append(share);
    }
    parts.push(tools);
  }
  if (run.check?.solved) parts.push(pilotUI.smileyRow());
  const guess = predictFeedback(run);
  if (guess) parts.unshift(el("div", { class: "message ok predict-feedback" }, guess));
  $("result").replaceChildren(...parts.filter(Boolean));
  speak([guess, run.feeling?.text, run.check?.message].filter(Boolean).join(" "));
  pilotUI.afterRun(run);
}

async function openStory(savedRun) {
  const page = window.open("", "_blank");
  try {
    const { html } = await api.story(savedRun);
    if (page) {
      page.document.open();
      page.document.write(html);
      page.document.close();
    } else {
      download("storybook.html", html);
    }
  } catch (error) {
    page?.close();
    showDiagnostics([{ line: 0, severity: "error", message: error.message }]);
  }
}

function download(name, text) {
  const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  const link = el("a", { href: url, download: name });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// --- the zoo: stickers in the habitat, outfits, card codes ------------------------------

const zoo = { habitat: null, dragging: null };

async function openZoo() {
  if (!state.player) return players.choose();
  zoo.habitat = await api.habitat(state.player.id);
  $("zoo-error").textContent = "";
  $("card-code").value = "";
  const cardAnimal = state.level?.pack.id || "monkey";
  $("cards-link").href = window.CODEZOO_OFFLINE
    ? `cards-${cardAnimal}-${lang()}.html`
    : `cards.html?animal=${encodeURIComponent(cardAnimal)}&lang=${lang()}`;
  $("scan-card").hidden = !("BarcodeDetector" in window && navigator.mediaDevices?.getUserMedia);
  renderZoo();
  $("zoo-dialog").showModal();
}

function renderZoo() {
  const { stickers, placed, outfits, outfit } = zoo.habitat;
  const area = $("habitat");
  const wearing = outfits.find((o) => o.id === outfit)?.emoji || "";
  const animal = el("div", { class: "home-animal", "aria-hidden": "true" }, state.level?.pack.emoji || "🐾");
  if (wearing) animal.append(el("span", { class: "outfit" }, wearing));
  const pieces = stickers
    .filter((s) => placed[s.id])
    .map((s) => {
      const node = el("span", { class: "placed", title: s.name, "data-id": s.id }, s.emoji);
      node.style.left = `${placed[s.id][0]}%`;
      node.style.top = `${placed[s.id][1]}%`;
      node.addEventListener("pointerdown", (event) => startDrag(event, s.id, node));
      return node;
    });
  area.replaceChildren(animal, ...pieces);
  const tray = stickers.filter((s) => !placed[s.id]);
  $("sticker-tray").replaceChildren(
    ...(tray.length
      ? tray.map((s) => {
          const button = el("button", { type: "button", title: s.name, "aria-label": s.name }, s.emoji);
          button.addEventListener("click", () => place(s.id, [20 + Math.random() * 60, 20 + Math.random() * 60]));
          return button;
        })
      : [el("span", { class: "note" }, stickers.length ? t("Every sticker is in the habitat.") : t("Solve levels to earn stickers!"))]),
  );
  $("outfits").replaceChildren(
    ...outfits.map((o) => {
      const button = el(
        "button",
        { type: "button", "aria-pressed": String(o.id === outfit), title: o.open ? "" : t("Needs {n} stickers", { n: o.needs }) },
        o.emoji || t("nothing"),
      );
      button.disabled = !o.open;
      button.addEventListener("click", () => saveHabitat({ outfit: o.id }));
      return button;
    }),
  );
}

async function saveHabitat(body) {
  try {
    zoo.habitat = await api.setHabitat(state.player.id, body);
    state.outfit = zoo.habitat.outfits.find((o) => o.id === zoo.habitat.outfit)?.emoji || "";
    stage.setOutfit?.(state.outfit);
    renderZoo();
  } catch (error) {
    $("zoo-error").textContent = error.message;
  }
}

function place(id, spot) {
  saveHabitat({ placed: { ...zoo.habitat.placed, [id]: spot.map((v) => Math.round(Math.max(0, Math.min(100, v)))) } });
}

function startDrag(event, id, node) {
  event.preventDefault();
  node.setPointerCapture(event.pointerId);
  const box = $("habitat").getBoundingClientRect();
  const move = (e) => {
    node.style.left = `${((e.clientX - box.left) / box.width) * 100}%`;
    node.style.top = `${((e.clientY - box.top) / box.height) * 100}%`;
  };
  const up = (e) => {
    node.removeEventListener("pointermove", move);
    node.removeEventListener("pointerup", up);
    place(id, [((e.clientX - box.left) / box.width) * 100, ((e.clientY - box.top) / box.height) * 100]);
  };
  node.addEventListener("pointermove", move);
  node.addEventListener("pointerup", up);
}

async function unlockCard(code) {
  try {
    const result = await api.unlock(state.player.id, code);
    $("zoo-error").textContent = "";
    zoo.habitat = await api.habitat(state.player.id);
    renderZoo();
    const open = el("button", { type: "button", class: "small" }, t("Play it now"));
    open.addEventListener("click", () => {
      $("zoo-dialog").close();
      loadLevel(result.card.level);
    });
    $("card-result").replaceChildren(
      `${result.sticker.emoji} ${result.new ? t("New sticker: {name}", result.sticker) : t("You already have this card's sticker.")} `,
      open,
    );
  } catch (error) {
    $("card-result").replaceChildren();
    $("zoo-error").textContent = error.message;
  }
}

// Optional: read the QR code on a card with the camera. The picture stays on this device.
async function scanCard() {
  const video = $("scan-video");
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
  } catch {
    $("zoo-error").textContent = t("The camera is not available. Type the code instead.");
    return;
  }
  video.hidden = false;
  video.srcObject = stream;
  await video.play();
  const detector = new window.BarcodeDetector({ formats: ["qr_code"] });
  const stop = () => {
    for (const track of stream.getTracks()) track.stop();
    video.hidden = true;
  };
  const started = Date.now();
  while (!video.hidden && Date.now() - started < 20000 && $("zoo-dialog").open) {
    const codes = await detector.detect(video).catch(() => []);
    const found = codes.find((c) => c.rawValue.toLowerCase().startsWith("codezoo:card:"));
    if (found) {
      stop();
      $("card-code").value = found.rawValue.slice("codezoo:card:".length);
      return unlockCard(found.rawValue);
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  stop();
}

// --- wiring ------------------------------------------------------------------------

$("run").addEventListener("click", () => {
  if (state.playing) stopPlayback();
  else play();
});
$("step").addEventListener("click", () => {
  stopPlayback();
  play({ single: true });
});
$("reset").addEventListener("click", () => {
  invalidateRun();
  stage.reset();
});
$("speed").addEventListener("input", (event) => stage.setSpeed(Number(event.target.value)));
$("timeline-range").addEventListener("input", (event) => seek(Number(event.target.value)));
$("python-select").addEventListener("change", async (event) => {
  setPython(event.target.value || null);
  saveSetting(PYTHON_KEY, event.target.value);
  state.levels = await api.levels(state.animal);
  renderLevelOptions();
  if (state.level) loadLevel(state.level.id);
});
$("edit-code").addEventListener("change", (event) => code.setEditable(event.target.checked));
$("level-select").addEventListener("change", (event) => loadLevel(event.target.value));
$("player").addEventListener("click", () => players.choose());
$("view-3d").addEventListener("change", (event) => useView(event.target.checked));
$("lang").addEventListener("change", (event) => changeLanguage(event.target.value));
window.addEventListener("hashchange", () => {
  const id = location.hash.slice(1);
  if (id.startsWith("play=")) {
    loadShared(id.slice(5));
    return;
  }
  if (id !== state.level?.id && visibleLevels().some((l) => l.id === id)) loadLevel(id);
});
$("grownups").addEventListener("click", () => players.openGrownups());
$("animal-select").addEventListener("change", (event) => switchAnimal(event.target.value));
$("zoo").addEventListener("click", () => openZoo());
$("look").addEventListener("click", openLook);
$("reset-view").addEventListener("click", resetAllZoom);
$("card-form").addEventListener("submit", (event) => {
  event.preventDefault();
  unlockCard($("card-code").value);
});
$("scan-card").addEventListener("click", () => scanCard());
$("zoo-close").addEventListener("click", () => $("zoo-dialog").close());

for (const tab of document.querySelectorAll(".tabs button")) {
  tab.addEventListener("click", () => {
    for (const other of document.querySelectorAll(".tabs button")) other.classList.toggle("active", other === tab);
    for (const pane of document.querySelectorAll(".pane")) pane.classList.toggle("active", pane.dataset.pane === tab.dataset.tab);
    if (tab.dataset.tab === "blocks") blocks.resize();
  });
}

setupSplitters({
  panes: $("panes"),
  stageSplit: $("split-stage"),
  paneSplit: $("split-panes"),
  headSplit: $("split-head"),
  consoleSplit: $("split-console"),
  onResize: () => blocks.resize(),
});

async function start() {
  translatePage();
  players.relabel();
  renderLanguages();
  updateButtons();
  stage.setSpeed(Number($("speed").value));
  const want3d = readSetting(VIEW_KEY) !== "2d";
  $("view-3d").checked = want3d;
  await useView(want3d);
  state.animal = readSetting(ANIMAL_KEY);
  const info = await api.info();
  if (info.hub) {
    // a classroom hub: open in the class's language (unless the link names one); a child
    // can still switch, and that choice is remembered in this browser
    if (info.hub.lang && !urlLang() && info.hub.lang !== lang()) {
      setLang(info.hub.lang, { save: false });
      translatePage();
      players.relabel();
      renderLanguages();
      updateButtons();
      blocks.redefine();
    }
    // join with the class code before anything else (levels need it)
    inClass = true;
    players.classroom = classroom;
    await classroom.start(info);
  }
  const releases = info.releases.filter((r) => r.readable).map((r) => r.version);
  $("python-select").replaceChildren(
    el("option", { value: "" }, t("Python {version} (newest)", { version: info.default })),
    ...releases.map((v) => el("option", { value: v }, `Python ${v}`)),
  );
  const python = readSetting(PYTHON_KEY);
  if (python && releases.includes(python)) {
    $("python-select").value = python;
    setPython(python);
  }
  [state.levels, state.animals] = await Promise.all([api.levels(state.animal), api.animals()]);
  renderLevelOptions();
  const wanted = location.hash.slice(1);
  if (!(wanted.startsWith("play=") && (await loadShared(wanted.slice(5))))) {
    // any level in the address; Cub mode (known once the player is) moves on if it isn't theirs
    const first = visibleLevels().find((l) => l.assigned) || visibleLevels()[0]; // today's first
    await loadLevel(state.levels.some((l) => l.id === wanted) ? wanted : first.id);
  }
  if (!inClass) await players.start(); // in a class, joining picked the player
}

start().catch((error) => {
  $("result").replaceChildren(el("div", { class: "message err" }, t("Could not start: {message}", { message: error.message })));
});
