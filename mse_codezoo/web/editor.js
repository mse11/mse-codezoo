// Level editor prototype: paint a world, write a reference solution, let the engine test it,
// then download the level JSON and its solution file for mse_codezoo/content/levels/.
// The engine checks the level exactly like `codezoo levels validate` does.

import { api } from "./api.js";
import { initialLang, setLang, t, translatePage } from "./i18n.js";
import { EMOJI } from "./stage.js";

const $ = (id) => document.getElementById(id);
setLang(initialLang());

const TERRAIN = [
  ["~", "💧", "water"],
  ["t", "🌴", "tree"],
  ["-", "🧊", "thin-ice"],
  ["o", "👁️", "watched"],
];
const MODULES = [
  "sequences", "loops-1", "variables", "text", "conditions", "loops-2", "functions", "errors",
  "collections", "recursion",
];
const BLOCKS = [
  "step", "turn_left", "turn_right", "grab", "say", "for_range", "while", "if", "if_else",
  "compare", "logic", "not", "is_blocked", "item_here", "item_ahead", "text", "number", "set",
  "change", "var", "math", "break", "continue", "def", "call", "return", "try", "raise",
  "for_each", "list", "append", "len", "index",
];
const ARROW = { east: "▶", south: "▼", west: "◀", north: "▲" };

const state = {
  animals: [],
  tool: "#",
  width: 6,
  height: 3,
  cells: [], // rows of tile characters
  up: {}, // "x,y" -> item letter sitting on terrain (a coconut up a tree)
  start: [0, 0],
  flag: null,
};

const pack = () => state.animals.find((a) => a.id === $("animal").value) || state.animals[0];

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  node.append(...children);
  return node;
}

function resize() {
  const width = Math.max(1, Math.min(16, Number($("width").value) || 1));
  const height = Math.max(1, Math.min(12, Number($("height").value) || 1));
  state.cells = Array.from({ length: height }, (_, y) =>
    Array.from({ length: width }, (_, x) => state.cells[y]?.[x] ?? "."),
  );
  state.width = width;
  state.height = height;
  state.start = [Math.min(state.start[0], width - 1), Math.min(state.start[1], height - 1)];
  if (state.flag && (state.flag[0] >= width || state.flag[1] >= height)) state.flag = null;
  render();
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
  $("goal-item").replaceChildren(...items.map(([tile, id]) => el("option", { value: tile }, `${EMOJI[id] || ""} ${id}`)));
}

function paint(x, y) {
  const tool = state.tool;
  if (tool === "start") state.start = [x, y];
  else if (tool === "flag") state.flag = [x, y];
  else if (/^[A-Z]$/.test(tool) && state.cells[y][x] === "t") state.up[`${x},${y}`] = tool;
  else {
    state.cells[y][x] = tool;
    delete state.up[`${x},${y}`];
  }
  render();
}

function render() {
  const grid = $("grid");
  grid.style.gridTemplateColumns = `repeat(${state.width}, minmax(24px, 56px))`;
  const terrainClass = Object.fromEntries(TERRAIN.map(([tile, , name]) => [tile, name]));
  const items = pack()?.items || {};
  const cells = [];
  for (let y = 0; y < state.height; y++) {
    for (let x = 0; x < state.width; x++) {
      const tile = state.cells[y][x];
      const classes = ["cell", (x + y) % 2 ? "alt" : "", tile === "#" ? "wall" : terrainClass[tile] || ""];
      let mark = tile === "#" ? "🪨" : items[tile] ? EMOJI[items[tile]] || tile : TERRAIN.find((e) => e[0] === tile)?.[1] || "";
      if (state.up[`${x},${y}`]) mark += EMOJI[items[state.up[`${x},${y}`]]] || "";
      if (state.flag && state.flag[0] === x && state.flag[1] === y) mark += "🏁";
      if (state.start[0] === x && state.start[1] === y) mark = `${pack()?.emoji || "🐾"}${ARROW[$("facing").value]}`;
      const cell = el("div", { class: classes.join(" "), "data-x": x, "data-y": y }, mark);
      cells.push(cell);
    }
  }
  grid.replaceChildren(...cells);
  $("json").textContent = JSON.stringify(levelData(), null, 2);
}

function countLines(text) {
  return text.split("\n").filter((line) => line.trim() && !line.trim().startsWith("#")).length;
}

function levelData() {
  const animal = pack();
  const tiles = state.cells.map((row) => row.join(""));
  const usesTerrain = tiles.some((row) => /[~t\-o]/.test(row));
  const world = { tiles, start: [...state.start, $("facing").value] };
  const up = Object.entries(state.up).map(([key, tile]) => [...key.split(",").map(Number), tile]);
  if (up.length) world.items = up;
  const type = $("goal-type").value;
  const goal =
    type === "reach"
      ? { type, at: state.flag || [state.width - 1, state.height - 1] }
      : type === "say"
        ? { type, text: $("goal-text").value }
        : { type, item: $("goal-item").value || "B" };
  const mustUse = $("must-use").value.split(",").map((s) => s.trim()).filter(Boolean);
  const data = {
    id: $("level-id").value.trim() || "my-l01",
    title: $("title").value.trim() || "My level",
    module: $("module").value,
    concepts: [$("module").value],
    animal: animal?.id || "monkey",
    world,
    goal,
    constraints: { maxLines: Math.max(1, countLines($("solution").value)), mustUse },
    unlockedBlocks: [...BLOCKS, ...(usesTerrain ? animal?.tricks || [] : [])],
    hints: $("hints").value.split("\n").map((s) => s.trim()).filter(Boolean),
    mode: "both_editable",
  };
  if (usesTerrain) data.signature = true;
  if ($("starter").value.trim()) data.starter = $("starter").value;
  return data;
}

async function test() {
  const report = $("report");
  report.className = "report";
  report.textContent = t("Testing…");
  try {
    const result = await api.checkLevel(levelData(), $("solution").value);
    report.className = `report ${result.ok ? "ok" : "err"}`;
    report.replaceChildren(
      result.ok ? t("The solution earns every star, in every world and for every animal that can play it.") : t("Not yet:"),
      ...(result.ok ? [] : [el("ul", {}, ...result.errors.map((e) => el("li", {}, e)))]),
    );
  } catch (error) {
    report.className = "report err";
    report.textContent = error.message;
  }
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

async function open(file) {
  try {
    const data = JSON.parse(await file.text());
    const rows = typeof data.world.tiles === "string" ? data.world.tiles.split("\n") : data.world.tiles;
    state.cells = rows.map((row) => [...row]);
    state.width = rows[0].length;
    state.height = rows.length;
    state.up = Object.fromEntries((data.world.items || []).map(([x, y, tile]) => [`${x},${y}`, tile]));
    state.start = data.world.start.slice(0, 2);
    $("facing").value = data.world.start[2];
    $("width").value = state.width;
    $("height").value = state.height;
    $("level-id").value = data.id;
    $("title").value = data.title || data.id;
    $("module").value = data.module;
    $("animal").value = data.animal || "monkey";
    $("goal-type").value = ["collect_all", "reach", "say"].includes(data.goal.type) ? data.goal.type : "collect_all";
    if (data.goal.item) $("goal-item").value = data.goal.item;
    if (data.goal.text) $("goal-text").value = data.goal.text;
    state.flag = data.goal.at || null;
    $("must-use").value = (data.constraints?.mustUse || []).join(", ");
    $("hints").value = (data.hints || []).join("\n");
    $("starter").value = data.starter || "";
    tools();
    goalRows();
    render();
  } catch (error) {
    $("report").className = "report err";
    $("report").textContent = t("That file is not a level: {message}", { message: error.message });
  }
}

function goalRows() {
  const type = $("goal-type").value;
  $("goal-item-row").hidden = type !== "collect_all";
  $("goal-text-row").hidden = type !== "say";
}

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
for (const id of ["facing", "level-id", "title", "module", "goal-item", "goal-text", "must-use", "hints", "starter", "solution"]) {
  $(id).addEventListener("input", render);
}
$("animal").addEventListener("change", () => {
  tools();
  render();
});
$("goal-type").addEventListener("change", () => {
  goalRows();
  render();
});
$("test").addEventListener("click", test);
$("download").addEventListener("click", download);
$("open").addEventListener("change", (event) => event.target.files[0] && open(event.target.files[0]));

async function start() {
  translatePage();
  state.animals = await api.animals();
  $("animal").replaceChildren(...state.animals.map((a) => el("option", { value: a.id }, `${a.emoji} ${a.animalName}`)));
  $("module").replaceChildren(...MODULES.map((m) => el("option", { value: m }, m)));
  state.cells = [
    [".", "B", ".", ".", ".", "."],
    [".", ".", ".", ".", ".", "."],
    [".", ".", ".", ".", ".", "."],
  ];
  tools();
  goalRows();
  resize();
}

start();
