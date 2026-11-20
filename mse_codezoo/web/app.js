// CodeZoo web client: three panes (stage, blocks, code) over one program.
//
// Blocks change -> IR from blocks -> engine prints Python -> code pane.
// Code typed    -> engine parses -> IR -> blocks rebuilt (if the code parses).
// Run           -> engine runs the code in the world shown -> steps animate the stage and
//                  light up line + block; the engine also checks the level's other worlds.
//                  With a player chosen, the engine saves the result to their progress.

import { api } from "./api.js";
import { createWorkspace } from "./blocks.js";
import { CodeView } from "./code.js";
import { LANGS, initialLang, lang, setLang, t, translatePage } from "./i18n.js";
import { setupSplitters } from "./layout.js";
import { Players } from "./players.js";
import { Stage } from "./stage.js";

const $ = (id) => document.getElementById(id);
const HEARTBEAT_SECONDS = 30;
const VIEW_KEY = "codezoo.view";
const ANIMAL_KEY = "codezoo.animal";

setLang(initialLang());

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
};

const stage2d = new Stage($("stage"));
let stage3d = null;
let stage = stage2d;

const code = new CodeView({
  textarea: $("code"),
  gutter: $("gutter"),
  mark: $("line-mark"),
  onInput: (text) => debounce("parse", 350, () => codeChanged(text)),
});
const blocks = createWorkspace($("blockly"), () => debounce("print", 150, blocksChanged));
const players = new Players({ onChoose: playerChosen, onSettingsChanged: checkToday });

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
  node.append(...children);
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
    showDiagnostics([]);
    invalidateRun();
  } catch (error) {
    showDiagnostics([{ line: 0, severity: "error", message: error.message }]);
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
}

async function loadProgram(text) {
  if (!text) {
    code.setText("");
    blocks.load({ type: "Program", id: "program", body: [] }, state.level.pack.actions, "", {});
    return;
  }
  const parsed = await api.parse(text);
  state.text = text;
  code.setText(text);
  if (parsed.ok) {
    state.sourceMap = parsed.positions;
    blocks.load(parsed.program, state.level.pack.actions, text, parsed.positions);
  }
  showDiagnostics(parsed.diagnostics);
}

// --- players and the daily limit ----------------------------------------------------

async function playerChosen(profile) {
  state.player = profile;
  state.progress = {};
  state.over = false;
  state.outfit = "";
  if (profile) {
    const progress = await api.progress(profile.id);
    state.progress = progress.levels;
    applyToday(progress.today);
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
  select.replaceChildren(
    ...state.levels.map((l) => {
      const stars = starText(state.progress[l.id]?.stars || 0);
      const only = l.signature ? `${animalEmoji(l.animal)} ` : "";
      return el("option", { value: l.id }, `${l.id} · ${only}${l.title}${stars ? `  ${stars}` : ""}`);
    }),
  );
  if (state.level) select.value = state.level.id;
}

const MUST_USE = {
  For: "for", While: "while", If: "if", Compare: "== <", BoolOp: "and / or", UnaryOp: "not",
  FString: 'f"…"', MethodCall: ".method()", Subscript: "[ ]", Assign: "x = …",
  AugAssign: "x += …", BinOp: "+ * /", Comment: "#", Break: "break", Continue: "continue",
  FunctionDef: "def", Return: "return", Try: "try / except", Raise: "raise", Assert: "assert",
  Import: "import", List: "[…]", Tuple: "(a, b)", Dict: "{key: value}", Set: "{a, b}",
  Global: "global", Comprehension: "[… for …]", Recursion: t("a function that calls itself"),
};

const animalEmoji = (id) => state.animals.find((a) => a.id === id)?.emoji || "🐾";

function describeGoal(level, goal) {
  const pack = level.pack;
  const animal = pack.animalName || pack.animal;
  const one = (tile) => pack.itemNames?.[tile]?.one || pack.items[tile] || "item";
  const many = (tile) => pack.itemNames?.[tile]?.many || one(tile);
  switch (goal.type) {
    case "collect_all": {
      let text = t("Help the {animal} collect every {item}", { animal, item: one(goal.item), items: many(goal.item) });
      if (goal.avoid) text += `, ${t("but leave every {item} alone", { item: one(goal.avoid) })}`;
      return text;
    }
    case "reach":
      return t("Help the {animal} reach square ({x}, {y})", { animal, x: goal.at[0], y: goal.at[1] });
    case "say":
      if (goal.texts) return t("Make the {animal} say: {texts}", { animal, texts: goal.texts.map((x) => `“${x}”`).join(", ") });
      return t("Make the {animal} say “{text}”", { animal, text: goal.text });
    case "avoid":
      return t("Leave every {item} alone", { item: one(goal.item) });
    case "build":
      return t("Build a dam from exactly: {logs}", {
        logs: Object.entries(goal.logs).map(([log, n]) => `${n} × ${log}`).join(", "),
      });
    case "all":
      return goal.goals
        .map((part, i) => {
          const text = describeGoal(level, part);
          return i ? text.charAt(0).toLowerCase() + text.slice(1) : text;
        })
        .join("; ");
  }
  return goal.type;
}

function renderGoal() {
  const level = state.level;
  const rules = [];
  if (level.constraints.maxLines) rules.push(t("{n} lines or fewer", { n: level.constraints.maxLines }));
  if (level.constraints.mustUse?.length) {
    rules.push(t("use {what}", { what: level.constraints.mustUse.map((n) => MUST_USE[n] || n).join(", ") }));
  }
  const hintButton = el("button", { type: "button", class: "small" }, t("Hint"));
  const hint = el("span", { class: "hint" });
  const showHint = () => {
    hint.textContent = level.hints[state.hintsShown - 1] || "";
    hintButton.disabled = state.hintsShown >= level.hints.length;
  };
  hintButton.addEventListener("click", () => {
    if (state.hintsShown < level.hints.length) state.hintsShown += 1;
    showHint();
  });
  showHint();
  hintButton.disabled = level.hints.length === 0 || state.hintsShown >= level.hints.length;
  const parts = [
    el("h2", {}, level.title),
    el("p", {}, `${describeGoal(level, currentGoal())}.`),
    el("p", {}, t("Stars for: {rules}", { rules: rules.length ? rules.join("; ") : t("just solving it") })),
  ];
  if (level.starter) parts.push(el("p", {}, t("This program has a bug. Run it, watch, then fix it!")));
  parts.push(el("div", { class: "hint-row" }, hintButton, hint));
  $("goal").replaceChildren(...parts);
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
  stage.load(state.level, currentWorld(), currentGoal());
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
  const level = await api.level(id, state.animal);
  state.level = level;
  state.variant = 0;
  state.hintsShown = 0;
  state.text = "";
  state.sourceMap = {};
  invalidateRun();
  location.hash = id;
  $("level-select").value = id;

  renderGoal();
  renderWorlds();
  renderAnimals();
  renderFiles();
  stage.load(level, currentWorld(), currentGoal());
  stage.setOutfit?.(state.outfit);
  showDiagnostics([]);
  const typing = level.mode === "both_editable" || level.mode === "code_first";
  $("edit-code").checked = typing;
  code.setEditable(typing);
  blocks.setPalette(level.unlockedBlocks);
  await loadProgram(level.starter);
  blocks.resize();
}

// --- stage view: 2D or 3D -----------------------------------------------------------

async function useView(want3d) {
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
  saveSetting(VIEW_KEY, stage === stage2d ? "2d" : "3d");
  if (state.level) {
    invalidateRun();
    stage.load(state.level, currentWorld(), currentGoal());
  }
}

// --- language ------------------------------------------------------------------------

function renderLanguages() {
  $("lang").replaceChildren(
    ...Object.entries(LANGS).map(([code, label]) => el("option", { value: code }, label)),
  );
  $("lang").value = lang();
}

async function changeLanguage(code) {
  stopPlayback();
  setLang(code);
  translatePage();
  players.relabel();
  updateButtons();
  state.levels = await api.levels();
  state.animals = await api.animals();
  renderLevelOptions();
  if (!state.level) return;
  const level = await api.level(state.level.id, state.animal);
  state.level = level;
  renderGoal();
  renderWorlds();
  renderAnimals();
  renderFiles();
  invalidateRun();
  stage.load(level, currentWorld(), currentGoal());
  blocks.redefine();
  blocks.setPalette(level.unlockedBlocks);
  const text = state.text;
  if (text) {
    const parsed = await api.parse(text);
    if (parsed.ok) blocks.load(parsed.program, level.pack.actions, text, parsed.positions);
  } else {
    blocks.load({ type: "Program", id: "program", body: [] }, level.pack.actions, "", {});
  }
}

// --- running -----------------------------------------------------------------------

function invalidateRun() {
  stopPlayback();
  state.run = null;
  state.stepIndex = 0;
  $("result").replaceChildren();
  $("feeling").replaceChildren();
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
  $("run").disabled = state.over && !state.playing;
  $("step").disabled = state.over;
}

async function ensureRun() {
  if (state.run) return state.run;
  stage.reset();
  const result = await api.run(state.level.id, state.text, state.player?.id, state.variant, {
    animal: state.level.pack.id,
  });
  state.run = result;
  state.stepIndex = 0;
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
    } else {
      await stage.play(event);
    }
  }
}

async function play({ single = false } = {}) {
  if (state.over) return players.showGoodbye(state.level?.pack);
  const run = await ensureRun();
  if (!run.steps) {
    showResult(run);
    return;
  }
  const token = ++state.token;
  state.playing = !single;
  updateButtons();
  while (state.stepIndex < run.steps.length) {
    const step = run.steps[state.stepIndex++];
    await playStep(step);
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
  if (!run.error) {
    code.highlight(0);
    blocks.highlight(null);
  }
  showResult(run);
  stage.showFeeling(run.feeling);
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
    if (run.output?.length) parts.push(el("pre", { class: "printed" }, run.output.join("\n")));
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
    parts.push(el("div", { class: "result-tools" }, story, save));
  }
  $("result").replaceChildren(...parts);
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
  $("cards-link").href = `cards.html?animal=${encodeURIComponent(state.level?.pack.id || "monkey")}&lang=${lang()}`;
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
$("edit-code").addEventListener("change", (event) => code.setEditable(event.target.checked));
$("level-select").addEventListener("change", (event) => loadLevel(event.target.value));
$("player").addEventListener("click", () => players.choose());
$("view-3d").addEventListener("change", (event) => useView(event.target.checked));
$("lang").addEventListener("change", (event) => changeLanguage(event.target.value));
window.addEventListener("hashchange", () => {
  const id = location.hash.slice(1);
  if (id !== state.level?.id && state.levels.some((l) => l.id === id)) loadLevel(id);
});
$("grownups").addEventListener("click", () => players.openGrownups());
$("animal-select").addEventListener("change", (event) => {
  state.animal = event.target.value;
  saveSetting(ANIMAL_KEY, state.animal);
  if (state.level) loadLevel(state.level.id);
});
$("zoo").addEventListener("click", () => openZoo());
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
  [state.levels, state.animals] = await Promise.all([api.levels(), api.animals()]);
  renderLevelOptions();
  const wanted = location.hash.slice(1);
  await loadLevel(state.levels.some((l) => l.id === wanted) ? wanted : state.levels[0].id);
  await players.start();
}

start().catch((error) => {
  $("result").replaceChildren(el("div", { class: "message err" }, t("Could not start: {message}", { message: error.message })));
});
