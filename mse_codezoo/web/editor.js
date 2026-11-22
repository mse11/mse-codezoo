// Level editor: paint one or more worlds, write a reference solution, let the engine test
// it exactly like `codezoo levels validate`, then play it, share it as a link, keep it in
// this browser, or download the level JSON and solution for mse_codezoo/content/levels/.
// Shared levels only ever run in the zoo's own interpreter, like every other level.

import { api } from "./api.js";
import "./look.js"; // the "Look and feel" settings apply here too
import { initialLang, setLang, t, translatePage } from "./i18n.js";
import { EMOJI } from "./stage.js";
import { encodeShare } from "./share.js";

const $ = (id) => document.getElementById(id);
setLang(initialLang(), { save: false });

const TERRAIN = [
  ["~", "💧", "water"],
  ["t", "🌴", "tree"],
  ["-", "🧊", "thin-ice"],
  ["o", "👁️", "watched"],
];
const MODULES = [
  "sequences", "loops-1", "variables", "text", "conditions", "loops-2", "functions", "errors",
  "collections", "recursion", "comprehensions-and-generators", "objects", "decorators",
  "concurrency", "first-project",
];
const RELEASES = ["", "3.12", "3.13", "3.14", "3.15"];
const BLOCKS = [
  "step", "turn_left", "turn_right", "grab", "say", "for_range", "while", "if", "if_else",
  "compare", "logic", "not", "is_blocked", "item_here", "item_ahead", "text", "number", "set",
  "change", "var", "math", "break", "continue", "def", "call", "return", "try", "raise",
  "for_each", "list", "append", "len", "index", "yield", "class", "async_def", "await",
];
const ARROW = { east: "▶", south: "▼", west: "◀", north: "▲" };
const LIBRARY_KEY = "codezoo.my-levels";

function blankWorld(width = 6, height = 3) {
  return {
    cells: Array.from({ length: height }, () => Array.from({ length: width }, () => ".")),
    up: {}, // "x,y" -> item letter sitting on terrain (a coconut up a tree)
    start: [0, 0],
    facing: "east",
    flag: null,
    inputs: "",
    data: "",
    noGil: false,
  };
}

const state = { animals: [], tool: "#", worlds: [blankWorld()], current: 0 };
const world = () => state.worlds[state.current];
const pack = () => state.animals.find((a) => a.id === $("animal").value) || state.animals[0];

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  node.append(...children);
  return node;
}

// --- worlds -----------------------------------------------------------------------------

function resize() {
  const width = Math.max(1, Math.min(16, Number($("width").value) || 1));
  const height = Math.max(1, Math.min(12, Number($("height").value) || 1));
  for (const w of state.worlds) {
    w.cells = Array.from({ length: height }, (_, y) => Array.from({ length: width }, (_, x) => w.cells[y]?.[x] ?? "."));
    w.start = [Math.min(w.start[0], width - 1), Math.min(w.start[1], height - 1)];
    if (w.flag && (w.flag[0] >= width || w.flag[1] >= height)) w.flag = null;
  }
  render();
}

function showWorld(index) {
  state.current = index;
  const w = world();
  $("facing").value = w.facing;
  $("inputs").value = w.inputs;
  $("data").value = w.data;
  $("no-gil").checked = w.noGil;
  render();
}

function renderTabs() {
  $("world-tabs").replaceChildren(
    ...state.worlds.map((_, i) => {
      const button = el("button", { type: "button", class: "small", "aria-pressed": String(i === state.current) }, `${t("World")} ${i + 1}`);
      button.addEventListener("click", () => showWorld(i));
      return button;
    }),
  );
  $("remove-world").disabled = state.worlds.length < 2;
}

function tools() {
  const items = Object.entries(pack()?.items || {});
  const list = [
    [".", "⬜", t("ground")],
    ["#", "🪨", t("rock")],
    ...items.map(([tile, id]) => [tile, EMOJI[id] || tile, id]),
    ...TERRAIN.map(([tile, mark, name]) => [tile, mark, t(name.replace("-", " "))]),
    ["start", "🐾", t("start")],
    ["flag", "🏁", t("flag")],
  ];
  $("tools").replaceChildren(
    ...list.map(([tool, mark, label]) => {
      const button = el("button", { type: "button", role: "radio", "aria-checked": String(tool === state.tool), title: label, "aria-label": label }, mark);
      button.addEventListener("click", () => {
        state.tool = tool;
        tools();
      });
      return button;
    }),
  );
  const options = items.map(([tile, id]) => el("option", { value: tile }, `${EMOJI[id] || ""} ${id}`));
  $("goal-item").replaceChildren(...options);
  $("goal-avoid").replaceChildren(el("option", { value: "" }, "—"), ...options.map((o) => o.cloneNode(true)));
}

function paint(x, y) {
  const w = world();
  const tool = state.tool;
  if (tool === "start") w.start = [x, y];
  else if (tool === "flag") w.flag = [x, y];
  else if (/^[A-Z]$/.test(tool) && w.cells[y][x] === "t") w.up[`${x},${y}`] = tool;
  else {
    w.cells[y][x] = tool;
    delete w.up[`${x},${y}`];
  }
  render();
}

function render() {
  const w = world();
  const grid = $("grid");
  const width = w.cells[0].length;
  grid.style.gridTemplateColumns = `repeat(${width}, minmax(24px, 56px))`;
  const terrainClass = Object.fromEntries(TERRAIN.map(([tile, , name]) => [tile, name]));
  const items = pack()?.items || {};
  const cells = [];
  w.cells.forEach((row, y) =>
    row.forEach((tile, x) => {
      const classes = ["cell", (x + y) % 2 ? "alt" : "", tile === "#" ? "wall" : terrainClass[tile] || ""];
      let mark = tile === "#" ? "🪨" : items[tile] ? EMOJI[items[tile]] || tile : TERRAIN.find((e) => e[0] === tile)?.[1] || "";
      if (w.up[`${x},${y}`]) mark += EMOJI[items[w.up[`${x},${y}`]]] || "";
      if (w.flag && w.flag[0] === x && w.flag[1] === y) mark += "🏁";
      if (w.start[0] === x && w.start[1] === y) mark = `${pack()?.emoji || "🐾"}${ARROW[w.facing]}`;
      cells.push(el("div", { class: classes.join(" "), "data-x": x, "data-y": y }, mark));
    }),
  );
  grid.replaceChildren(...cells);
  renderTabs();
  $("json").textContent = JSON.stringify(levelData(), null, 2);
}

// --- the level as JSON -------------------------------------------------------------------

function countLines(text) {
  return text.split("\n").filter((line) => line.trim() && !line.trim().startsWith("#")).length;
}

const lines = (text) => text.split("\n").map((s) => s.trim()).filter(Boolean);

// "scores.txt\n---\nBea 5" (more files: repeat) -> {"scores.txt": "Bea 5\n"}
function parseFiles(text) {
  const files = {};
  const parts = text.split(/^---$/m);
  for (let i = 0; i + 1 < parts.length; i += 2) {
    const name = parts[i].trim().split("\n").pop()?.trim();
    if (name) files[name] = parts[i + 1].replace(/^\n/, "");
  }
  return files;
}

function formatFiles(files) {
  return Object.entries(files || {}).map(([name, text]) => `${name}\n---\n${text}`).join("\n---\n");
}

function worldSpec(w) {
  const spec = { tiles: w.cells.map((row) => row.join("")), start: [...w.start, w.facing] };
  const up = Object.entries(w.up).map(([key, tile]) => [...key.split(",").map(Number), tile]);
  if (up.length) spec.items = up;
  if (w.inputs.trim()) spec.inputs = w.inputs.split("\n").filter((line, i, all) => line || i < all.length - 1);
  const files = parseFiles(w.data);
  if (Object.keys(files).length) spec.data = files;
  if (w.noGil) spec.gil = false;
  return spec;
}

function goalFor(w) {
  const type = $("goal-type").value;
  let goal;
  if (type === "reach") goal = { type, at: w.flag || [w.cells[0].length - 1, w.cells.length - 1] };
  else if (type === "say" || type === "print") goal = { type, text: $("goal-text").value };
  else if (type === "file") goal = { type, name: $("goal-file").value.trim() || "scores.txt", text: $("goal-text").value };
  else {
    goal = { type, item: $("goal-item").value || "B" };
    if ($("goal-avoid").value) goal.avoid = $("goal-avoid").value;
  }
  const within = Number($("within").value);
  return within > 0 ? { type: "all", goals: [goal, { type: "time", within }] } : goal;
}

function levelData() {
  const animal = pack();
  const usesTerrain = state.worlds.some((w) => w.cells.some((row) => row.some((tile) => /[~t\-o]/.test(tile))));
  const [first, ...others] = state.worlds;
  const mustUse = $("must-use").value.split(",").map((s) => s.trim()).filter(Boolean);
  const data = {
    id: $("level-id").value.trim() || "my-l01",
    title: $("title").value.trim() || "My level",
    module: $("module").value,
    concepts: [$("module").value],
    animal: animal?.id || "monkey",
    world: worldSpec(first),
    goal: goalFor(first),
    constraints: { maxLines: Math.max(1, countLines($("solution").value)), mustUse },
    unlockedBlocks: [...BLOCKS, ...(usesTerrain ? animal?.tricks || [] : [])],
    hints: lines($("hints").value),
    mode: "both_editable",
  };
  if (others.length) {
    data.variants = others.map((w) => {
      const variant = worldSpec(w);
      if ($("goal-type").value === "reach" && w.flag) variant.goal = goalFor(w);
      return variant;
    });
  }
  if ($("min-python").value) data.minPython = $("min-python").value;
  if (usesTerrain) data.signature = true;
  if ($("starter").value.trim()) data.starter = $("starter").value;
  const sk = {};
  if ($("title-sk").value.trim()) sk.title = $("title-sk").value.trim();
  const hintsSk = lines($("hints-sk").value);
  if (hintsSk.length) sk.hints = hintsSk;
  if (Object.keys(sk).length) data.i18n = { sk };
  return data;
}

// --- test, play, share, keep, download, open ------------------------------------------------

function report(ok, message, errors = []) {
  $("report").className = `report ${ok ? "ok" : "err"}`;
  $("report").replaceChildren(message, ...(errors.length ? [el("ul", {}, ...errors.map((e) => el("li", {}, e)))] : []));
}

async function test() {
  $("report").className = "report";
  $("report").textContent = t("Testing…");
  try {
    const result = await api.checkLevel(levelData(), $("solution").value);
    if (result.ok) report(true, t("The solution earns every star, in every world and for every animal that can play it."));
    else report(false, t("Not yet:"), result.errors);
    return result.ok;
  } catch (error) {
    report(false, error.message);
    return false;
  }
}

function shareLink() {
  const url = new URL("index.html", location.href);
  url.hash = `play=${encodeShare({ level: levelData() })}`;
  return url.href;
}

async function play() {
  if (await test()) window.open(shareLink(), "_blank");
}

async function share() {
  if (!(await test())) return;
  const link = shareLink();
  try {
    await navigator.clipboard.writeText(link);
    report(true, t("The link is copied. Whoever opens it plays the level; nothing is uploaded."));
  } catch {
    report(true, link);
  }
}

// On a classroom hub: send the level to the teacher, who decides whether the class sees it.
async function shareWithClass() {
  if (!(await test())) return;
  let player = null;
  try {
    player = localStorage.getItem("codezoo.player");
  } catch {
    player = null;
  }
  if (!player) {
    report(false, t("Pick your picture in the game first, then share."));
    return;
  }
  const data = levelData();
  try {
    await api.share(player, "level", data.title || data.id, { level: data, solution: $("solution").value });
    report(true, t("Sent! The class sees your level once the teacher says yes."));
  } catch (error) {
    report(false, error.message);
  }
}

function readLibrary() {
  try {
    return JSON.parse(localStorage.getItem(LIBRARY_KEY) || "{}");
  } catch {
    return {};
  }
}

function writeLibrary(library) {
  try {
    localStorage.setItem(LIBRARY_KEY, JSON.stringify(library));
  } catch {
    report(false, t("This browser can't keep levels; download them instead."));
  }
}

function keep() {
  const library = readLibrary();
  const data = levelData();
  library[data.id] = { level: data, solution: $("solution").value };
  writeLibrary(library);
  renderLibrary();
  $("library-box").open = true;
}

function renderLibrary() {
  const library = readLibrary();
  const entries = Object.values(library);
  $("library").replaceChildren(
    ...(entries.length
      ? entries.map(({ level, solution }) => {
          const edit = el("button", { type: "button", class: "small" }, t("Edit"));
          edit.addEventListener("click", () => load(level, solution));
          const forget = el("button", { type: "button", class: "small" }, t("Forget"));
          forget.addEventListener("click", () => {
            const next = readLibrary();
            delete next[level.id];
            writeLibrary(next);
            renderLibrary();
          });
          return el("li", {}, `${level.id} · ${level.title} `, edit, " ", forget);
        })
      : [el("li", { class: "note" }, t("No levels kept yet."))]),
  );
}

function save(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = el("a", { href: url, download: name });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function download() {
  const data = levelData();
  const name = data.id.split("-").pop() || "l01";
  save(`${name}.json`, `${JSON.stringify(data, null, 2)}\n`, "application/json");
  save(`${name}.solution.py`, $("solution").value, "text/x-python");
}

function worldFrom(spec) {
  const rows = typeof spec.tiles === "string" ? spec.tiles.split("\n") : spec.tiles;
  return {
    cells: rows.map((row) => [...row]),
    up: Object.fromEntries((spec.items || []).map(([x, y, tile]) => [`${x},${y}`, tile])),
    start: spec.start.slice(0, 2),
    facing: spec.start[2],
    flag: null,
    inputs: (spec.inputs || []).join("\n"),
    data: formatFiles(spec.data),
    noGil: spec.gil === false,
  };
}

function load(data, solution) {
  const goals = data.goal.type === "all" ? data.goal.goals : [data.goal];
  const main = goals.find((g) => g.type !== "time") || goals[0];
  const time = goals.find((g) => g.type === "time");
  state.worlds = [worldFrom(data.world), ...(data.variants || []).map(worldFrom)];
  state.worlds[0].flag = main.at || null;
  (data.variants || []).forEach((variant, i) => {
    state.worlds[i + 1].flag = variant.goal?.at || main.at || null;
  });
  $("width").value = state.worlds[0].cells[0].length;
  $("height").value = state.worlds[0].cells.length;
  $("level-id").value = data.id;
  $("title").value = data.title || data.id;
  $("title-sk").value = data.i18n?.sk?.title || "";
  $("hints-sk").value = (data.i18n?.sk?.hints || []).join("\n");
  $("module").value = data.module;
  $("min-python").value = data.minPython || "";
  $("animal").value = data.animal || "monkey";
  tools();
  $("goal-type").value = ["collect_all", "reach", "say", "print", "file"].includes(main.type) ? main.type : "collect_all";
  if (main.item) $("goal-item").value = main.item;
  $("goal-avoid").value = main.avoid || "";
  if (main.text) $("goal-text").value = main.text;
  if (main.name) $("goal-file").value = main.name;
  $("within").value = time ? time.within : "";
  $("must-use").value = (data.constraints?.mustUse || []).join(", ");
  $("hints").value = (data.hints || []).join("\n");
  $("starter").value = data.starter || "";
  if (solution !== undefined) $("solution").value = solution;
  goalRows();
  showWorld(0);
}

async function open(file) {
  try {
    load(JSON.parse(await file.text()));
  } catch (error) {
    report(false, t("That file is not a level: {message}", { message: error.message }));
  }
}

function goalRows() {
  const type = $("goal-type").value;
  $("goal-item-row").hidden = type !== "collect_all";
  $("goal-avoid-row").hidden = type !== "collect_all";
  $("goal-text-row").hidden = !["say", "print", "file"].includes(type);
  $("goal-file-row").hidden = type !== "file";
}

// --- wiring --------------------------------------------------------------------------------

let painting = false;
$("grid").addEventListener("pointerdown", (event) => {
  const cell = event.target.closest(".cell");
  if (!cell) return;
  painting = !["start", "flag"].includes(state.tool);
  paint(Number(cell.dataset.x), Number(cell.dataset.y));
});
$("grid").addEventListener("pointerover", (event) => {
  const cell = event.target.closest(".cell");
  if (painting && cell && event.buttons) paint(Number(cell.dataset.x), Number(cell.dataset.y));
});
window.addEventListener("pointerup", () => (painting = false));
for (const id of ["width", "height"]) $(id).addEventListener("change", resize);
$("facing").addEventListener("input", () => {
  world().facing = $("facing").value;
  render();
});
$("inputs").addEventListener("input", () => {
  world().inputs = $("inputs").value;
  render();
});
$("data").addEventListener("input", () => {
  world().data = $("data").value;
  render();
});
$("no-gil").addEventListener("change", () => {
  world().noGil = $("no-gil").checked;
  render();
});
const fields = [
  "level-id", "title", "title-sk", "module", "min-python", "goal-item", "goal-avoid", "goal-text",
  "goal-file", "within", "must-use", "hints", "hints-sk", "starter", "solution",
];
for (const id of fields) $(id).addEventListener("input", render);
$("animal").addEventListener("change", () => {
  tools();
  render();
});
$("goal-type").addEventListener("change", () => {
  goalRows();
  render();
});
$("add-world").addEventListener("click", () => {
  const copy = structuredClone(world());
  state.worlds.push(copy);
  showWorld(state.worlds.length - 1);
});
$("remove-world").addEventListener("click", () => {
  if (state.worlds.length < 2) return;
  state.worlds.splice(state.current, 1);
  showWorld(Math.max(0, state.current - 1));
});
$("test").addEventListener("click", test);
$("play").addEventListener("click", play);
$("share").addEventListener("click", share);
$("keep").addEventListener("click", keep);
$("share-class").addEventListener("click", shareWithClass);
$("download").addEventListener("click", download);
$("open").addEventListener("change", (event) => event.target.files[0] && open(event.target.files[0]));

async function start() {
  translatePage();
  const info = await api.info();
  $("share-class").hidden = !info.hub;
  state.animals = await api.animals();
  $("animal").replaceChildren(...state.animals.map((a) => el("option", { value: a.id }, `${a.emoji} ${a.animalName}`)));
  $("module").replaceChildren(...MODULES.map((m) => el("option", { value: m }, m)));
  $("min-python").replaceChildren(
    ...RELEASES.map((v) => el("option", { value: v }, v ? `Python ${v}+` : t("any (3.11)"))),
  );
  state.worlds = [blankWorld()];
  state.worlds[0].cells[0][1] = "B";
  tools();
  goalRows();
  renderLibrary();
  showWorld(0);
}

start();
