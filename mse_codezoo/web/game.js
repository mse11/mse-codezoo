// Game mode (phase 8): the program writes the rules, then the child plays the game live.
// The engine keeps the running game between ticks (gamemode.py); this page sends the keys
// pressed since the last tick and draws what came back. Everything stays on the grid, so
// the page only slides pieces from square to square: emoji on the 2D board, or the zoo's
// low-poly models on the 3D stage (stage3d.js, loaded only when 3D is picked).

import { api } from "./api.js";
import "./look.js"; // the "Look and feel" settings apply here too
import { reducedMotion } from "./look.js";
import { fillLangSelect, initialLang, setLang, t, translatePage } from "./i18n.js";
import { EMOJI } from "./stage.js";

const $ = (id) => document.getElementById(id);
setLang(initialLang(), { save: false });

const CELL = 56;
const KEY_NAMES = { ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right", " ": "space" };
const CRITTERS = {
  guard: "🐊", ghost: "👻", bee: "🐝", snake: "🐍", robot: "🤖", cat: "🐈", dog: "🐕",
  spider: "🕷️", owl: "🦉", wolf: "🐺", frog: "🐸", bat: "🦇",
};
const TERRAIN = { "~": "water", t: "tree", "-": "thin-ice", o: "watched", "=": "bridge" };
const DRAFT_KEY = "codezoo.game-drafts";
const VIEW_KEY = "codezoo.game-view";

const state = {
  games: [],
  game: null, // the game as /api/games/<id> describes it
  session: null,
  playing: false,
  keys: [],
  timer: null,
  nodes: { critters: new Map() },
  view: "2d",
  stage3d: null, // the 3D stage, once 3D was picked
  last: null, // the last game state drawn, to redraw it after switching views
};

// --- 2D or 3D: 3D where WebGL works, unless this browser's player picked 2D -------------

function savedView() {
  try {
    return localStorage.getItem(VIEW_KEY);
  } catch {
    return null;
  }
}

async function setView(view, { save = false } = {}) {
  let next = view === "3d" ? "3d" : "2d";
  if (next === "3d" && !state.stage3d) {
    try {
      const { Stage3D, webglAvailable } = await import("./stage3d.js");
      if (webglAvailable()) state.stage3d = new Stage3D($("stage"));
      else next = "2d";
    } catch {
      next = "2d"; // no WebGL or three.js failed to load: the flat board always works
    }
  }
  if (next === "2d" && state.stage3d) state.stage3d.detach();
  state.view = next;
  $("view-2d").setAttribute("aria-pressed", String(next === "2d"));
  $("view-3d").setAttribute("aria-pressed", String(next === "3d"));
  $("view-3d").disabled = !state.stage3d && view === "3d" && next === "2d";
  if (save) {
    try {
      localStorage.setItem(VIEW_KEY, next);
    } catch {
      // storage blocked: asked again next time
    }
  }
  if (state.game) {
    drawBoard();
    if (state.last) drawState(state.last);
  }
}

// --- drafts: each game's code is kept in this browser while the child changes it -------

function drafts() {
  try {
    return JSON.parse(localStorage.getItem(DRAFT_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveDraft() {
  if (!state.game) return;
  try {
    const all = drafts();
    all[state.game.id] = $("source").value;
    localStorage.setItem(DRAFT_KEY, JSON.stringify(all));
  } catch {
    // storage blocked: the draft lives only on this page
  }
}

// --- drawing ---------------------------------------------------------------------------

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function place(node, [x, y]) {
  node.style.transform = `translate(${x * CELL}px, ${y * CELL}px)`;
}

// a piece that just appeared jumps to its square instead of sliding in from the corner
function placeNow(node, at) {
  node.style.transition = "none";
  place(node, at);
  void node.offsetWidth;
  node.style.transition = "";
}

function itemEmoji(tile) {
  const id = state.game.pack.items[tile];
  return EMOJI[id] || "⭐";
}

function critterEmoji(kind) {
  return CRITTERS[kind] || EMOJI[kind] || "🐾";
}

function drawBoard() {
  const stage = $("stage");
  if (state.view === "3d" && state.stage3d) {
    state.stage3d.loadGame(state.game);
    state.nodes = { critters: new Map() };
    return;
  }
  const world = state.game.world;
  const [width, height] = world.size;
  stage.replaceChildren();
  stage.classList.toggle("still", reducedMotion());
  const board = el("div", "board");
  board.style.width = `${width * CELL}px`;
  board.style.height = `${height * CELL}px`;
  const walls = new Set(world.walls.map(([x, y]) => `${x},${y}`));
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const cell = el("div", `cell${(x + y) % 2 ? " alt" : ""}${walls.has(`${x},${y}`) ? " wall" : ""}`);
      place(cell, [x, y]);
      board.append(cell);
    }
  }
  for (const [x, y, kind] of world.terrain) {
    const cell = el("div", `cell terrain ${TERRAIN[kind] || ""}`, kind === "t" ? "🌴" : "");
    place(cell, [x, y]);
    board.append(cell);
  }
  const items = el("div", "layer");
  const critters = el("div", "layer");
  const animal = el("div", "piece animal", EMOJI[state.game.pack.animal] || state.game.pack.emoji || "🐾");
  const bubble = el("div", "bubble");
  bubble.hidden = true;
  board.append(items, critters, animal, bubble);
  stage.append(board);
  state.nodes = { board, items, critters: new Map(), critterLayer: critters, animal, bubble };
  fitBoard();
}

// the board shrinks to fit a phone; the squares stay square
function fitBoard() {
  const { board } = state.nodes;
  if (state.view === "3d") return; // the 3D stage fits itself
  if (!board || !state.game) return;
  const [width] = state.game.world.size;
  const room = $("stage").clientWidth - 8;
  const scale = Math.min(1, room / (width * CELL));
  board.style.transform = `scale(${scale})`;
  board.style.marginBottom = `${(scale - 1) * board.offsetHeight}px`;
}

function drawState(game) {
  state.last = game;
  $("score").textContent = String(game.score);
  $("tick").textContent = String(game.tick);
  const status = $("status-text");
  status.textContent = game.status === "playing" || game.status === "ready" ? "" : game.message;
  status.dataset.status = game.status;
  if (state.view === "3d" && state.stage3d) {
    state.stage3d.showGame(game, state.game.tickMs);
    return;
  }
  const { items, critters, critterLayer, animal, bubble } = state.nodes;
  items.replaceChildren(
    ...game.items.map(([x, y, tile]) => {
      const node = el("div", "piece item", itemEmoji(tile));
      place(node, [x, y]);
      return node;
    }),
  );
  (animal.style.transform ? place : placeNow)(animal, game.animal.at);
  animal.dataset.facing = game.animal.facing;
  const seen = new Set();
  for (const critter of game.critters) {
    seen.add(critter.id);
    let node = critters.get(critter.id);
    if (!node) {
      node = el("div", "piece critter", critterEmoji(critter.kind));
      node.title = critter.kind;
      critterLayer.append(node);
      critters.set(critter.id, node);
      placeNow(node, critter.at);
    }
    place(node, critter.at);
    node.dataset.facing = critter.facing;
  }
  for (const [id, node] of critters) {
    if (!seen.has(id)) {
      node.remove();
      critters.delete(id);
    }
  }
  if (game.said) {
    bubble.textContent = game.said;
    bubble.hidden = false;
    place(bubble, game.animal.at);
  }
}

function flash(events) {
  const { animal, critters } = state.nodes;
  for (const event of events) {
    if (state.view === "3d" && state.stage3d) {
      if (event.type === "bump") state.stage3d.bumpGame("animal");
      if (event.type === "critter" && event.bump) state.stage3d.bumpGame(event.id);
      continue;
    }
    if (event.type === "bump") shake(animal);
    if (event.type === "critter" && event.bump) shake(critters.get(event.id));
  }
}

function shake(node) {
  if (!node || reducedMotion()) return;
  node.classList.remove("bumped");
  void node.offsetWidth; // restart the animation
  node.classList.add("bumped");
}

// --- the code pane ---------------------------------------------------------------------

function drawGutter(lit = [], wrong = null) {
  const count = $("source").value.split("\n").length;
  const gutter = $("gutter");
  const lines = [];
  for (let n = 1; n <= count; n += 1) {
    const line = el("div", lit.includes(n) ? "lit" : n === wrong ? "wrong" : "", String(n));
    lines.push(line);
  }
  gutter.replaceChildren(...lines);
  gutter.scrollTop = $("source").scrollTop;
}

function report(text, kind = "") {
  const box = $("report");
  box.textContent = text;
  box.dataset.kind = kind;
}

function showProblems(data) {
  const errors = (data.diagnostics || []).filter((d) => d.severity === "error");
  if (errors.length) {
    const first = errors[0];
    report(t("Line {line}: {message}", { line: first.line, message: first.message }), "err");
    drawGutter([], first.line);
    return true;
  }
  if (data.error) {
    const where = data.error.line ? t("Line {line}: {message}", { line: data.error.line, message: data.error.message }) : data.error.message;
    report(where, "err");
    drawGutter([], data.error.line);
    return true;
  }
  return false;
}

function addOutput(lines, notes) {
  const box = $("output");
  const more = [...(lines || []), ...(notes || []).map((note) => `💬 ${note}`)];
  if (!more.length) return;
  box.textContent = [...box.textContent.split("\n").filter(Boolean), ...more].slice(-30).join("\n");
  box.scrollTop = box.scrollHeight;
}

// --- playing ---------------------------------------------------------------------------

async function play() {
  await stop();
  saveDraft();
  report("");
  $("output").textContent = "";
  drawBoard();
  let data;
  try {
    data = await api.gameStart(state.game.id, $("source").value, $("animal-select").value);
  } catch (error) {
    report(error.message, "err");
    return;
  }
  state.session = data.session;
  drawState(data.state);
  addOutput(data.output, data.notes);
  if (showProblems(data) || data.state.status !== "playing") return;
  report(t("Playing! Use the arrow keys or the buttons."), "ok");
  drawGutter(data.lines);
  state.playing = true;
  state.keys = [];
  $("play").disabled = true;
  $("stop").disabled = false;
  $("stage").focus();
  loop();
}

// one tick at a time: the next waits for the last answer, so a slow tablet just plays slower
async function loop() {
  if (!state.playing) return;
  const started = performance.now();
  const keys = state.keys.splice(0, 4);
  let data;
  try {
    data = await api.gameTick(state.session, keys);
  } catch (error) {
    report(error.message, "err");
    finish();
    return;
  }
  if (!state.playing) return;
  drawState(data.state);
  flash(data.events);
  drawGutter(data.lines);
  addOutput(data.output, data.notes);
  if (data.state.status !== "playing") {
    if (!showProblems(data)) report(data.state.message, data.state.status === "won" ? "ok" : "");
    finish();
    return;
  }
  const wait = Math.max(0, state.game.tickMs - (performance.now() - started));
  state.timer = setTimeout(loop, wait);
}

function finish() {
  state.playing = false;
  clearTimeout(state.timer);
  $("play").disabled = false;
  $("stop").disabled = true;
}

async function stop() {
  const session = state.session;
  const was = state.playing;
  finish();
  state.session = null;
  if (session) {
    try {
      await api.gameStop(session);
    } catch {
      // the game is forgotten on the engine side anyway
    }
  }
  if (was) report(t("Stopped."));
}

function press(key) {
  if (!state.playing) return;
  if (state.keys.length < 8) state.keys.push(key);
}

// --- choosing a game -------------------------------------------------------------------

async function loadGame(id) {
  await stop();
  state.game = await api.game(id, $("animal-select").value);
  const draft = drafts()[id];
  $("source").value = draft ?? state.game.starter;
  $("help").replaceChildren(...state.game.help.map((line) => el("li", "", line)));
  report("");
  $("output").textContent = "";
  drawBoard();
  drawState({
    tick: 0, status: "ready", message: "", score: 0, said: "",
    animal: { at: state.game.world.position, facing: state.game.world.facing },
    items: state.game.world.items, critters: [],
  });
  drawGutter();
  const url = new URL(location.href);
  url.searchParams.set("game", id);
  history.replaceState(null, "", url);
}

function fillLangs() {
  const select = $("lang");
  fillLangSelect(select); // a drawn flag and "SK"
  select.addEventListener("change", async () => {
    setLang(select.value);
    translatePage();
    await start();
  });
}

async function start() {
  translatePage();
  const [games, animals] = await Promise.all([api.games(), api.animals()]);
  state.games = games;
  const gameSelect = $("game-select");
  const wanted = new URLSearchParams(location.search).get("game");
  const current = state.game?.id || (games.some((g) => g.id === wanted) ? wanted : games[0]?.id);
  gameSelect.replaceChildren(
    ...games.map((game) => {
      const option = el("option", "", game.title);
      option.value = game.id;
      return option;
    }),
  );
  const animalSelect = $("animal-select");
  const animal = animalSelect.value;
  animalSelect.replaceChildren(
    ...animals.map((pack) => {
      const option = el("option", "", `${EMOJI[pack.animal] || pack.emoji || ""} ${pack.animalName}`);
      option.value = pack.id;
      return option;
    }),
  );
  if (animal) animalSelect.value = animal;
  if (current) {
    gameSelect.value = current;
    await loadGame(current);
    if (!animal) animalSelect.value = state.game.animal;
  } else {
    report(t("There are no games yet."));
  }
}

function wire() {
  $("play").addEventListener("click", play);
  $("stop").addEventListener("click", stop);
  $("restart").addEventListener("click", () => {
    if (!state.game) return;
    $("source").value = state.game.starter;
    saveDraft();
    drawGutter();
  });
  $("view-2d").addEventListener("click", () => setView("2d", { save: true }));
  $("view-3d").addEventListener("click", () => setView("3d", { save: true }));
  $("game-select").addEventListener("change", (event) => loadGame(event.target.value));
  $("animal-select").addEventListener("change", () => state.game && loadGame(state.game.id));
  $("source").addEventListener("input", () => {
    saveDraft();
    drawGutter();
  });
  $("source").addEventListener("scroll", () => ($("gutter").scrollTop = $("source").scrollTop));
  document.addEventListener("keydown", (event) => {
    const key = KEY_NAMES[event.key];
    if (!key || !state.playing || event.target === $("source")) return;
    event.preventDefault();
    press(key);
  });
  for (const button of document.querySelectorAll(".pad button")) {
    button.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      press(button.dataset.key);
    });
  }
  window.addEventListener("resize", fitBoard);
  window.addEventListener("pagehide", () => state.session && api.gameStop(state.session).catch(() => {}));
}

fillLangs();
wire();
setView(savedView() || "3d")
  .then(start)
  .catch((error) => report(error.message, "err"));
