// The blocks pane: Blockly blocks and the mapping between a Blockly workspace and the IR.
//
// Block ids and IR node ids are the same strings, so a run step, a code line and a block
// can all be matched. Values (numbers, text, variables, questions) are blocks that plug
// into sockets. Anything without a block becomes a grey "raw" block (a statement or a
// value) that keeps its IR, so nothing the learner typed is ever lost.

import { t } from "./i18n.js";

const Blockly = window.Blockly;

const COLOURS = {
  motion: "#4C97FF",
  action: "#FFAB19",
  say: "#CF63CF",
  loop: "#59C059",
  logic: "#5CA6A6",
  variable: "#FF8C1A",
  math: "#40BF4A",
  text: "#C88330",
  sensor: "#5CB1D6",
  note: "#8E9A82",
  raw: "#7A7A7A",
};

const MATH_OPS = ["+", "-", "*", "/", "//", "%", "**"];
const COMPARE_OPS = ["==", "!=", "<", "<=", ">", ">="];
const CHANGE_OPS = ["+=", "-=", "*="];
const SENSORS = ["is_blocked", "item_here", "item_ahead"];
const TEXT_METHODS = ["upper", "lower", "title", "capitalize", "strip"];

// level.unlockedBlocks name -> toolbox entry (with default values as shadow blocks)
const num = (value) => ({ shadow: { type: "cz_number", fields: { NUM: value } } });
const txt = (value) => ({ shadow: { type: "cz_text", fields: { TEXT: value } } });
const PALETTE = {
  step: { type: "cz_step", inputs: { N: num(1) } },
  turn_left: { type: "cz_turn_left" },
  turn_right: { type: "cz_turn_right" },
  grab: { type: "cz_grab" },
  say: { type: "cz_say", inputs: { TEXT: txt("Yum!") } },
  print: { type: "cz_print", inputs: { TEXT: txt("hello") } },
  for_range: { type: "cz_repeat", inputs: { COUNT: num(3) } },
  while: { type: "cz_while" },
  if: { type: "cz_if" },
  if_else: { type: "cz_if_else" },
  set: { type: "cz_set", inputs: { VALUE: num(0) } },
  change: { type: "cz_change", inputs: { VALUE: num(1) } },
  var: { type: "cz_var" },
  number: { type: "cz_number" },
  text: { type: "cz_text" },
  bool: { type: "cz_bool" },
  math: { type: "cz_math", inputs: { A: num(1), B: num(1) } },
  compare: { type: "cz_compare", inputs: { B: num(0) } },
  logic: { type: "cz_logic" },
  not: { type: "cz_not" },
  is_blocked: { type: "cz_sensor", fields: { SENSOR: "is_blocked" } },
  item_here: { type: "cz_sensor", fields: { SENSOR: "item_here" } },
  item_ahead: { type: "cz_sensor", fields: { SENSOR: "item_ahead" } },
  str: { type: "cz_str", inputs: { VALUE: num(3) } },
  text_method: { type: "cz_text_method", inputs: { VALUE: txt("yum") } },
  comment: { type: "cz_comment" },
};

const statement = { previousStatement: null, nextStatement: null };
const value = { output: null };
const dropdown = (name, options) => ({ type: "field_dropdown", name, options: options.map((o) => [o, o]) });

export function defineBlocks() {
  Blockly.common.defineBlocksWithJsonArray([
    {
      type: "cz_step",
      message0: t("step %1"),
      args0: [{ type: "input_value", name: "N" }],
      inputsInline: true,
      colour: COLOURS.motion,
      tooltip: `step() · ${t("Walk forward this many squares.")}`,
      ...statement,
    },
    { type: "cz_turn_left", message0: t("turn left ↺"), colour: COLOURS.motion, tooltip: `turn_left() · ${t("Turn a quarter to the left.")}`, ...statement },
    { type: "cz_turn_right", message0: t("turn right ↻"), colour: COLOURS.motion, tooltip: `turn_right() · ${t("Turn a quarter to the right.")}`, ...statement },
    { type: "cz_grab", message0: t("grab"), colour: COLOURS.action, tooltip: `grab() · ${t("Pick up what is on this square.")}`, ...statement },
    {
      type: "cz_say",
      message0: t("say %1"),
      args0: [{ type: "input_value", name: "TEXT" }],
      inputsInline: true,
      colour: COLOURS.say,
      tooltip: `say() · ${t("Show a speech bubble.")}`,
      ...statement,
    },
    {
      type: "cz_print",
      message0: t("print %1"),
      args0: [{ type: "input_value", name: "TEXT" }],
      inputsInline: true,
      colour: COLOURS.say,
      tooltip: `print() · ${t("Write a line under the stage.")}`,
      ...statement,
    },
    {
      type: "cz_repeat",
      message0: t("repeat %1 times (count with %2)"),
      args0: [
        { type: "input_value", name: "COUNT" },
        { type: "field_input", name: "VAR", text: "i" },
      ],
      message1: "%1",
      args1: [{ type: "input_statement", name: "DO" }],
      inputsInline: true,
      colour: COLOURS.loop,
      tooltip: `for … in range() · ${t("Do the blocks inside again and again.")}`,
      ...statement,
    },
    {
      type: "cz_while",
      message0: t("repeat while %1"),
      args0: [{ type: "input_value", name: "COND" }],
      message1: "%1",
      args1: [{ type: "input_statement", name: "DO" }],
      colour: COLOURS.loop,
      tooltip: `while · ${t("Repeat the blocks inside as long as the question is true.")}`,
      ...statement,
    },
    {
      type: "cz_if",
      message0: t("if %1"),
      args0: [{ type: "input_value", name: "COND" }],
      message1: "%1",
      args1: [{ type: "input_statement", name: "DO" }],
      colour: COLOURS.logic,
      tooltip: `if · ${t("Do the blocks inside only when the question is true.")}`,
      ...statement,
    },
    {
      type: "cz_if_else",
      message0: t("if %1"),
      args0: [{ type: "input_value", name: "COND" }],
      message1: "%1",
      args1: [{ type: "input_statement", name: "DO" }],
      message2: t("else"),
      message3: "%1",
      args3: [{ type: "input_statement", name: "ELSE" }],
      colour: COLOURS.logic,
      tooltip: `if … else · ${t("One way when the question is true, the other way when it is not.")}`,
      ...statement,
    },
    {
      type: "cz_set",
      message0: t("set %1 to %2"),
      args0: [
        { type: "field_input", name: "VAR", text: "count" },
        { type: "input_value", name: "VALUE" },
      ],
      inputsInline: true,
      colour: COLOURS.variable,
      tooltip: `x = … · ${t("Put a value in a box with a name (a variable).")}`,
      ...statement,
    },
    {
      type: "cz_change",
      message0: t("change %1 %2 %3"),
      args0: [
        { type: "field_input", name: "VAR", text: "count" },
        dropdown("OP", CHANGE_OPS),
        { type: "input_value", name: "VALUE" },
      ],
      inputsInline: true,
      colour: COLOURS.variable,
      tooltip: `x += … · ${t("Change the value in a variable.")}`,
      ...statement,
    },
    {
      type: "cz_comment",
      message0: "# %1",
      args0: [{ type: "field_input", name: "TEXT", text: t("a note") }],
      colour: COLOURS.note,
      tooltip: t("A note for people. The animal ignores it."),
      ...statement,
    },
    {
      type: "cz_raw",
      message0: "%1",
      args0: [{ type: "field_label_serializable", name: "TEXT", text: "code" }],
      colour: COLOURS.raw,
      tooltip: t("Code that has no block yet. It is kept exactly as typed."),
      ...statement,
    },
    // --- values ---
    {
      type: "cz_number",
      message0: "%1",
      args0: [{ type: "field_number", name: "NUM", value: 0 }],
      colour: COLOURS.math,
      tooltip: t("A number."),
      ...value,
    },
    {
      type: "cz_text",
      message0: "“%1”",
      args0: [{ type: "field_input", name: "TEXT", text: "" }],
      colour: COLOURS.text,
      tooltip: t("Text, between quotes."),
      ...value,
    },
    {
      type: "cz_bool",
      message0: "%1",
      args0: [dropdown("BOOL", ["True", "False"])],
      colour: COLOURS.logic,
      tooltip: t("Yes or no."),
      ...value,
    },
    {
      type: "cz_var",
      message0: "%1",
      args0: [{ type: "field_input", name: "NAME", text: "count" }],
      colour: COLOURS.variable,
      tooltip: t("The value inside a variable."),
      ...value,
    },
    {
      type: "cz_math",
      message0: "%1 %2 %3",
      args0: [{ type: "input_value", name: "A" }, dropdown("OP", MATH_OPS), { type: "input_value", name: "B" }],
      inputsInline: true,
      colour: COLOURS.math,
      tooltip: t("Count with two values."),
      ...value,
    },
    {
      type: "cz_compare",
      message0: "%1 %2 %3",
      args0: [{ type: "input_value", name: "A" }, dropdown("OP", COMPARE_OPS), { type: "input_value", name: "B" }],
      inputsInline: true,
      colour: COLOURS.logic,
      tooltip: t("Compare two values: the answer is True or False."),
      ...value,
    },
    {
      type: "cz_logic",
      message0: "%1 %2 %3",
      args0: [
        { type: "input_value", name: "A" },
        { type: "field_dropdown", name: "OP", options: [[t("and"), "and"], [t("or"), "or"]] },
        { type: "input_value", name: "B" },
      ],
      inputsInline: true,
      colour: COLOURS.logic,
      tooltip: `and / or · ${t("Both must be true (and), or one is enough (or).")}`,
      ...value,
    },
    {
      type: "cz_not",
      message0: t("not %1"),
      args0: [{ type: "input_value", name: "A" }],
      inputsInline: true,
      colour: COLOURS.logic,
      tooltip: `not · ${t("The opposite: True becomes False.")}`,
      ...value,
    },
    {
      type: "cz_sensor",
      message0: "%1",
      args0: [
        {
          type: "field_dropdown",
          name: "SENSOR",
          options: [[t("is blocked?"), "is_blocked"], [t("item here"), "item_here"], [t("item ahead"), "item_ahead"]],
        },
      ],
      colour: COLOURS.sensor,
      tooltip: `is_blocked() · item_here() · item_ahead() · ${t("Ask the world a question.")}`,
      ...value,
    },
    {
      type: "cz_str",
      message0: t("text of %1"),
      args0: [{ type: "input_value", name: "VALUE" }],
      inputsInline: true,
      colour: COLOURS.text,
      tooltip: `str() · ${t("Turn a value into text.")}`,
      ...value,
    },
    {
      type: "cz_text_method",
      message0: "%1 . %2 ()",
      args0: [{ type: "input_value", name: "VALUE" }, dropdown("METHOD", TEXT_METHODS)],
      inputsInline: true,
      colour: COLOURS.text,
      tooltip: t("A text command: big letters, small letters..."),
      ...value,
    },
    {
      type: "cz_raw_value",
      message0: "%1",
      args0: [{ type: "field_label_serializable", name: "TEXT", text: "value" }],
      colour: COLOURS.raw,
      tooltip: t("Code that has no block yet. It is kept exactly as typed."),
      ...value,
    },
  ]);
}

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
  defineBlocks();
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
  let unlocked = [];
  workspace.addChangeListener((event) => {
    if (loading || event.isUiEvent) return;
    onChange();
  });
  window.addEventListener("resize", () => Blockly.svgResize(workspace));
  darkQuery.addEventListener("change", () => workspace.setTheme(currentTheme()));
  const api = {
    workspace,
    setPalette(names) {
      unlocked = names;
      const contents = names
        .map((name) => PALETTE[name])
        .filter(Boolean)
        .map((entry) => ({ kind: "block", ...structuredClone(entry) }));
      workspace.updateToolbox({ kind: "flyoutToolbox", contents });
    },
    load(program, names, sourceText, positions) {
      loading = true;
      Blockly.Events.disable();
      try {
        workspace.clear();
        const context = { names, sourceText, positions };
        const first = chainState(program.body, context);
        if (first) Blockly.serialization.blocks.append({ ...first, x: 24, y: 24 }, workspace);
      } finally {
        Blockly.Events.enable();
        loading = false;
      }
    },
    // Rebuild the block definitions in the current language; load() the program again after.
    redefine() {
      defineBlocks();
      api.setPalette(unlocked);
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
  return api;
}

// --- IR -> blocks ------------------------------------------------------------

function chainState(stmts, context) {
  const states = stmts.map((stmt) => blockState(stmt, context));
  for (let i = states.length - 2; i >= 0; i--) states[i].next = { block: states[i + 1] };
  return states[0] || null;
}

const isConst = (node, kind) => node && node.type === "Const" && typeof node.value === kind;
const noKeywords = (call) => !call.keywords || call.keywords.length === 0;

// A plain number or text goes in as a shadow block: drop a variable on it and it hides,
// take the variable away and it comes back.
function input(expr, context) {
  const state = exprState(expr, context);
  return state.type === "cz_number" || state.type === "cz_text" ? { shadow: state } : { block: state };
}

function exprState(expr, context) {
  const base = { id: expr.id };
  switch (expr.type) {
    case "Const":
      if (typeof expr.value === "number") return { ...base, type: "cz_number", fields: { NUM: expr.value } };
      if (typeof expr.value === "string") return { ...base, type: "cz_text", fields: { TEXT: expr.value } };
      if (typeof expr.value === "boolean") return { ...base, type: "cz_bool", fields: { BOOL: expr.value ? "True" : "False" } };
      break;
    case "Name":
      return { ...base, type: "cz_var", fields: { NAME: expr.name } };
    case "UnaryOp":
      if (expr.op === "not") return { ...base, type: "cz_not", inputs: { A: input(expr.operand, context) } };
      if (expr.op === "-" && isConst(expr.operand, "number")) {
        return { ...base, type: "cz_number", fields: { NUM: -expr.operand.value } };
      }
      break;
    case "BinOp":
      if (MATH_OPS.includes(expr.op)) {
        return {
          ...base,
          type: "cz_math",
          fields: { OP: expr.op },
          inputs: { A: input(expr.left, context), B: input(expr.right, context) },
        };
      }
      break;
    case "Compare":
      if (expr.ops.length === 1 && COMPARE_OPS.includes(expr.ops[0])) {
        return {
          ...base,
          type: "cz_compare",
          fields: { OP: expr.ops[0] },
          inputs: { A: input(expr.left, context), B: input(expr.comparators[0], context) },
        };
      }
      break;
    case "BoolOp": {
      // a and b and c -> ((a and b) and c), flattened again on the way back
      let state = exprState(expr.values[0], context);
      for (let i = 1; i < expr.values.length; i++) {
        state = {
          id: i === expr.values.length - 1 ? expr.id : `${expr.id}.${i}`,
          type: "cz_logic",
          fields: { OP: expr.op },
          inputs: { A: { block: state }, B: input(expr.values[i], context) },
        };
      }
      return state;
    }
    case "Call": {
      const sensor = SENSORS.find((name) => context.names[name] === expr.func);
      if (sensor && expr.args.length === 0 && noKeywords(expr)) {
        return { ...base, type: "cz_sensor", fields: { SENSOR: sensor } };
      }
      if (expr.func === "str" && expr.args.length === 1 && noKeywords(expr)) {
        return { ...base, type: "cz_str", inputs: { VALUE: input(expr.args[0], context) } };
      }
      break;
    }
    case "MethodCall":
      if (TEXT_METHODS.includes(expr.method) && expr.args.length === 0) {
        return {
          ...base,
          type: "cz_text_method",
          fields: { METHOD: expr.method },
          inputs: { VALUE: input(expr.obj, context) },
        };
      }
      break;
  }
  return {
    id: expr.id,
    type: "cz_raw_value",
    fields: { TEXT: rawLabel(expr, context, true) },
    data: JSON.stringify({ raw: expr }),
  };
}

function blockState(stmt, context) {
  const { names } = context;
  const base = { id: stmt.id };
  if (stmt.comment != null) base.data = JSON.stringify({ comment: stmt.comment });
  const body = (stmts) => {
    const first = chainState(stmts, context);
    return first ? { block: first } : undefined;
  };
  const withInputs = (state, inputs) => {
    const clean = Object.fromEntries(Object.entries(inputs).filter(([, v]) => v));
    return Object.keys(clean).length ? { ...state, inputs: clean } : state;
  };

  if (stmt.type === "ExprStmt" && stmt.value.type === "Call" && noKeywords(stmt.value)) {
    const { func, args } = stmt.value;
    if (func === names.step && args.length <= 1) {
      const n = args.length ? input(args[0], context) : { shadow: { type: "cz_number", fields: { NUM: 1 } } };
      return { ...base, type: "cz_step", inputs: { N: n } };
    }
    if (args.length === 0 && func === names.turn_left) return { ...base, type: "cz_turn_left" };
    if (args.length === 0 && func === names.turn_right) return { ...base, type: "cz_turn_right" };
    if (args.length === 0 && func === names.grab) return { ...base, type: "cz_grab" };
    if (func === names.say && args.length === 1) return { ...base, type: "cz_say", inputs: { TEXT: input(args[0], context) } };
    if (func === "print" && args.length === 1) return { ...base, type: "cz_print", inputs: { TEXT: input(args[0], context) } };
  }
  if (
    stmt.type === "For" &&
    stmt.iter.type === "Call" &&
    stmt.iter.func === "range" &&
    stmt.iter.args.length === 1 &&
    noKeywords(stmt.iter)
  ) {
    return withInputs(
      { ...base, type: "cz_repeat", fields: { VAR: stmt.target.name } },
      { COUNT: input(stmt.iter.args[0], context), DO: body(stmt.body) },
    );
  }
  if (stmt.type === "While") {
    return withInputs({ ...base, type: "cz_while" }, { COND: input(stmt.test, context), DO: body(stmt.body) });
  }
  if (stmt.type === "If") {
    const type = stmt.orelse.length ? "cz_if_else" : "cz_if";
    return withInputs(
      { ...base, type },
      { COND: input(stmt.test, context), DO: body(stmt.body), ELSE: stmt.orelse.length ? body(stmt.orelse) : undefined },
    );
  }
  if (stmt.type === "Assign") {
    return { ...base, type: "cz_set", fields: { VAR: stmt.target.name }, inputs: { VALUE: input(stmt.value, context) } };
  }
  if (stmt.type === "AugAssign" && CHANGE_OPS.includes(`${stmt.op}=`)) {
    return {
      ...base,
      type: "cz_change",
      fields: { VAR: stmt.target.name, OP: `${stmt.op}=` },
      inputs: { VALUE: input(stmt.value, context) },
    };
  }
  if (stmt.type === "Comment") return { ...base, type: "cz_comment", fields: { TEXT: stmt.text } };

  return {
    id: stmt.id,
    type: "cz_raw",
    fields: { TEXT: rawLabel(stmt, context, false) },
    data: JSON.stringify({ raw: stmt }),
  };
}

function rawLabel(node, { sourceText, positions }, isValue) {
  let text = node.type === "RawCode" ? node.text : "";
  const span = positions && positions[node.id];
  if (!text && span && sourceText) {
    const lines = sourceText.split("\n");
    text = span.line === span.end_line && isValue
      ? (lines[span.line - 1] || "").slice(span.col, span.end_col)
      : lines[span.line - 1] || "";
  }
  const first = (text || node.type).split("\n")[0].trim();
  return first.length > 40 ? `${first.slice(0, 39)}…` : first;
}

// --- blocks -> IR ------------------------------------------------------------

function workspaceToProgram(workspace, names) {
  const body = [];
  for (const top of workspace.getTopBlocks(true)) {
    if (top.outputConnection) continue; // a loose value block does nothing on its own
    body.push(...chainToStmts(top, names));
  }
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
  return { type: "ExprStmt", id, value: { type: "Call", id: `${id}.call`, func, args, keywords: [] } };
}

function constant(id, value) {
  return { type: "Const", id, value };
}

function name(id, text) {
  return { type: "Name", id, name: safeName(text) };
}

// The value plugged into `inputName`, or a default when the socket is empty.
function exprAt(block, inputName, fallback, names) {
  const child = block.getInputTargetBlock(inputName);
  return child ? exprOf(child, names) : constant(`${block.id}.${inputName.toLowerCase()}`, fallback);
}

function exprOf(block, names) {
  const id = block.id;
  switch (block.type) {
    case "cz_number":
      return constant(id, Number(block.getFieldValue("NUM")));
    case "cz_text":
      return constant(id, block.getFieldValue("TEXT"));
    case "cz_bool":
      return constant(id, block.getFieldValue("BOOL") === "True");
    case "cz_var":
      return name(id, block.getFieldValue("NAME"));
    case "cz_math":
      return {
        type: "BinOp",
        id,
        op: block.getFieldValue("OP"),
        left: exprAt(block, "A", 0, names),
        right: exprAt(block, "B", 0, names),
      };
    case "cz_compare":
      return {
        type: "Compare",
        id,
        left: exprAt(block, "A", 0, names),
        ops: [block.getFieldValue("OP")],
        comparators: [exprAt(block, "B", 0, names)],
      };
    case "cz_logic": {
      const op = block.getFieldValue("OP");
      const left = exprAt(block, "A", false, names);
      const right = exprAt(block, "B", false, names);
      const values = left.type === "BoolOp" && left.op === op ? [...left.values, right] : [left, right];
      return { type: "BoolOp", id, op, values };
    }
    case "cz_not":
      return { type: "UnaryOp", id, op: "not", operand: exprAt(block, "A", false, names) };
    case "cz_sensor": {
      const sensor = block.getFieldValue("SENSOR");
      return { type: "Call", id, func: names[sensor] || sensor, args: [], keywords: [] };
    }
    case "cz_str":
      return { type: "Call", id, func: "str", args: [exprAt(block, "VALUE", "", names)], keywords: [] };
    case "cz_text_method":
      return {
        type: "MethodCall",
        id,
        obj: exprAt(block, "VALUE", "", names),
        method: block.getFieldValue("METHOD"),
        args: [],
      };
    case "cz_raw_value": {
      const data = readData(block);
      if (data.raw) return reId(data.raw, id);
      break;
    }
  }
  return constant(id, null);
}

function blockToStmt(block, names) {
  const id = block.id;
  const data = readData(block);
  const body = (inputName) => chainToStmts(block.getInputTargetBlock(inputName), names);
  let stmt;
  switch (block.type) {
    case "cz_step":
      stmt = call(id, names.step, [exprAt(block, "N", 1, names)]);
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
      stmt = call(id, names.say, [exprAt(block, "TEXT", "", names)]);
      break;
    case "cz_print":
      stmt = call(id, "print", [exprAt(block, "TEXT", "", names)]);
      break;
    case "cz_repeat":
      stmt = {
        type: "For",
        id,
        target: name(`${id}.var`, block.getFieldValue("VAR")),
        iter: { type: "Call", id: `${id}.range`, func: "range", args: [exprAt(block, "COUNT", 3, names)], keywords: [] },
        body: body("DO"),
      };
      break;
    case "cz_while":
      stmt = { type: "While", id, test: exprAt(block, "COND", false, names), body: body("DO") };
      break;
    case "cz_if":
    case "cz_if_else":
      stmt = {
        type: "If",
        id,
        test: exprAt(block, "COND", false, names),
        body: body("DO"),
        orelse: block.type === "cz_if_else" ? body("ELSE") : [],
      };
      break;
    case "cz_set":
      stmt = { type: "Assign", id, target: name(`${id}.var`, block.getFieldValue("VAR")), value: exprAt(block, "VALUE", 0, names) };
      break;
    case "cz_change":
      stmt = {
        type: "AugAssign",
        id,
        target: name(`${id}.var`, block.getFieldValue("VAR")),
        op: block.getFieldValue("OP").slice(0, -1),
        value: exprAt(block, "VALUE", 1, names),
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

const KEYWORDS = new Set([
  "False", "None", "True", "and", "as", "assert", "async", "await", "break", "class", "continue",
  "def", "del", "elif", "else", "except", "finally", "for", "from", "global", "if", "import", "in",
  "is", "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try", "while", "with", "yield",
]);

function safeName(text) {
  const value = String(text).trim();
  return /^[A-Za-z_][A-Za-z0-9_]*$/.test(value) && !KEYWORDS.has(value) ? value : "x";
}

// A copied raw block must not reuse the ids of the original.
function reId(node, rootId) {
  let counter = 0;
  const visit = (item, isRoot) => {
    if (Array.isArray(item)) return item.map((child) => visit(child, false));
    if (item && typeof item === "object") {
      const copy = {};
      for (const [key, child] of Object.entries(item)) copy[key] = visit(child, false);
      if ("type" in copy && "id" in copy) copy.id = isRoot ? rootId : `${rootId}.${counter++}`;
      return copy;
    }
    return item;
  };
  return visit(node, true);
}
