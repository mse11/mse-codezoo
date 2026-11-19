// CodeZoo web client: three panes (stage, blocks, code) over one program.
//
// Blocks change -> IR from blocks -> engine prints Python -> code pane.
// Code typed    -> engine parses -> IR -> blocks rebuilt (if the code parses).
// Run           -> engine runs the code -> steps animate the stage and light up line + block;
//                  with a player chosen, the engine also saves the result to their progress.

import { api } from "./api.js";
import { createWorkspace } from "./blocks.js";
import { CodeView } from "./code.js";
import { setupSplitters } from "./layout.js";
import { Players } from "./players.js";
import { Stage } from "./stage.js";

const $ = (id) => document.getElementById(id);
const HEARTBEAT_SECONDS = 30;

const state = {
  levels: [],
  level: null,
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
};

const stage = new Stage($("stage"));
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

function showDiagnostics(diagnostics) {
  $("diagnostics").replaceChildren(
    ...diagnostics.map((d) => el("li", { class: d.severity }, `line ${d.line}: ${d.message}`)),
  );
}

function blockAtLine(line) {
  for (const [id, span] of Object.entries(state.sourceMap)) {
    if (span.line === line && blocks.workspace.getBlockById(id)) return id;
  }
  return null;
}

const starText = (n) => (n ? "★".repeat(n) + "☆".repeat(3 - n) : "");

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

// --- players and the daily limit ----------------------------------------------------

async function playerChosen(profile) {
  state.player = profile;
  state.progress = {};
  state.over = false;
  if (profile) {
    const progress = await api.progress(profile.id);
    state.progress = progress.levels;
    applyToday(progress.today);
  }
  renderLevelOptions();
  updateButtons();
}

function applyToday(today) {
  state.over = Boolean(today?.over);
  updateButtons();
  if (state.over && !state.playing) players.showGoodbye();
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
      return el("option", { value: l.id }, `${l.id} · ${l.title}${stars ? `  ${stars}` : ""}`);
    }),
  );
  if (state.level) select.value = state.level.id;
}

function describeGoal(level) {
  const goal = level.goal;
  if (goal.type === "collect_all") return `Help the ${level.pack.animal} collect every ${level.pack.items[goal.item] || "item"}.`;
  if (goal.type === "reach") return `Help the ${level.pack.animal} reach square (${goal.at[0]}, ${goal.at[1]}).`;
  return goal.type;
}

function renderGoal() {
  const level = state.level;
  const rules = [];
  if (level.constraints.maxLines) rules.push(`${level.constraints.maxLines} lines or fewer`);
  if (level.constraints.mustUse?.length) rules.push(`use ${level.constraints.mustUse.join(", ")}`);
  const hintButton = el("button", { type: "button", class: "small" }, "Hint");
  const hint = el("span", { class: "hint" });
  hintButton.addEventListener("click", () => {
    if (state.hintsShown < level.hints.length) state.hintsShown += 1;
    hint.textContent = level.hints[state.hintsShown - 1] || "";
    hintButton.disabled = state.hintsShown >= level.hints.length;
  });
  hintButton.disabled = level.hints.length === 0;
  const parts = [
    el("h2", {}, `${level.title}`),
    el("p", {}, describeGoal(level)),
    el("p", {}, `Stars for: ${rules.length ? rules.join("; ") : "just solving it"}`),
  ];
  if (level.starter) parts.push(el("p", {}, "This program has a bug. Run it, watch, then fix it!"));
  parts.push(el("div", { class: "hint-row" }, hintButton, hint));
  $("goal").replaceChildren(...parts);
}

async function loadLevel(id) {
  stopPlayback();
  const level = await api.level(id);
  state.level = level;
  state.hintsShown = 0;
  state.text = "";
  state.sourceMap = {};
  invalidateRun();
  location.hash = id;
  $("level-select").value = id;

  renderGoal();
  stage.load(level);
  showDiagnostics([]);
  const typing = level.mode === "both_editable" || level.mode === "code_first";
  $("edit-code").checked = typing;
  code.setEditable(typing);
  blocks.setPalette(level.unlockedBlocks);

  if (level.starter) {
    const parsed = await api.parse(level.starter);
    state.text = level.starter;
    state.sourceMap = parsed.positions;
    code.setText(level.starter);
    blocks.load(parsed.program, level.pack.actions, level.starter, parsed.positions);
  } else {
    code.setText("");
    blocks.load({ type: "Program", id: "program", body: [] }, level.pack.actions, "", {});
  }
  blocks.resize();
}

// --- running -----------------------------------------------------------------------

function invalidateRun() {
  stopPlayback();
  state.run = null;
  state.stepIndex = 0;
  $("result").replaceChildren();
  code.highlight(0);
  blocks.highlight(null);
}

function stopPlayback() {
  state.token += 1;
  state.playing = false;
  updateButtons();
}

function updateButtons() {
  $("run").textContent = state.playing ? "⏸ Pause" : "▶ Run";
  $("run").disabled = state.over && !state.playing;
  $("step").disabled = state.over;
}

async function ensureRun() {
  if (state.run) return state.run;
  stage.reset();
  const result = await api.run(state.level.id, state.text, state.player?.id);
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
  for (const event of step.events) await stage.play(event);
}

async function play({ single = false } = {}) {
  if (state.over) return players.showGoodbye();
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
  if (state.over) setTimeout(() => players.showGoodbye(), 1500); // let them see the result first
}

function showResult(run) {
  const parts = [];
  if (!run.check) {
    parts.push(el("div", { class: "message err" }, "Python can't read this program yet. Look under the code."));
  } else {
    const earned = run.check.stars.filter((s) => s.earned).length;
    const prefix = run.error && run.error.line ? `Line ${run.error.line}: ` : "";
    parts.push(
      el("div", { class: "stars", "aria-label": `${earned} of 3 stars` }, "★".repeat(earned) + "☆".repeat(3 - earned)),
      el("div", { class: `message ${run.check.solved ? "ok" : "err"}` }, prefix + run.check.message),
      el("ul", {}, ...run.check.stars.map((s) => el("li", {}, `${s.earned ? "✓" : "–"} ${s.label}`))),
    );
    if (run.output?.length) parts.push(el("pre", { class: "printed" }, run.output.join("\n")));
  }
  $("result").replaceChildren(...parts);
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
window.addEventListener("hashchange", () => {
  const id = location.hash.slice(1);
  if (id !== state.level?.id && state.levels.some((l) => l.id === id)) loadLevel(id);
});
$("grownups").addEventListener("click", () => players.openGrownups());

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
  stage.setSpeed(Number($("speed").value));
  state.levels = await api.levels();
  renderLevelOptions();
  const wanted = location.hash.slice(1);
  await loadLevel(state.levels.some((l) => l.id === wanted) ? wanted : state.levels[0].id);
  await players.start();
}

start().catch((error) => {
  $("result").replaceChildren(el("div", { class: "message err" }, `Could not start: ${error.message}`));
});
