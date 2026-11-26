// Game mode (phase 8): the program writes the rules, then the child plays the game live.
// The engine keeps the running game between ticks (gamemode.py); this page sends the keys
// pressed since the last tick and draws what came back. Everything stays on the grid, so
// the page only slides pieces from square to square: emoji on the 2D board, or the zoo's
// low-poly models on the 3D stage (stage3d.js, loaded only when 3D is picked).
//
// G1: lesson rounds and twist cards, the design card, "Test my game" (the playtest bot).
// G2: the world editor (squares, the start, objects with a class from the code), share
//     links (game.html#play=...: the game travels inside the link) and class sharing.
// G3: "Play together" on a classroom hub: a room's game runs on the hub, every device
//     sends its keys and draws each tick pushed to it (server-sent events). Emoji only.
// Also: doors, switches and power-ups, "Which handler fired?" (one row per tick), and
// sounds made on the spot (fun.js), following the Sounds switch.

import { api } from "./api.js";
import { GAME_PALETTE, createWorkspace } from "./blocks.js";
import "./look.js"; // the "Look and feel" settings apply here too
import { reducedMotion, setupGraphicsSwitch } from "./look.js";
import { fillLangSelect, initialLang, setLang, t, translatePage } from "./i18n.js";
import { music, sfx, setupSoundButton } from "./fun.js";
import { decodeShare, encodeShare } from "./share.js";
import { colourTextarea, setCommandNames } from "./syntax.js";
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
const ROUNDS_KEY = "codezoo.game-rounds";
const DESIGN_KEY = "codezoo.game-designs";
const PLAYER_KEY = "codezoo.player"; // the player picked on the main page (players.js)
const ROOMS_POLL_MS = 4000;
const MAX_LANES = 30; // ticks kept in "Which handler fired?"
const MAX_TICK_SOUNDS = 3; // a busy tick still plays only a few sounds
const CHANGES = {
  animal: "🐾", score: "⭐", items: "🍌", critters: "🐊", world: "🧱", doors: "🚪",
  status: "🏁", printed: "💬", sounds: "🔔",
};
const THINGS = { door: "🚪", switch: "🔘", power: "💫" };

const state = {
  games: [],
  game: null, // the game as /api/games/<id> (or /api/game/preview) describes it
  custom: null, // a game from the world editor, a share link or the class: its whole file
  session: null,
  playing: false,
  keys: [],
  timer: null,
  nodes: { critters: new Map() },
  view: "2d",
  stage3d: null, // the 3D stage, once 3D was picked
  last: null, // the last game state drawn, to redraw it after switching views
  tilesKey: "", // the walls and terrain drawn, to redraw them when code builds
  features: null, // what the program had at its last start (for the rounds)
  editing: false,
  brush: ".",
  info: {},
  room: null, // {id, seat, number, events, status}
  roomsTimer: null,
  lanes: [], // [{tick, fired}], newest first
  combo: 0, // items grabbed in a row, so the grab sound climbs
};

const storage = {
  read(key) {
    try {
      return JSON.parse(localStorage.getItem(key) || "{}");
    } catch {
      return {};
    }
  },
  write(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // storage blocked: kept only on this page
    }
  },
};

// the key under which this game's draft, rounds and design card are kept
const gameKey = () => (state.custom ? `custom:${state.custom.id}` : state.game?.id);
const gameRef = () => (state.custom ? { gameData: state.custom } : state.game.id);
const playerId = () => {
  try {
    return localStorage.getItem(PLAYER_KEY);
  } catch {
    return null;
  }
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

function saveDraft() {
  if (!state.game) return;
  const all = storage.read(DRAFT_KEY);
  all[gameKey()] = $("source").value;
  storage.write(DRAFT_KEY, all);
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

function animalEmoji(look) {
  return EMOJI[look] || EMOJI[state.game.pack.animal] || state.game.pack.emoji || "🐾";
}

function readyState() {
  const world = state.game.world;
  return {
    tick: 0, status: "ready", message: "", score: 0, said: "",
    animal: { at: world.position, facing: world.facing },
    items: world.items, critters: [], walls: world.walls, terrain: world.terrain,
    ...thingsOf(world.objects || []),
  };
}

// doors, switches and power-ups as the world file has them, before the game starts
function thingsOf(objects) {
  const of = (type) => objects.filter((object) => object.type === type);
  return {
    doors: of("door").map(({ at, open }) => [...at, Boolean(open)]),
    switches: of("switch").map(({ at }) => [...at, false]),
    powers: of("power").map(({ at }) => [...at]),
  };
}

function drawBoard() {
  const stage = $("stage");
  state.tilesKey = "";
  if (state.view === "3d" && state.stage3d) {
    state.stage3d.loadGame(state.game);
    state.nodes = { critters: new Map() };
    state.tilesKey = JSON.stringify([state.game.world.walls, state.game.world.terrain]);
    return;
  }
  const [width, height] = state.game.world.size;
  stage.replaceChildren();
  stage.classList.toggle("still", reducedMotion());
  stage.classList.toggle("editing", state.editing);
  const board = el("div", "board");
  board.style.width = `${width * CELL}px`;
  board.style.height = `${height * CELL}px`;
  const cells = el("div", "layer");
  const objects = el("div", "layer");
  const things = el("div", "layer");
  const items = el("div", "layer");
  const critters = el("div", "layer");
  const animal = el("div", "piece animal", animalEmoji(""));
  const bubble = el("div", "bubble");
  bubble.hidden = true;
  board.append(cells, things, objects, items, critters, animal, bubble);
  stage.append(board);
  state.nodes = { board, cells, things, objects, items, critters: new Map(), critterLayer: critters, animal, bubble, others: new Map() };
  drawCells(state.game.world.walls, state.game.world.terrain);
  drawObjects();
  fitBoard();
}

// the squares: plain, stone, water, trees... drawn again when the code builds
function drawCells(walls, terrain) {
  const key = JSON.stringify([walls, terrain]);
  if (key === state.tilesKey) return;
  state.tilesKey = key;
  if (state.view === "3d" && state.stage3d) {
    if (state.last) state.stage3d.loadGame({ ...state.game, world: { ...state.game.world, walls, terrain, items: state.last.items } });
    return;
  }
  const { cells } = state.nodes;
  if (!cells) return;
  const [width, height] = state.game.world.size;
  const stone = new Set(walls.map(([x, y]) => `${x},${y}`));
  const nodes = [];
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const cell = el("div", `cell${(x + y) % 2 ? " alt" : ""}${stone.has(`${x},${y}`) ? " wall" : ""}`);
      cell.dataset.x = x;
      cell.dataset.y = y;
      place(cell, [x, y]);
      nodes.push(cell);
    }
  }
  for (const [x, y, kind] of terrain) {
    const cell = el("div", `cell terrain ${TERRAIN[kind] || ""}`, kind === "t" ? "🌴" : "");
    cell.dataset.x = x;
    cell.dataset.y = y;
    place(cell, [x, y]);
    nodes.push(cell);
  }
  cells.replaceChildren(...nodes);
}

// the world's objects, shown before the game starts (and while editing)
function drawObjects() {
  const { objects } = state.nodes;
  if (!objects) return;
  const show = !state.last || state.last.status === "ready" || state.editing;
  objects.replaceChildren(
    ...(show ? state.game.world.objects.filter((object) => !object.type) : []).map((object) => {
      const node = el("div", "piece object", critterEmoji(object.kind || object.class.toLowerCase()));
      node.title = object.class;
      place(node, object.at);
      return node;
    }),
  );
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
  state.nodes.scale = scale;
}

// the game music's pace: how close the nearest critter is to an animal (0 far .. 1 next to it)
function danger(game) {
  const animals = game.players?.length ? game.players.map((p) => p.at) : [game.animal?.at].filter(Boolean);
  let nearest = Infinity;
  for (const critter of game.critters || []) {
    for (const at of animals) nearest = Math.min(nearest, Math.abs(critter.at[0] - at[0]) + Math.abs(critter.at[1] - at[1]));
  }
  return nearest === Infinity ? 0 : Math.max(0, Math.min(1, 1 - (nearest - 1) / 5));
}

// 🎶: the game music on or off (it also follows 🎵, like every sound)
// a game opens with its starter; a bug hunt ("bug-…") opens with its broken program, the
// one its rounds start from (the starter is the fixed game, for the playtest bot)
function firstCode(game) {
  return game.id?.startsWith("bug-") && game.lesson ? game.lesson : game.starter;
}

// --- the blocks view of the game's code: the same program, kept in step by the engine ----
// (code -> /api/parse -> blocks; blocks -> /api/print -> code), with handler blocks
// ("when a key is pressed") for `def on_key(key):` and the game's own commands

const GAME_NAMES = { step: "step", turn_left: "turn_left", turn_right: "turn_right", grab: "grab", say: "say" };
let gameBlocks = null;
let blocksSequence = 0;

async function showBlocks(on) {
  $("blocks-msg").textContent = "";
  if (on) {
    const text = $("source").value;
    const parsed = await api.parse(text).catch(() => null);
    if (!parsed?.ok) {
      // code with a mistake stays code: blocks would lose what doesn't parse yet
      $("blocks-msg").textContent = t("Fix the code first, then the blocks can show it.");
      return;
    }
    $("game-blocks").hidden = false;
    document.querySelector(".game-code").hidden = true;
    gameBlocks ||= createWorkspace($("game-blocks"), () => blocksChanged(), { game: true });
    gameBlocks.setPalette(GAME_PALETTE);
    gameBlocks.load(parsed.program, GAME_NAMES, text, parsed.positions);
    gameBlocks.resize();
  } else {
    $("game-blocks").hidden = true;
    document.querySelector(".game-code").hidden = false;
  }
  $("view-code").setAttribute("aria-pressed", String(!on));
  $("view-blocks").setAttribute("aria-pressed", String(on));
}

async function blocksChanged() {
  const mine = ++blocksSequence;
  await new Promise((resolve) => setTimeout(resolve, 150));
  if (mine !== blocksSequence || !gameBlocks) return;
  try {
    const printed = await api.print(gameBlocks.toProgram(GAME_NAMES));
    if (mine !== blocksSequence) return;
    $("source").value = printed.text;
    $("source").dispatchEvent(new Event("input")); // saved as the draft, the gutter follows
  } catch (error) {
    $("blocks-msg").textContent = error.message;
  }
}

function setupMusicButton() {
  const button = $("music");
  if (!button) return;
  const show = () => {
    const on = music.on();
    button.setAttribute("aria-pressed", String(on));
    button.title = on ? t("Game music on") : t("Game music off");
    button.setAttribute("aria-label", button.title);
  };
  button.addEventListener("click", () => {
    music.set(!music.on());
    show();
  });
  show();
}

function drawState(game) {
  state.last = game;
  $("score").textContent = String(game.score);
  $("tick").textContent = String(game.tick);
  const status = $("status-text");
  status.textContent = game.status === "playing" || game.status === "ready" ? "" : game.message;
  status.dataset.status = game.status;
  drawCells(game.walls || state.game.world.walls, game.terrain || state.game.world.terrain);
  if (state.view === "3d" && state.stage3d) {
    state.stage3d.showGame(game, state.game.tickMs, state.room?.number || 0);
    return;
  }
  drawObjects();
  drawThings(game);
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
  drawPlayers(game.players || []);
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

// doors (open ones fade), switches (green when on) and power-ups on the flat board
function drawThings(game) {
  const { things } = state.nodes;
  if (!things) return;
  const piece = (at, emoji, className, label) => {
    const node = el("div", `piece thing ${className}`, emoji);
    node.title = label;
    place(node, at);
    return node;
  };
  things.replaceChildren(
    ...(game.doors || []).map(([x, y, open]) => piece([x, y], THINGS.door, open ? "door open" : "door", open ? t("an open door") : t("a closed door"))),
    ...(game.switches || []).map(([x, y, on]) => piece([x, y], on ? "🟢" : THINGS.switch, "switch", t("a switch"))),
    ...(game.powers || []).map(([x, y]) => piece([x, y], THINGS.power, "power", t("a power-up"))),
  );
  $("stage").classList.toggle("frozen", (game.frozen || 0) > 0);
}

// playing together: player 1 is the usual animal piece, the others get their own; each
// wears its number so children find their own animal
function drawPlayers(players) {
  const { animal, others, board } = state.nodes;
  if (!others) return;
  animal.dataset.number = players.length ? "1" : "";
  if (players[0]) animal.textContent = animalEmoji(players[0].look);
  const seen = new Set();
  for (const player of players.slice(1)) {
    seen.add(player.number);
    let node = others.get(player.number);
    if (!node) {
      node = el("div", "piece animal other", animalEmoji(player.look));
      node.dataset.number = String(player.number);
      board.append(node);
      others.set(player.number, node);
      placeNow(node, player.at);
    }
    place(node, player.at);
    node.dataset.facing = player.facing;
    node.classList.toggle("me", state.room?.number === player.number);
  }
  animal.classList.toggle("me", state.room?.number === 1);
  for (const [number, node] of others) {
    if (!seen.has(number)) {
      node.remove();
      others.delete(number);
    }
  }
}

function flash(events) {
  const { animal, critters } = state.nodes;
  for (const event of events) {
    if (state.view === "3d" && state.stage3d) {
      if (event.type === "bump" && !state.room) state.stage3d.bumpGame("animal");
      if (event.type === "critter" && event.bump) state.stage3d.bumpGame(event.id);
      continue;
    }
    if (event.type === "bump" && !state.room) shake(animal);
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

let colours = null; // Python colours under the code (syntax.js)

function drawGutter(lit = [], wrong = null) {
  colours ??= colourTextarea($("source"));
  if (state.game) setCommandNames(state.game.pack.actions); // the animal's own command names
  colours.render(); // the code may have been set without an input event
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

function addCode(code) {
  const source = $("source");
  const text = source.value.replace(/\s*$/, "");
  source.value = `${text}${text ? "\n\n\n" : ""}${code.replace(/\s*$/, "")}\n`;
  saveDraft();
  drawGutter();
}

// --- "Which handler fired?": one row per tick, a column per handler -----------------------

// the game program's variables after a tick, changed ones lit (the debugger on the game page)
let lastVars = {};
function showVars(vars) {
  if (!vars) return;
  const rows = Object.entries(vars).map(([name, value]) => {
    const row = el("tr", lastVars[name] !== undefined && lastVars[name] !== value ? "changed" : "");
    const head = el("th", "", name);
    head.scope = "row";
    row.append(head, el("td", "", value));
    return row;
  });
  const body = el("tbody");
  body.append(...rows);
  $("game-vars").replaceChildren(body);
  $("game-vars-none").hidden = rows.length > 0;
  lastVars = vars;
}

function addLane(tick, fired) {
  if (!fired?.length) return;
  state.lanes.unshift({ tick, fired });
  state.lanes.length = Math.min(state.lanes.length, MAX_LANES);
  if ($("lanes-box").open) drawLanes();
}

function changeText(changes) {
  return changes.map((change) => CHANGES[change] || "").join("");
}

function drawLanes() {
  const box = $("lanes");
  if (!state.lanes.length) {
    box.replaceChildren(el("p", "note", t("Press Play: every tick gets a row here.")));
    return;
  }
  const names = [];
  for (const { fired } of [...state.lanes].reverse()) {
    for (const entry of fired) if (!names.includes(entry.handler)) names.push(entry.handler);
  }
  const table = el("table", "lanes-table");
  const head = el("tr");
  head.append(el("th", "", t("Tick")), ...names.map((name) => el("th", "", name)));
  table.append(head);
  for (const { tick, fired } of state.lanes) {
    const row = el("tr");
    row.append(el("td", "lane-tick", String(tick)));
    for (const name of names) {
      const entry = fired.find((found) => found.handler === name);
      const cell = el("td", entry ? "lane-fired" : "");
      if (entry) {
        cell.textContent = `●${entry.times > 1 ? `×${entry.times}` : ""} ${changeText(entry.changes)}`;
        cell.title = t("{handler}: ran {times} times, {steps} steps", { handler: name, times: entry.times, steps: entry.steps });
      }
      row.append(cell);
    }
    table.append(row);
  }
  box.replaceChildren(table);
}

// --- sounds: the world's events, and the game's own sound("...") ------------------------------

function playSounds(events) {
  let played = 0;
  let bumped = false;
  let built = false;
  const play = (name, ...args) => {
    if (played >= MAX_TICK_SOUNDS || !sfx[name]) return;
    played += 1;
    sfx[name](...args);
  };
  for (const event of events || []) {
    if (event.type === "grab") {
      state.combo += 1;
      play("grab", state.combo);
    } else if (event.type === "bump" && !bumped && !state.room) {
      bumped = true;
      play("bump");
    } else if (event.type === "touch") play("boing");
    else if (event.type === "door") play("door", event.open);
    else if (event.type === "switch") play("click");
    else if (event.type === "power") play("power");
    else if (event.type === "tile" && !built) {
      built = true;
      play("build");
    } else if (event.type === "sound") play(event.name);
    else if (event.type === "win") play("win", false);
    else if (event.type === "lose") play("oops");
  }
}

// --- lesson rounds and twist cards (G1) ---------------------------------------------------

function roundsDone() {
  return new Set(storage.read(ROUNDS_KEY)[gameKey()] || []);
}

function picked() {
  return storage.read(ROUNDS_KEY)[`${gameKey()}:twist`] || null;
}

// a round's needs: names the program must have, and "!name" ones it must not (a bug hunt)
function has(needs) {
  const features = new Set(state.features || []);
  return needs.every((need) => (need.startsWith("!") ? !features.has(need.slice(1)) : features.has(need)));
}

// a round counts once the code has what it asks for; a round stays done after that
function checkRounds() {
  const rounds = state.game?.rounds || [];
  if (!rounds.length || !state.features) return;
  const all = storage.read(ROUNDS_KEY);
  const done = new Set(all[gameKey()] || []);
  const before = done.size;
  rounds.forEach((round, index) => {
    if (round.twist) {
      const card = state.game.twists.find((twist) => twist.id === picked());
      if (card && has(card.needs)) done.add(index);
    } else if (round.needs.length && has(round.needs)) {
      done.add(index);
    }
  });
  all[gameKey()] = [...done].sort((a, b) => a - b);
  storage.write(ROUNDS_KEY, all);
  if (done.size > before) addOutput([], [t("Round done! {done} of {count}.", { done: done.size, count: rounds.length })]);
  drawRounds();
}

function drawRounds() {
  const rounds = state.game?.rounds || [];
  $("rounds-box").hidden = !rounds.length;
  if (!rounds.length) return;
  const done = roundsDone();
  const next = rounds.findIndex((_round, index) => !done.has(index));
  $("rounds-count").textContent = t("{done} of {count}", { done: done.size, count: rounds.length });
  $("rounds").replaceChildren(
    ...rounds.map((round, index) => {
      const item = el("li", done.has(index) ? "done" : index === next ? "now" : "");
      const mark = el("span", "round-mark", done.has(index) ? "✅" : index === next ? "👉" : "⬜");
      mark.setAttribute("aria-hidden", "true");
      item.append(mark, el("strong", "", round.title));
      if (index === next || !done.has(index)) item.append(el("span", "round-goal", ` ${round.goal}`));
      if (index === next && round.hint) {
        const show = el("button", "small", t("Show me how"));
        show.type = "button";
        const code = el("pre", "round-hint", round.hint);
        code.hidden = true;
        const add = el("button", "small", t("Add it to my code"));
        add.type = "button";
        add.hidden = true;
        show.addEventListener("click", () => {
          code.hidden = !code.hidden;
          add.hidden = code.hidden;
        });
        add.addEventListener("click", () => addCode(round.hint));
        item.append(" ", show, code, add);
      }
      return item;
    }),
  );
  drawTwists(next >= 0 && rounds[next].twist);
}

function drawTwists(show) {
  const box = $("twists");
  box.hidden = !show;
  if (!show) return;
  const chosen = picked();
  box.replaceChildren(
    ...state.game.twists.map((card) => {
      const button = el("button", `twist${card.id === chosen ? " picked" : ""}`);
      button.type = "button";
      button.setAttribute("aria-pressed", String(card.id === chosen));
      button.append(el("span", "twist-emoji", card.emoji), el("strong", "", card.title), el("span", "", card.text));
      button.addEventListener("click", () => {
        const all = storage.read(ROUNDS_KEY);
        all[`${gameKey()}:twist`] = card.id;
        storage.write(ROUNDS_KEY, all);
        drawRounds();
      });
      const wrap = el("div", "twist-card");
      wrap.append(button);
      if (card.id === chosen) {
        wrap.append(el("pre", "round-hint", card.code));
        wrap.append(el("p", "note", t("Fit it into your code, then press Play.")));
      }
      return wrap;
    }),
  );
}

// --- the design card ---------------------------------------------------------------------

const DESIGN_FIELDS = { idea: "design-idea", win: "design-win", lose: "design-lose" };

function design() {
  return Object.fromEntries(Object.entries(DESIGN_FIELDS).map(([key, id]) => [key, $(id).value.trim()]));
}

function loadDesign(given) {
  const saved = given || storage.read(DESIGN_KEY)[gameKey()] || {};
  for (const [key, id] of Object.entries(DESIGN_FIELDS)) $(id).value = saved[key] || "";
  $("design-box").open = Object.values(saved).some(Boolean);
}

function saveDesign() {
  const all = storage.read(DESIGN_KEY);
  all[gameKey()] = design();
  storage.write(DESIGN_KEY, all);
}

// --- playing ---------------------------------------------------------------------------

async function play() {
  if (state.room) return;
  await stop();
  saveDraft();
  if (state.editing) await setEditing(false);
  report("");
  $("output").textContent = "";
  state.lanes = [];
  state.combo = 0;
  drawLanes();
  drawBoard();
  let data;
  try {
    data = await api.gameStart(gameRef(), $("source").value, $("animal-select").value);
  } catch (error) {
    report(error.message, "err");
    return;
  }
  state.session = data.session;
  state.features = data.features;
  drawState(data.state);
  playSounds(data.events);
  addOutput(data.output, data.notes);
  checkRounds();
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
  playSounds(data.events);
  addLane(data.state.tick, data.fired);
  showVars(data.vars);
  if (data.state.status === "playing") music.beat(data.state.tick, danger(data.state));
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
  $("play").disabled = Boolean(state.room);
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
  if (state.room?.status === "playing") {
    api.room("keys", { room: state.room.id, seat: state.room.seat, keys: [key] }).catch(() => {});
    return;
  }
  if (!state.playing) return;
  if (state.keys.length < 8) state.keys.push(key);
}

// --- "Test my game" (G1): bot animals play it on the simulated clock -------------------

async function testGame() {
  await stop();
  saveDraft();
  const box = $("test-report");
  box.replaceChildren(el("p", "note", t("The bots are playing your game…")));
  $("test").disabled = true;
  let data;
  try {
    // the offline build plays in this browser: fewer games, so a tablet answers quickly
    const games = window.CODEZOO_OFFLINE ? 30 : 60;
    data = await api.gameTest(gameRef(), $("source").value, $("animal-select").value, games);
  } catch (error) {
    box.replaceChildren(el("p", "error", error.message));
    return;
  } finally {
    $("test").disabled = false;
  }
  const summary = el(
    "p",
    "test-summary",
    t("{played} games: {won} won, {lost} lost, {playing} still going after {ticks} ticks, {broken} broke.", data),
  );
  box.replaceChildren(
    summary,
    ...data.messages.map((message) => el("p", `test-${message.kind}`, `${message.kind === "ok" ? "🙂" : message.kind === "warn" ? "🤔" : "🛠️"} ${message.text}`)),
  );
  if (data.error?.line) drawGutter([], data.error.line);
}

// --- the world editor (G2) ------------------------------------------------------------------

// the game's own file, to edit: a bundled game becomes the child's own copy
function editableSpec() {
  const spec = structuredClone(state.custom || state.game.spec);
  if (!state.custom) {
    spec.id = `my-${spec.id}`.slice(0, 60);
    spec.title = Object.fromEntries(Object.entries(spec.title).map(([lang, title]) => [lang, `${title} ✏️`]));
  }
  spec.world.tiles = [...(Array.isArray(spec.world.tiles) ? spec.world.tiles : spec.world.tiles.split("\n"))];
  spec.world.objects = [...(spec.world.objects || [])];
  return spec;
}

async function setEditing(on) {
  if (on) await stop();
  state.editing = on;
  $("world-tools").hidden = !on;
  $("edit-world").setAttribute("aria-pressed", String(on));
  $("world-msg").textContent = on ? t("Pick something, then tap squares on the board.") : "";
  if (on) $("brush-item").textContent = itemEmoji("B");
  // the world is edited in the view the child is using (2D board or 3D stage)
  await setView(savedView() || state.view || "3d");
  if (state.game) {
    state.last = null;
    drawBoard();
    drawState(readyState());
  }
}

async function editSquare(x, y) {
  const spec = editableSpec();
  const rows = spec.world.tiles;
  const objects = spec.world.objects;
  const here = objects.findIndex((object) => object.at[0] === x && object.at[1] === y);
  if (state.brush === "start") {
    spec.world.start = [x, y, spec.world.start[2]];
    if (here >= 0) objects.splice(here, 1);
  } else if (THINGS[state.brush]) {
    const same = here >= 0 && objects[here].type === state.brush;
    if (here >= 0) objects.splice(here, 1);
    if (!same) {
      objects.push({ at: [x, y], type: state.brush });
      rows[y] = `${rows[y].slice(0, x)}.${rows[y].slice(x + 1)}`;
    }
  } else if (state.brush === "object") {
    if (here >= 0) objects.splice(here, 1);
    else {
      const name = $("object-class").value.trim() || "Guard";
      objects.push({ at: [x, y], class: name, facing: "east", kind: name.toLowerCase().slice(0, 20) });
      rows[y] = `${rows[y].slice(0, x)}.${rows[y].slice(x + 1)}`;
    }
  } else {
    rows[y] = `${rows[y].slice(0, x)}${state.brush}${rows[y].slice(x + 1)}`;
    if (here >= 0 && state.brush !== ".") objects.splice(here, 1);
  }
  await useSpec(spec);
}

async function resize(dx, dy) {
  const spec = editableSpec();
  let rows = spec.world.tiles;
  const width = rows[0].length + dx;
  const height = rows.length + dy;
  if (width < 3 || height < 2 || width > 16 || height > 12) return;
  rows = rows.slice(0, height).map((row) => (dx > 0 ? `${row}.` : row.slice(0, width)));
  while (rows.length < height) rows.push(".".repeat(width));
  spec.world.tiles = rows;
  spec.world.objects = spec.world.objects.filter(({ at: [x, y] }) => x < width && y < height);
  const [sx, sy, facing] = spec.world.start;
  spec.world.start = [Math.min(sx, width - 1), Math.min(sy, height - 1), facing];
  await useSpec(spec);
}

// a changed game is checked by the engine before it is drawn; a bad change is undone
async function useSpec(spec) {
  try {
    const game = await api.gamePreview(spec, $("animal-select").value);
    const first = !state.custom;
    state.custom = spec;
    state.game = game;
    $("world-msg").textContent = "";
    if (first) {
      saveDraft(); // the child's code comes along to the copy
      const option = el("option", "", game.title);
      option.value = "";
      $("game-select").append(option);
      $("game-select").value = "";
    }
    state.last = null;
    drawBoard();
    drawState(readyState());
  } catch (error) {
    $("world-msg").textContent = error.message;
  }
}

function boardClick(event) {
  if (!state.editing) return;
  // the 3D stage: the square under the tap, found by the stage itself
  if (state.view === "3d" && state.stage3d) {
    const square = state.stage3d.squareAt(event);
    if (square) editSquare(...square);
    return;
  }
  if (!state.nodes.board) return;
  const box = state.nodes.board.getBoundingClientRect();
  const scale = state.nodes.scale || 1;
  const x = Math.floor((event.clientX - box.left) / (CELL * scale));
  const y = Math.floor((event.clientY - box.top) / (CELL * scale));
  const [width, height] = state.game.world.size;
  if (x >= 0 && y >= 0 && x < width && y < height) editSquare(x, y);
}

// --- sharing (G2): a link that carries the game, or the class with the teacher's yes ----

function sharePayload() {
  return { game: state.custom || state.game.spec, source: $("source").value, design: design() };
}

async function shareLink() {
  const message = $("share-msg");
  let link;
  try {
    const url = new URL(location.href);
    url.search = "";
    url.hash = `play=${encodeShare(sharePayload())}`;
    link = url.toString();
  } catch (error) {
    message.textContent = error.message;
    return;
  }
  try {
    await navigator.clipboard.writeText(link);
    message.textContent = t("The link is copied. Whoever opens it gets your game and your code.");
  } catch {
    message.replaceChildren(t("Copy this link:"), " ", Object.assign(el("input", "share-input"), { value: link, readOnly: true }));
  }
}

async function shareWithClass() {
  const message = $("share-msg");
  const player = playerId();
  if (!player) {
    message.textContent = t("Pick your picture in the game first, then share.");
    return;
  }
  saveDraft();
  saveDesign();
  try {
    await api.share(player, "game", state.game.title, sharePayload());
    message.textContent = t("Sent! The teacher looks at it before the class can play it.");
  } catch (error) {
    message.textContent = error.message;
  }
}

async function drawClassGames() {
  if (!state.info.hub) return;
  let shares = [];
  try {
    ({ shares } = await api.classShares());
  } catch {
    return;
  }
  const games = shares.filter((share) => share.kind === "game");
  const key = games.map((share) => share.id).join();
  if (key === state.classGamesKey && $("class-games-list").childElementCount) return;
  state.classGamesKey = key;
  $("class-games").hidden = false;
  $("class-games-list").replaceChildren(
    ...(games.length
      ? games.map((share) => {
          const play = el("button", "small primary", t("▶ Try it"));
          play.type = "button";
          play.addEventListener("click", () => openShared(share.payload));
          const card = el("div", "share-card");
          const text = el("div", "share-text");
          text.append(el("strong", "", share.title), el("span", "note", share.name));
          if (share.payload.design?.idea) text.append(el("span", "note", `“${share.payload.design.idea}”`));
          card.append(text, play);
          return card;
        })
      : [el("p", "note", t("No games shared yet. Make one and press “Share with the class”."))]),
  );
}

// a game from a link or a classmate: its own copy, with its code and design card
async function openShared(payload) {
  await stop();
  await leaveRoom();
  const spec = payload.game;
  try {
    state.game = await api.gamePreview(spec, $("animal-select").value || spec.animal);
  } catch (error) {
    report(error.message, "err");
    return;
  }
  state.custom = spec;
  const option = el("option", "", state.game.title);
  option.value = "";
  $("game-select").querySelector('option[value=""]')?.remove();
  $("game-select").append(option);
  $("game-select").value = "";
  $("source").value = storage.read(DRAFT_KEY)[gameKey()] ?? payload.source ?? spec.starter ?? "";
  showGame(payload.design);
}

// --- playing together (G3) -------------------------------------------------------------------

async function drawRooms() {
  if (!state.info.hub || state.room) return;
  let data;
  try {
    data = await api.rooms();
  } catch {
    return;
  }
  $("together").hidden = false;
  drawReactions(data.reactions);
  $("room-list").replaceChildren(
    ...data.rooms.map((room) => {
      const item = el("li", "room");
      const who = room.players.map((p) => p.name).join(", ");
      item.append(el("strong", "", room.title), el("span", "note", ` ${room.players.length}/${room.max} · ${who}`));
      // a world can be joined until it is full, also while its game runs
      if (room.joinable ?? (room.status === "lobby" && room.players.length < room.max)) {
        const join = el("button", "small primary", t("Join"));
        join.type = "button";
        join.addEventListener("click", () => joinRoom(room.id));
        item.append(" ", join);
      } else {
        item.append(el("span", "note", ` · ${t("playing")}`));
      }
      return item;
    }),
  );
}

function drawReactions(reactions) {
  const box = $("reactions");
  if (box.childElementCount) return;
  box.replaceChildren(
    ...reactions.map((emoji) => {
      const button = el("button", "small reaction", emoji);
      button.type = "button";
      button.addEventListener("click", () => state.room && api.room("react", { room: state.room.id, seat: state.room.seat, emoji }).catch(() => {}));
      return button;
    }),
  );
}

async function openRoom() {
  await stop();
  saveDraft();
  const ref = gameRef();
  try {
    const data = await api.room("open", {
      ...(typeof ref === "string" ? { game: ref } : ref),
      source: $("source").value,
      profile: playerId(),
      look: $("animal-select").value,
    });
    enterRoom(data);
  } catch (error) {
    $("room-msg").textContent = error.message;
  }
}

async function joinRoom(id) {
  await stop();
  try {
    enterRoom(await api.room("join", { room: id, profile: playerId(), look: $("animal-select").value }));
  } catch (error) {
    $("room-msg").textContent = error.message;
  }
}

function enterRoom(data) {
  // the room's world is drawn while in it; the child's own game comes back on leaving
  state.room = {
    id: data.room.id, seat: data.seat, number: data.number, status: data.room.status, events: null,
    back: { game: state.game, custom: state.custom },
  };
  state.game = data.game;
  state.last = null;
  $("room-msg").textContent = "";
  $("room-lobby").hidden = true;
  $("room-here").hidden = false;
  $("reactions").hidden = false;
  $("play").disabled = true;
  drawRoom(data.room);
  setView(savedView() || "3d").then(() => drawState(readyState()));
  const events = api.roomEvents(data.room.id);
  state.room.events = events;
  events.onmessage = (event) => roomMessage(JSON.parse(event.data));
}

function drawRoom(room) {
  if (!state.room) return;
  state.room.status = room.status;
  $("room-title").textContent = room.title;
  $("room-status").textContent = room.status === "lobby" ? t("waiting for players") : room.status === "playing" ? t("playing") : t("the end");
  $("room-players").replaceChildren(
    ...room.players.map((player) => el("li", player.number === state.room.number ? "me" : "", `${player.number}. ${EMOJI[player.look] || "🐾"} ${player.name}`)),
  );
  $("room-start").hidden = !(state.room.number === 1 && room.status === "lobby");
}

async function roomMessage(message) {
  if (!state.room) return;
  if (message.type === "room") drawRoom(message.room);
  if (message.type === "react") floatEmoji(message.emoji, message.player);
  if (message.type === "start" || message.type === "tick") {
    if (message.type === "start") {
      $("output").textContent = "";
      state.lanes = [];
      state.combo = 0;
      report(t("Playing together! Use the arrow keys or the buttons."), "ok");
      $("stage").focus();
    }
    if (!state.nodes.board || message.type === "start") drawBoard();
    drawState(message.state);
    flash(message.events || []);
    playSounds(message.events);
    addLane(message.state.tick, message.fired);
    showVars(message.vars);
    if (message.state.status === "playing") music.beat(message.state.tick, danger(message.state));
    addOutput(message.output, message.notes);
    if (message.error) showProblems(message);
  }
  if (message.type === "end") {
    drawRoom(message.room);
    report(message.message || t("The game is over."), "");
    state.room.events?.close();
  }
}

function floatEmoji(emoji, player) {
  const bubble = el("div", "float-emoji", emoji);
  bubble.setAttribute("aria-hidden", "true");
  bubble.style.left = `${10 + ((player * 23) % 80)}%`;
  $("stage").append(bubble);
  setTimeout(() => bubble.remove(), reducedMotion() ? 900 : 1800);
}

async function leaveRoom() {
  const room = state.room;
  if (!room) return;
  room.events?.close();
  state.room = null;
  state.game = room.back.game;
  state.custom = room.back.custom;
  state.last = null;
  try {
    await api.room("leave", { room: room.id, seat: room.seat });
  } catch {
    // the room may have closed already
  }
  $("room-lobby").hidden = false;
  $("room-here").hidden = true;
  $("reactions").hidden = true;
  $("play").disabled = false;
  await setView(savedView() || "3d");
  drawState(readyState());
  report("");
  drawRooms();
}

async function startRoom() {
  try {
    await api.room("start", { room: state.room.id, seat: state.room.seat });
  } catch (error) {
    $("room-msg").textContent = error.message;
  }
}

// --- choosing a game -------------------------------------------------------------------

function showGame(givenDesign) {
  $("help").replaceChildren(...state.game.help.map((line) => el("li", "", line)));
  report("");
  $("output").textContent = "";
  $("test-report").replaceChildren();
  $("share-msg").textContent = "";
  state.features = null;
  state.last = null;
  drawBoard();
  drawState(readyState());
  drawGutter();
  drawRounds();
  loadDesign(givenDesign);
}

async function loadGame(id) {
  await stop();
  if (state.editing) await setEditing(false);
  state.custom = null;
  $("game-select").querySelector('option[value=""]')?.remove();
  state.game = await api.game(id, $("animal-select").value);
  const draft = storage.read(DRAFT_KEY)[id];
  $("source").value = draft ?? firstCode(state.game);
  showGame();
  const url = new URL(location.href);
  url.searchParams.set("game", id);
  url.hash = "";
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
  const [games, animals, info] = await Promise.all([api.games(), api.animals(), api.info().catch(() => ({}))]);
  state.games = games;
  state.info = info;
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
  $("share-class").hidden = !info.hub;
  const shared = location.hash.startsWith("#play=") ? location.hash.slice(6) : null;
  if (shared && !state.custom) {
    try {
      const payload = decodeShare(shared);
      if (!animal) animalSelect.value = payload.game.animal;
      await openShared(payload);
    } catch {
      report(t("This link is broken. Ask for a new one."), "err");
    }
  } else if (state.custom) {
    await openShared({ game: state.custom, source: $("source").value, design: design() });
  } else if (current) {
    gameSelect.value = current;
    // a game starts with its own animal until the child picks another
    if (!animal) animalSelect.value = games.find((game) => game.id === current)?.animal || animalSelect.value;
    await loadGame(current);
  } else {
    report(t("There are no games yet."));
  }
  if (info.hub) {
    drawRooms();
    drawClassGames();
    clearInterval(state.roomsTimer);
    state.roomsTimer = setInterval(() => {
      drawRooms();
      drawClassGames();
    }, ROOMS_POLL_MS);
  }
}

function wire() {
  setupSoundButton($("sounds"));
  setupGraphicsSwitch($("detail-switch"));
  setupMusicButton();
  $("lanes-box").addEventListener("toggle", () => $("lanes-box").open && drawLanes());
  $("play").addEventListener("click", play);
  $("stop").addEventListener("click", stop);
  $("restart").addEventListener("click", () => {
    if (!state.game) return;
    $("source").value = firstCode(state.game);
    saveDraft();
    drawGutter();
  });
  $("rounds-begin").addEventListener("click", () => {
    if (!state.game) return;
    if ($("source").value.trim() && !window.confirm(t("Start again from a nearly empty game? Your code is replaced."))) return;
    $("source").value = state.game.lesson || "";
    saveDraft();
    drawGutter();
  });
  $("view-2d").addEventListener("click", () => setView("2d", { save: true }));
  $("view-3d").addEventListener("click", () => setView("3d", { save: true }));
  $("game-select").addEventListener("change", (event) => {
    const game = state.games.find((found) => found.id === event.target.value);
    if (!game) return;
    $("animal-select").value = game.animal;
    loadGame(game.id);
  });
  $("animal-select").addEventListener("change", async () => {
    if (!state.game) return;
    if (state.custom) await openShared({ game: state.custom, source: $("source").value, design: design() });
    else await loadGame(state.game.id);
  });
  $("source").addEventListener("input", () => {
    saveDraft();
    drawGutter();
  });
  $("source").addEventListener("scroll", () => ($("gutter").scrollTop = $("source").scrollTop));
  $("view-code").addEventListener("click", () => showBlocks(false));
  $("view-blocks").addEventListener("click", () => showBlocks(true));
  for (const id of Object.values(DESIGN_FIELDS)) $(id).addEventListener("input", saveDesign);
  $("test").addEventListener("click", testGame);
  $("edit-world").addEventListener("click", () => setEditing(!state.editing));
  $("world-done").addEventListener("click", () => setEditing(false));
  for (const button of document.querySelectorAll("[data-brush]")) {
    button.addEventListener("click", () => {
      state.brush = button.dataset.brush;
      for (const other of document.querySelectorAll("[data-brush]")) other.setAttribute("aria-pressed", String(other === button));
    });
  }
  $("grow-x").addEventListener("click", () => resize(1, 0));
  $("shrink-x").addEventListener("click", () => resize(-1, 0));
  $("grow-y").addEventListener("click", () => resize(0, 1));
  $("shrink-y").addEventListener("click", () => resize(0, -1));
  $("stage").addEventListener("click", boardClick);
  $("share-link").addEventListener("click", shareLink);
  $("share-class").addEventListener("click", shareWithClass);
  $("room-open").addEventListener("click", openRoom);
  $("room-start").addEventListener("click", startRoom);
  $("room-leave").addEventListener("click", leaveRoom);
  document.addEventListener("keydown", (event) => {
    const key = KEY_NAMES[event.key];
    const typing = event.target instanceof HTMLInputElement || event.target === $("source");
    if (!key || typing || !(state.playing || state.room?.status === "playing")) return;
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
  window.addEventListener("hashchange", () => {
    if (location.hash.startsWith("#play=")) {
      state.custom = null;
      start();
    }
  });
  window.addEventListener("pagehide", () => {
    if (state.session) api.gameStop(state.session).catch(() => {});
    if (state.room) api.room("leave", { room: state.room.id, seat: state.room.seat }).catch(() => {});
  });
}

fillLangs();
wire();
setView(savedView() || "3d")
  .then(start)
  .catch((error) => report(error.message, "err"));
