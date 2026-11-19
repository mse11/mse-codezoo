// The blocks pane: Blockly blocks and the mapping between a Blockly workspace and the IR.
//
// Block ids and IR statement ids are the same strings, so a run step, a code line and a
// block can all be matched. Anything without a block becomes a grey "raw" block that keeps
// its IR, so nothing the learner typed is ever lost.

const Blockly = window.Blockly;

const COLOURS = {
  motion: "#4C97FF",
  action: "#FFAB19",
  say: "#CF63CF",
  loop: "#59C059",
  note: "#8E9A82",
  raw: "#7A7A7A",
};

// level.unlockedBlocks name -> block type
const PALETTE = {
  step: "cz_step",
  turn_left: "cz_turn_left",
  turn_right: "cz_turn_right",
  grab: "cz_grab",
  say: "cz_say",
  for_range: "cz_repeat",
  comment: "cz_comment",
};

const statement = { previousStatement: null, nextStatement: null };

Blockly.common.defineBlocksWithJsonArray([
  {
    type: "cz_step",
    message0: "step %1",
    args0: [{ type: "field_number", name: "N", value: 1, min: 1, max: 99, precision: 1 }],
    colour: COLOURS.motion,
    tooltip: "Walk forward this many squares.",
    ...statement,
  },
  { type: "cz_turn_left", message0: "turn left ↺", colour: COLOURS.motion, tooltip: "Turn a quarter to the left.", ...statement },
  { type: "cz_turn_right", message0: "turn right ↻", colour: COLOURS.motion, tooltip: "Turn a quarter to the right.", ...statement },
  { type: "cz_grab", message0: "grab", colour: COLOURS.action, tooltip: "Pick up what is on this square.", ...statement },
  {
    type: "cz_say",
    message0: "say %1",
    args0: [{ type: "field_input", name: "TEXT", text: "Yum!" }],
    colour: COLOURS.say,
    tooltip: "Show a speech bubble.",
    ...statement,
  },
  {
    type: "cz_repeat",
    message0: "repeat %1 times (count with %2)",
    args0: [
      { type: "field_number", name: "COUNT", value: 3, min: 0, max: 99, precision: 1 },
      { type: "field_input", name: "VAR", text: "i" },
    ],
    message1: "%1",
    args1: [{ type: "input_statement", name: "DO" }],
    colour: COLOURS.loop,
    tooltip: "Do the blocks inside again and again.",
    ...statement,
  },
  {
    type: "cz_comment",
    message0: "# %1",
    args0: [{ type: "field_input", name: "TEXT", text: "a note" }],
    colour: COLOURS.note,
    tooltip: "A note for people. The animal ignores it.",
    ...statement,
  },
  {
    type: "cz_raw",
    message0: "%1",
    args0: [{ type: "field_label_serializable", name: "TEXT", text: "code" }],
    colour: COLOURS.raw,
    tooltip: "Code that has no block yet. It is kept exactly as typed.",
    ...statement,
  },
]);

const DARK = Blockly.Theme.defineTheme("codezoo-dark", {
  base: Blockly.Themes.Classic,
  componentStyles: {
    workspaceBackgroundColour: "#1b1e19",
    toolboxBackgroundColour: "#20231e",
    toolboxForegroundColour: "#e6e8e1",
    flyoutBackgroundColour: "#262a23",
    flyoutForegroundColour: "#e6e8e1",
    flyoutOpacity: 1,
    scrollbarColour: "#5b6152",
    scrollbarOpacity: 0.6,
    insertionMarkerColour: "#ffffff",
    insertionMarkerOpacity: 0.3,
    cursorColour: "#d0d0d0",
  },
});
const LIGHT = Blockly.Theme.defineTheme("codezoo-light", {
  base: Blockly.Themes.Classic,
  componentStyles: { workspaceBackgroundColour: "#ffffff", flyoutBackgroundColour: "#f0efe9" },
});

const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");
const currentTheme = () => {
  const forced = document.documentElement.dataset.theme;
  if (forced) return forced === "dark" ? DARK : LIGHT;
  return darkQuery.matches ? DARK : LIGHT;
};

export function createWorkspace(container, onChange) {
  const workspace = Blockly.inject(container, {
    toolbox: { kind: "flyoutToolbox", contents: [] },
    media: "vendor/blockly/media/", // local copy; the default loads icons from static.blockly.com
    theme: currentTheme(),
    renderer: "zelos",
    trashcan: true,
    sounds: false,
    move: { scrollbars: true, drag: true, wheel: true },
    zoom: { controls: true, startScale: 0.8, maxScale: 2, minScale: 0.4 },
  });
  let loading = false;
  workspace.addChangeListener((event) => {
    if (loading || event.isUiEvent) return;
    onChange();
  });
  window.addEventListener("resize", () => Blockly.svgResize(workspace));
  darkQuery.addEventListener("change", () => workspace.setTheme(currentTheme()));
  return {
    workspace,
    setPalette(unlocked) {
      const contents = unlocked
        .map((name) => PALETTE[name])
        .filter(Boolean)
        .map((type) => ({ kind: "block", type }));
      workspace.updateToolbox({ kind: "flyoutToolbox", contents });
    },
    load(program, names, sourceText, positions) {
      loading = true;
      Blockly.Events.disable();
      try {
        workspace.clear();
        const first = chainState(program.body, names, sourceText, positions);
        if (first) Blockly.serialization.blocks.append({ ...first, x: 24, y: 24 }, workspace);
      } finally {
        Blockly.Events.enable();
        loading = false;
      }
    },
    toProgram(names) {
      return workspaceToProgram(workspace, names);
    },
    highlight(blockId) {
      workspace.highlightBlock(blockId && workspace.getBlockById(blockId) ? blockId : null);
    },
    resize() {
      Blockly.svgResize(workspace);
    },
  };
}

// --- IR -> blocks ------------------------------------------------------------

function chainState(stmts, names, sourceText, positions) {
  const states = stmts.map((stmt) => blockState(stmt, names, sourceText, positions));
  for (let i = states.length - 2; i >= 0; i--) states[i].next = { block: states[i + 1] };
  return states[0] || null;
}

const isConst = (node, kind) => node && node.type === "Const" && typeof node.value === kind;
const isWholeNumber = (node, min) =>
  isConst(node, "number") && Number.isInteger(node.value) && node.value >= min && node.value <= 99;

function blockState(stmt, names, sourceText, positions) {
  const base = { id: stmt.id };
  if (stmt.comment != null) base.data = JSON.stringify({ comment: stmt.comment });

  if (stmt.type === "ExprStmt" && stmt.value.type === "Call") {
    const { func, args } = stmt.value;
    if (func === names.step && (args.length === 0 || (args.length === 1 && isWholeNumber(args[0], 1)))) {
      return { ...base, type: "cz_step", fields: { N: args.length ? args[0].value : 1 } };
    }
    if (args.length === 0 && func === names.turn_left) return { ...base, type: "cz_turn_left" };
    if (args.length === 0 && func === names.turn_right) return { ...base, type: "cz_turn_right" };
    if (args.length === 0 && func === names.grab) return { ...base, type: "cz_grab" };
    if (func === names.say && args.length === 1 && isConst(args[0], "string")) {
      return { ...base, type: "cz_say", fields: { TEXT: args[0].value } };
    }
  }
  if (
    stmt.type === "For" &&
    stmt.iter.type === "Call" &&
    stmt.iter.func === "range" &&
    stmt.iter.args.length === 1 &&
    isWholeNumber(stmt.iter.args[0], 0)
  ) {
    const state = {
      ...base,
      type: "cz_repeat",
      fields: { COUNT: stmt.iter.args[0].value, VAR: stmt.target.name },
    };
    const inner = chainState(stmt.body, names, sourceText, positions);
    if (inner) state.inputs = { DO: { block: inner } };
    return state;
  }
  if (stmt.type === "Comment") return { ...base, type: "cz_comment", fields: { TEXT: stmt.text } };

  return {
    id: stmt.id,
    type: "cz_raw",
    fields: { TEXT: rawLabel(stmt, sourceText, positions) },
    data: JSON.stringify({ raw: stmt }),
  };
}

function rawLabel(stmt, sourceText, positions) {
  let text = stmt.type === "RawCode" ? stmt.text : "";
  const span = positions && positions[stmt.id];
  if (!text && span && sourceText) text = sourceText.split("\n")[span.line - 1] || "";
  const first = (text || stmt.type).split("\n")[0].trim();
  return first.length > 40 ? `${first.slice(0, 39)}…` : first;
}

// --- blocks -> IR ------------------------------------------------------------

function workspaceToProgram(workspace, names) {
  const body = [];
  for (const top of workspace.getTopBlocks(true)) body.push(...chainToStmts(top, names));
  return { type: "Program", id: "program", body };
}

function chainToStmts(first, names) {
  const out = [];
  for (let block = first; block; block = block.getNextBlock()) {
    if (block.isInsertionMarker()) continue;
    const stmt = blockToStmt(block, names);
    if (stmt) out.push(stmt);
  }
  return out;
}

function readData(block) {
  try {
    return block.data ? JSON.parse(block.data) : {};
  } catch {
    return {};
  }
}

function call(id, func, args = []) {
  return { type: "ExprStmt", id, value: { type: "Call", id: `${id}.call`, func, args } };
}

function constant(id, value) {
  return { type: "Const", id, value };
}

function blockToStmt(block, names) {
  const id = block.id;
  const data = readData(block);
  let stmt;
  switch (block.type) {
    case "cz_step":
      stmt = call(id, names.step, [constant(`${id}.n`, Number(block.getFieldValue("N")))]);
      break;
    case "cz_turn_left":
      stmt = call(id, names.turn_left);
      break;
    case "cz_turn_right":
      stmt = call(id, names.turn_right);
      break;
    case "cz_grab":
      stmt = call(id, names.grab);
      break;
    case "cz_say":
      stmt = call(id, names.say, [constant(`${id}.text`, block.getFieldValue("TEXT"))]);
      break;
    case "cz_repeat":
      stmt = {
        type: "For",
        id,
        target: { type: "Name", id: `${id}.var`, name: safeName(block.getFieldValue("VAR")) },
        iter: {
          type: "Call",
          id: `${id}.range`,
          func: "range",
          args: [constant(`${id}.count`, Number(block.getFieldValue("COUNT")))],
        },
        body: chainToStmts(block.getInputTargetBlock("DO"), names),
      };
      break;
    case "cz_comment":
      stmt = { type: "Comment", id, text: block.getFieldValue("TEXT") };
      break;
    case "cz_raw":
      return data.raw ? reId(data.raw, id) : null;
    default:
      return null;
  }
  if (data.comment != null) stmt.comment = data.comment;
  return stmt;
}

function safeName(text) {
  const name = String(text).trim();
  return /^[A-Za-z_][A-Za-z0-9_]*$/.test(name) ? name : "i";
}

// A copied raw block must not reuse the ids of the original.
function reId(node, rootId) {
  let counter = 0;
  const visit = (value, isRoot) => {
    if (Array.isArray(value)) return value.map((item) => visit(item, false));
    if (value && typeof value === "object") {
      const copy = {};
      for (const [key, child] of Object.entries(value)) copy[key] = visit(child, false);
      if ("type" in copy && "id" in copy) copy.id = isRoot ? rootId : `${rootId}.${counter++}`;
      return copy;
    }
    return value;
  };
  return visit(node, true);
}
