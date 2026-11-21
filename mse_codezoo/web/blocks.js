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
  func: "#995BA5",
  error: "#D65C5C",
  list: "#745BA5",
  trick: "#E6732E",
};

const MATH_OPS = ["+", "-", "*", "/", "//", "%", "**"];
const COMPARE_OPS = ["==", "!=", "<", "<=", ">", ">="];
const CHANGE_OPS = ["+=", "-=", "*="];
const SENSORS = ["is_blocked", "item_here", "item_ahead"];
const TEXT_METHODS = ["upper", "lower", "title", "capitalize", "strip"];
const TRICK_STATEMENTS = ["swing", "climb", "slide", "hide"]; // no inputs
// tricks with one number: the bee's fly(2), the octopus's stretch(3) (await reach(3) is a value)
const TRICK_NUMBER = ["fly", "stretch"];
const TRICK_VALUES = ["sniff", "inventory", "guard_ahead"];
const BUILTINS = new Set([
  "print", "range", "len", "abs", "min", "max", "int", "float", "str", "bool", "round", "type",
  "list", "tuple", "dict", "set", "sorted", "sum", "enumerate", "zip", "reversed", "any", "all",
  "isinstance", "map", "filter", "iter", "next", "super", "input", "open", "issubclass", "callable",
]);
const LIST_SLOTS = ["A", "B", "C", "D"];

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
  break: { type: "cz_break" },
  continue: { type: "cz_continue" },
  def: { type: "cz_def" },
  call: { type: "cz_call" },
  return: { type: "cz_return" },
  try: { type: "cz_try" },
  raise: { type: "cz_raise", inputs: { MSG: txt("oops") } },
  for_each: { type: "cz_for_each" },
  list: { type: "cz_list", inputs: { A: num(1), B: num(2) } },
  append: { type: "cz_append" },
  len: { type: "cz_len" },
  index: { type: "cz_index", inputs: { INDEX: num(0) } },
  get: { type: "cz_get", inputs: { KEY: txt("oak"), DEFAULT: num(0) } },
  items: { type: "cz_items" },
  import: { type: "cz_import" },
  global: { type: "cz_global" },
  swing: { type: "cz_trick", fields: { TRICK: "swing" } },
  climb: { type: "cz_trick", fields: { TRICK: "climb" } },
  slide: { type: "cz_trick", fields: { TRICK: "slide" } },
  hide: { type: "cz_trick", fields: { TRICK: "hide" } },
  build: { type: "cz_build", inputs: { LOG: txt("oak") } },
  inventory: { type: "cz_trick_value", fields: { TRICK: "inventory" } },
  sniff: { type: "cz_trick_value", fields: { TRICK: "sniff" } },
  guard_ahead: { type: "cz_trick_value", fields: { TRICK: "guard_ahead" } },
  // phase 4
  yield: { type: "cz_yield", inputs: { VALUE: num(1) } },
  class: { type: "cz_class" },
  async_def: { type: "cz_async_def" },
  await: { type: "cz_await" },
  fly: { type: "cz_trick_number", fields: { TRICK: "fly" }, inputs: { N: num(2) } },
  stretch: { type: "cz_trick_number", fields: { TRICK: "stretch" }, inputs: { N: num(0) } },
  reach: { type: "cz_reach", inputs: { N: num(0) } },
};

// Cub mode (phase 7): pictures instead of words on the first blocks, for children who can't
// read yet. Same block types, so the IR mapping and the code don't change.
let cubIcons = false;
const label = (words, icon) => (cubIcons ? icon : t(words));
// the colour family of a block, for the colour-linked code pane (each also has a pattern)
const FAMILY = {
  cz_step: "motion", cz_turn_left: "motion", cz_turn_right: "motion", cz_grab: "action",
  cz_say: "say", cz_print: "say", cz_repeat: "loop", cz_while: "loop", cz_for_each: "loop",
  cz_if: "logic", cz_if_else: "logic",
};
if (!Blockly.Extensions.isRegistered("cz_cub_var")) {
  // a cub's repeat block shows only the count: the loop variable stays, hidden
  Blockly.Extensions.register("cz_cub_var", function hideVar() {
    if (cubIcons) this.getField("VAR")?.setVisible(false);
  });
}

const statement = { previousStatement: null, nextStatement: null };
const value = { output: null };
const dropdown = (name, options) => ({ type: "field_dropdown", name, options: options.map((o) => [o, o]) });

export function defineBlocks() {
  Blockly.common.defineBlocksWithJsonArray([
    {
      type: "cz_step",
      message0: label("step %1", "👣 %1"),
      args0: [{ type: "input_value", name: "N" }],
      inputsInline: true,
      colour: COLOURS.motion,
      tooltip: `step() · ${t("Walk forward this many squares.")}`,
      ...statement,
    },
    { type: "cz_turn_left", message0: label("turn left ↺", "↺"), colour: COLOURS.motion, tooltip: `turn_left() · ${t("Turn a quarter to the left.")}`, ...statement },
    { type: "cz_turn_right", message0: label("turn right ↻", "↻"), colour: COLOURS.motion, tooltip: `turn_right() · ${t("Turn a quarter to the right.")}`, ...statement },
    { type: "cz_grab", message0: label("grab", "✋"), colour: COLOURS.action, tooltip: `grab() · ${t("Pick up what is on this square.")}`, ...statement },
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
      message0: label("repeat %1 times (count with %2)", "🔁 %1 × %2"),
      args0: [
        { type: "input_value", name: "COUNT" },
        { type: "field_input", name: "VAR", text: "i" },
      ],
      message1: "%1",
      args1: [{ type: "input_statement", name: "DO" }],
      inputsInline: true,
      colour: COLOURS.loop,
      tooltip: `for … in range() · ${t("Do the blocks inside again and again.")}`,
      extensions: ["cz_cub_var"],
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
    // --- phase 4: generators, classes, async, outlines ---
    {
      type: "cz_yield",
      message0: t("hand out %1"),
      args0: [{ type: "input_value", name: "VALUE" }],
      inputsInline: true,
      colour: COLOURS.func,
      tooltip: `yield · ${t("Hand out one value and pause until the next one is asked for.")}`,
      ...statement,
    },
    {
      type: "cz_await",
      message0: t("wait for %1"),
      args0: [{ type: "input_value", name: "VALUE" }],
      inputsInline: true,
      colour: COLOURS.loop,
      tooltip: `await · ${t("Wait here; other tasks go on meanwhile.")}`,
      ...statement,
    },
    {
      type: "cz_reach",
      message0: t("await reach with arm %1"),
      args0: [{ type: "input_value", name: "N" }],
      inputsInline: true,
      output: null,
      colour: COLOURS.trick,
      tooltip: `await reach() · ${t("Stretch an arm (0-7) and bring back what is there.")}`,
    },
    {
      type: "cz_trick_number",
      message0: "%1 %2",
      args0: [dropdown("TRICK", TRICK_NUMBER), { type: "input_value", name: "N" }],
      inputsInline: true,
      colour: COLOURS.trick,
      tooltip: t("The animal's own trick."),
      ...statement,
    },
    {
      type: "cz_class",
      message0: t("class %1 built on %2"),
      args0: [
        { type: "field_input", name: "NAME", text: "Bee" },
        { type: "field_input", name: "BASES", text: "" },
      ],
      message1: "%1",
      args1: [{ type: "input_statement", name: "DO" }],
      colour: COLOURS.list,
      tooltip: `class · ${t("A new kind of object. Its methods go inside.")}`,
      ...statement,
    },
    {
      type: "cz_async_def",
      message0: t("teach async %1 with inputs %2"),
      args0: [
        { type: "field_input", name: "NAME", text: "arm" },
        { type: "field_input", name: "PARAMS", text: "" },
      ],
      message1: "%1",
      args1: [{ type: "input_statement", name: "DO" }],
      colour: COLOURS.loop,
      tooltip: `async def · ${t("A command that can wait with await while others go on.")}`,
      ...statement,
    },
    {
      // code-first modules: the first line as code (decorators, `with`, type hints...),
      // the body as blocks
      type: "cz_outline",
      message0: "%1",
      args0: [{ type: "field_label_serializable", name: "TEXT", text: "code" }],
      message1: "%1",
      args1: [{ type: "input_statement", name: "DO" }],
      colour: COLOURS.func,
      tooltip: t("The first line is kept exactly as typed; the inside is blocks."),
      ...statement,
    },
    // --- phase 3: loops II, functions, errors, collections, tricks ---
    { type: "cz_break", message0: t("stop the loop"), colour: COLOURS.loop, tooltip: `break · ${t("Leave the loop right now.")}`, previousStatement: null },
    { type: "cz_continue", message0: t("skip to the next turn"), colour: COLOURS.loop, tooltip: `continue · ${t("Jump to the next turn of the loop.")}`, previousStatement: null },
    {
      type: "cz_def",
      message0: t("teach %1 with inputs %2"),
      args0: [
        { type: "field_input", name: "NAME", text: "my_trick" },
        { type: "field_input", name: "PARAMS", text: "" },
      ],
      message1: "%1",
      args1: [{ type: "input_statement", name: "DO" }],
      colour: COLOURS.func,
      tooltip: `def · ${t("Teach a new command. Its inputs are names, split by commas.")}`,
      ...statement,
    },
    {
      type: "cz_call",
      message0: t("do %1 %2 %3"),
      args0: [{ type: "field_input", name: "NAME", text: "my_trick" }, { type: "input_value", name: "A" }, { type: "input_value", name: "B" }],
      inputsInline: true,
      colour: COLOURS.func,
      tooltip: t("Use a command you taught with `def`."),
      ...statement,
    },
    {
      type: "cz_call_value",
      message0: t("answer of %1 %2 %3"),
      args0: [{ type: "field_input", name: "NAME", text: "my_trick" }, { type: "input_value", name: "A" }, { type: "input_value", name: "B" }],
      inputsInline: true,
      colour: COLOURS.func,
      tooltip: t("What a command you taught gives back."),
      ...value,
    },
    {
      type: "cz_return",
      message0: t("give back %1"),
      args0: [{ type: "input_value", name: "VALUE" }],
      inputsInline: true,
      colour: COLOURS.func,
      tooltip: `return · ${t("End the command and give back a value.")}`,
      previousStatement: null,
    },
    {
      type: "cz_try",
      message0: t("try"),
      message1: "%1",
      args1: [{ type: "input_statement", name: "DO" }],
      message2: t("if %1 happens (call it %2)"),
      args2: [{ type: "field_input", name: "KIND", text: "CrackError" }, { type: "field_input", name: "AS", text: "" }],
      message3: "%1",
      args3: [{ type: "input_statement", name: "EXCEPT" }],
      colour: COLOURS.error,
      tooltip: `try / except · ${t("Try something; if that error happens, do the other blocks instead.")}`,
      ...statement,
    },
    {
      type: "cz_raise",
      message0: t("raise %1 %2"),
      args0: [{ type: "field_input", name: "KIND", text: "ValueError" }, { type: "input_value", name: "MSG" }],
      inputsInline: true,
      colour: COLOURS.error,
      tooltip: `raise · ${t("Stop with an error of your own.")}`,
      previousStatement: null,
    },
    {
      type: "cz_for_each",
      message0: t("for each %1 in %2"),
      args0: [{ type: "field_input", name: "VAR", text: "item" }, { type: "input_value", name: "LIST" }],
      message1: "%1",
      args1: [{ type: "input_statement", name: "DO" }],
      inputsInline: true,
      colour: COLOURS.loop,
      tooltip: `for … in · ${t("Do the blocks inside once for every item.")}`,
      ...statement,
    },
    {
      type: "cz_append",
      message0: t("add %1 to the list %2"),
      args0: [{ type: "input_value", name: "VALUE" }, { type: "field_input", name: "VAR", text: "found" }],
      inputsInline: true,
      colour: COLOURS.list,
      tooltip: `.append() · ${t("Put one more item at the end of a list.")}`,
      ...statement,
    },
    {
      type: "cz_import",
      message0: t("from %1 bring %2"),
      args0: [{ type: "field_input", name: "MODULE", text: "tricks" }, { type: "field_input", name: "NAMES", text: "hop" }],
      colour: COLOURS.func,
      tooltip: `from … import · ${t("Bring commands from a helper file.")}`,
      ...statement,
    },
    {
      type: "cz_global",
      message0: t("change the outside %1"),
      args0: [{ type: "field_input", name: "NAMES", text: "score" }],
      colour: COLOURS.variable,
      tooltip: `global · ${t("Let this command change a variable from outside it.")}`,
      ...statement,
    },
    {
      type: "cz_trick",
      message0: "%1",
      args0: [{ type: "field_dropdown", name: "TRICK", options: TRICK_STATEMENTS.map((name) => [name, name]) }],
      colour: COLOURS.trick,
      tooltip: t("The animal's own trick."),
      ...statement,
    },
    {
      type: "cz_build",
      message0: t("build %1"),
      args0: [{ type: "input_value", name: "LOG" }],
      inputsInline: true,
      colour: COLOURS.trick,
      tooltip: `build() · ${t("Lay a log into the water ahead.")}`,
      ...statement,
    },
    {
      type: "cz_trick_value",
      message0: "%1",
      args0: [{ type: "field_dropdown", name: "TRICK", options: TRICK_VALUES.map((name) => [name, name]) }],
      colour: COLOURS.trick,
      tooltip: t("The animal's own trick."),
      ...value,
    },
    {
      type: "cz_list",
      message0: "[ %1 %2 %3 %4 ]",
      args0: LIST_SLOTS.map((name) => ({ type: "input_value", name })),
      inputsInline: true,
      colour: COLOURS.list,
      tooltip: t("A list of things. Empty sockets are left out."),
      ...value,
    },
    {
      type: "cz_len",
      message0: t("how many in %1"),
      args0: [{ type: "input_value", name: "VALUE" }],
      inputsInline: true,
      colour: COLOURS.list,
      tooltip: `len() · ${t("How many items, or letters in a text.")}`,
      ...value,
    },
    {
      type: "cz_index",
      message0: "%1 [ %2 ]",
      args0: [{ type: "input_value", name: "VALUE" }, { type: "input_value", name: "INDEX" }],
      inputsInline: true,
      colour: COLOURS.list,
      tooltip: t("One item: by its position in a list, or by its key in a dictionary."),
      ...value,
    },
    {
      type: "cz_get",
      message0: t("%1 get %2 or %3"),
      args0: [{ type: "input_value", name: "VALUE" }, { type: "input_value", name: "KEY" }, { type: "input_value", name: "DEFAULT" }],
      inputsInline: true,
      colour: COLOURS.list,
      tooltip: `.get() · ${t("The value for a key, or the other value when the key is missing.")}`,
      ...value,
    },
    {
      type: "cz_items",
      message0: t("pairs in %1"),
      args0: [{ type: "input_value", name: "VALUE" }],
      inputsInline: true,
      colour: COLOURS.list,
      tooltip: `.items() · ${t("Every key with its value.")}`,
      ...value,
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

// "Big targets" in Look and feel (look.js): bigger blocks, and a tap on a palette block adds
// it to the end of the program, for children who find precise dragging hard.
// Cub mode always has big targets.
const big = () =>
  document.documentElement.dataset.targets === "true" || document.documentElement.dataset.cub === "true";

function lastInStack(block) {
  let last = block;
  while (last.getNextBlock()) last = last.getNextBlock();
  return last;
}

function bigTargets(workspace) {
  const scale = () => workspace.setScale(big() ? 1.25 : 0.8);
  window.addEventListener("codezoo-look", scale);
  window.addEventListener("codezoo-cub", scale);
  if (big()) scale();
  const flyout = workspace.getFlyout()?.getWorkspace();
  flyout?.addChangeListener((event) => {
    if (!big() || event.type !== Blockly.Events.CLICK || !event.blockId) return;
    const source = flyout.getBlockById(event.blockId)?.getRootBlock();
    if (!source) return;
    const state = Blockly.serialization.blocks.save(source, { addCoordinates: false });
    const top = workspace.getTopBlocks(true).find((b) => b.previousConnection || b.nextConnection);
    const block = Blockly.serialization.blocks.append(state, workspace);
    workspace.cubTapped?.(block); // read the new block aloud
    const last = top && top !== block ? lastInStack(top) : null;
    if (last?.nextConnection && block.previousConnection) {
      last.nextConnection.connect(block.previousConnection);
    } else {
      block.moveBy(24, 24 + workspace.getTopBlocks().length * 8);
    }
  });
}

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
  // a tap on a block in the program: read it aloud (Cub mode, or Read aloud in Look and feel)
  workspace.addChangeListener((event) => {
    if (event.type !== Blockly.Events.CLICK || !event.blockId || event.targetType !== "block") return;
    const block = workspace.getBlockById(event.blockId);
    if (block) workspace.cubTapped?.(block);
  });
  window.addEventListener("resize", () => Blockly.svgResize(workspace));
  darkQuery.addEventListener("change", () => workspace.setTheme(currentTheme()));
  bigTargets(workspace);
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
    // Cub mode: picture labels and big blocks; load() the program again after.
    setCub(on) {
      if (cubIcons === Boolean(on)) return false;
      cubIcons = Boolean(on);
      api.redefine();
      window.dispatchEvent(new CustomEvent("codezoo-cub"));
      return true;
    },
    // called with a block the child tapped (or added with a tap)
    onTap(callback) {
      workspace.cubTapped = callback;
    },
    // the colour family of the block for an IR statement id (null: no block, or no family)
    familyOf(id) {
      const block = workspace.getBlockById(id);
      return block ? FAMILY[block.type] || null : null;
    },
    // a code line was tapped: make its block wiggle so the child sees which one it is
    wiggle(id) {
      const block = workspace.getBlockById(id);
      const svg = block?.getSvgRoot?.();
      if (!svg) return;
      block.select?.();
      svg.classList.remove("cz-wiggle");
      void svg.getBoundingClientRect();
      svg.classList.add("cz-wiggle");
      setTimeout(() => svg.classList.remove("cz-wiggle"), 700);
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

// What a block says when it is read aloud: "Step 3", "Repeat 4 times".
export function describeBlock(block) {
  const number = (name) => {
    const target = block.getInputTargetBlock(name);
    return target?.type === "cz_number" ? target.getFieldValue("NUM") : "";
  };
  switch (block.type) {
    case "cz_step":
      return t("Step {n}", { n: number("N") || 1 });
    case "cz_turn_left":
      return t("Turn left");
    case "cz_turn_right":
      return t("Turn right");
    case "cz_grab":
      return t("Grab");
    case "cz_repeat": {
      const inside = [];
      for (let child = block.getInputTargetBlock("DO"); child; child = child.getNextBlock()) {
        inside.push(describeBlock(child));
      }
      const times = t("Repeat {n} times", { n: number("COUNT") || "" });
      return inside.length ? `${times}: ${inside.join(", ")}` : times;
    }
    default: {
      const tip = block.getTooltip?.();
      const text = typeof tip === "string" ? tip : "";
      return text.split(" · ").pop() || "";
    }
  }
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
  const reach = context.names.reach;
  if (
    expr.type === "Await" && reach && expr.value.type === "Call" && expr.value.func === reach
    && expr.value.args.length === 1 && !expr.value.keywords.length
  ) {
    return { ...base, type: "cz_reach", inputs: { N: input(expr.value.args[0], context) } };
  }
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
      if (expr.func === "len" && expr.args.length === 1 && noKeywords(expr)) {
        return { ...base, type: "cz_len", inputs: { VALUE: input(expr.args[0], context) } };
      }
      const trick = TRICK_VALUES.find((name) => context.names[name] === expr.func);
      if (trick && expr.args.length === 0 && noKeywords(expr)) {
        return { ...base, type: "cz_trick_value", fields: { TRICK: trick } };
      }
      if (isUserCall(expr, context)) {
        return withArgs({ ...base, type: "cz_call_value", fields: { NAME: expr.func } }, expr.args, context);
      }
      break;
    }
    case "List":
      if (expr.elts.length <= LIST_SLOTS.length && expr.elts.every((e) => e.type !== "Starred")) {
        const inputs = Object.fromEntries(expr.elts.map((e, i) => [LIST_SLOTS[i], input(e, context)]));
        return { ...base, type: "cz_list", inputs };
      }
      break;
    case "Subscript":
      if (expr.index.type !== "Slice") {
        return { ...base, type: "cz_index", inputs: { VALUE: input(expr.value, context), INDEX: input(expr.index, context) } };
      }
      break;
    case "MethodCall":
      if (expr.method === "get" && expr.args.length === 2 && noKeywords(expr)) {
        return {
          ...base,
          type: "cz_get",
          inputs: { VALUE: input(expr.obj, context), KEY: input(expr.args[0], context), DEFAULT: input(expr.args[1], context) },
        };
      }
      if (expr.method === "items" && expr.args.length === 0 && noKeywords(expr)) {
        return { ...base, type: "cz_items", inputs: { VALUE: input(expr.obj, context) } };
      }
      if (TEXT_METHODS.includes(expr.method) && expr.args.length === 0 && noKeywords(expr)) {
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

// A call to a command the learner taught (not an animal action, not a Python builtin).
function isUserCall(call, context) {
  const actions = new Set(Object.values(context.names));
  return !actions.has(call.func) && !BUILTINS.has(call.func) && call.args.length <= 2 && noKeywords(call)
    && call.args.every((a) => a.type !== "Starred");
}

function withArgs(state, args, context) {
  if (!args.length) return state;
  return { ...state, inputs: Object.fromEntries(args.map((a, i) => [["A", "B"][i], input(a, context)])) };
}

const simpleName = (node) => node && node.type === "Name";

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
    const trick = TRICK_STATEMENTS.find((t) => names[t] === func);
    if (trick && args.length === 0) return { ...base, type: "cz_trick", fields: { TRICK: trick } };
    if (func === names.build && args.length === 1) return { ...base, type: "cz_build", inputs: { LOG: input(args[0], context) } };
    if (isUserCall(stmt.value, context)) return withArgs({ ...base, type: "cz_call", fields: { NAME: func } }, args, context);
  }
  if (
    stmt.type === "ExprStmt" && stmt.value.type === "MethodCall" && stmt.value.method === "append"
    && simpleName(stmt.value.obj) && stmt.value.args.length === 1 && noKeywords(stmt.value)
  ) {
    return { ...base, type: "cz_append", fields: { VAR: stmt.value.obj.name }, inputs: { VALUE: input(stmt.value.args[0], context) } };
  }
  if (stmt.type === "Break") return { ...base, type: "cz_break" };
  if (stmt.type === "Continue") return { ...base, type: "cz_continue" };
  if (stmt.type === "Return") {
    return withInputs({ ...base, type: "cz_return" }, { VALUE: stmt.value ? input(stmt.value, context) : undefined });
  }
  const plainDef = stmt.type === "FunctionDef" && !stmt.decorators?.length && !stmt.returns
    && !stmt.type_params?.length
    && stmt.params.every((p) => p.default == null && (p.kind || "plain") === "plain" && !p.annotation);
  if (plainDef) {
    return withInputs(
      {
        ...base,
        type: stmt.is_async ? "cz_async_def" : "cz_def",
        fields: { NAME: stmt.name, PARAMS: stmt.params.map((p) => p.name).join(", ") },
      },
      { DO: body(stmt.body) },
    );
  }
  if (
    stmt.type === "ClassDef" && !stmt.decorators?.length && !stmt.keywords?.length
    && !stmt.type_params?.length && stmt.bases.every(simpleName)
  ) {
    return withInputs(
      { ...base, type: "cz_class", fields: { NAME: stmt.name, BASES: stmt.bases.map((b) => b.name).join(", ") } },
      { DO: body(stmt.body) },
    );
  }
  if (["FunctionDef", "ClassDef", "With"].includes(stmt.type)) {
    const { body: inner, ...head } = stmt;
    return withInputs(
      {
        ...base,
        type: "cz_outline",
        fields: { TEXT: outlineLabel(stmt, context) },
        data: JSON.stringify({ head, ...(stmt.comment != null ? { comment: stmt.comment } : {}) }),
      },
      { DO: body(inner) },
    );
  }
  if (stmt.type === "ExprStmt" && stmt.value.type === "Yield" && stmt.value.value) {
    return { ...base, type: "cz_yield", inputs: { VALUE: input(stmt.value.value, context) } };
  }
  if (stmt.type === "ExprStmt" && stmt.value.type === "Await") {
    return { ...base, type: "cz_await", inputs: { VALUE: input(stmt.value.value, context) } };
  }
  if (
    stmt.type === "ExprStmt" && stmt.value.type === "Call" && noKeywords(stmt.value)
    && stmt.value.args.length === 1
  ) {
    const trick = TRICK_NUMBER.find((name) => names[name] === stmt.value.func);
    if (trick) return { ...base, type: "cz_trick_number", fields: { TRICK: trick }, inputs: { N: input(stmt.value.args[0], context) } };
  }
  if (
    stmt.type === "Try" && stmt.handlers.length === 1 && !stmt.orelse.length && !stmt.finalbody.length
    && (stmt.handlers[0].kind == null || simpleName(stmt.handlers[0].kind))
  ) {
    const handler = stmt.handlers[0];
    return withInputs(
      { ...base, type: "cz_try", fields: { KIND: handler.kind ? handler.kind.name : "", AS: handler.name || "" } },
      { DO: body(stmt.body), EXCEPT: body(handler.body) },
    );
  }
  if (
    stmt.type === "Raise" && stmt.exc && stmt.exc.type === "Call" && stmt.exc.args.length <= 1
    && noKeywords(stmt.exc)
  ) {
    return withInputs(
      { ...base, type: "cz_raise", fields: { KIND: stmt.exc.func } },
      { MSG: stmt.exc.args.length ? input(stmt.exc.args[0], context) : undefined },
    );
  }
  if (stmt.type === "Import" && stmt.names.length) {
    return { ...base, type: "cz_import", fields: { MODULE: stmt.module, NAMES: stmt.names.join(", ") } };
  }
  if (stmt.type === "Global") return { ...base, type: "cz_global", fields: { NAMES: stmt.names.join(", ") } };
  if (stmt.type === "For" && simpleName(stmt.target) && !(stmt.iter.type === "Call" && stmt.iter.func === "range")) {
    return withInputs(
      { ...base, type: "cz_for_each", fields: { VAR: stmt.target.name } },
      { LIST: input(stmt.iter, context), DO: body(stmt.body) },
    );
  }
  if (
    stmt.type === "For" &&
    simpleName(stmt.target) &&
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
  if (stmt.type === "Assign" && simpleName(stmt.target)) {
    return { ...base, type: "cz_set", fields: { VAR: stmt.target.name }, inputs: { VALUE: input(stmt.value, context) } };
  }
  if (stmt.type === "AugAssign" && simpleName(stmt.target) && CHANGE_OPS.includes(`${stmt.op}=`)) {
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

// "@sneaky · def sneak():": the decorators and the header line of a statement with a body
function outlineLabel(stmt, { sourceText, positions }) {
  const span = positions && positions[stmt.id];
  if (!span || !sourceText) return stmt.type === "With" ? "with …:" : `${stmt.name}`;
  const lines = sourceText.split("\n").slice(span.line - 1, span.end_line);
  const decorators = [];
  let head = "";
  for (const line of lines) {
    const text = line.trim();
    if (text.startsWith("@")) decorators.push(text);
    else {
      head = text;
      break;
    }
  }
  const label = [...decorators, head].join(" · ");
  return label.length > 60 ? `${label.slice(0, 59)}…` : label;
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
        keywords: [],
      };
    case "cz_len":
      return { type: "Call", id, func: "len", args: [exprAt(block, "VALUE", "", names)], keywords: [] };
    case "cz_trick_value": {
      const trick = block.getFieldValue("TRICK");
      return { type: "Call", id, func: names[trick] || trick, args: [], keywords: [] };
    }
    case "cz_call_value":
      return { type: "Call", id, func: safeName(block.getFieldValue("NAME")), args: callArgs(block, names), keywords: [] };
    case "cz_reach":
      return {
        type: "Await",
        id,
        value: { type: "Call", id: `${id}.call`, func: names.reach || "reach", args: [exprAt(block, "N", 0, names)], keywords: [] },
      };
    case "cz_list":
      return {
        type: "List",
        id,
        elts: LIST_SLOTS.map((slot) => block.getInputTargetBlock(slot)).filter(Boolean).map((child) => exprOf(child, names)),
      };
    case "cz_index":
      return { type: "Subscript", id, value: exprAt(block, "VALUE", "", names), index: exprAt(block, "INDEX", 0, names) };
    case "cz_get":
      return {
        type: "MethodCall",
        id,
        obj: exprAt(block, "VALUE", null, names),
        method: "get",
        args: [exprAt(block, "KEY", "", names), exprAt(block, "DEFAULT", 0, names)],
        keywords: [],
      };
    case "cz_items":
      return { type: "MethodCall", id, obj: exprAt(block, "VALUE", null, names), method: "items", args: [], keywords: [] };
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
    case "cz_break":
      stmt = { type: "Break", id };
      break;
    case "cz_continue":
      stmt = { type: "Continue", id };
      break;
    case "cz_def":
      stmt = {
        type: "FunctionDef",
        id,
        name: safeName(block.getFieldValue("NAME")),
        params: nameList(block.getFieldValue("PARAMS")).map((param, i) => ({ type: "Param", id: `${id}.p${i}`, name: param, default: null })),
        body: body("DO"),
      };
      break;
    case "cz_call":
      stmt = {
        type: "ExprStmt",
        id,
        value: { type: "Call", id: `${id}.call`, func: safeName(block.getFieldValue("NAME")), args: callArgs(block, names), keywords: [] },
      };
      break;
    case "cz_return": {
      const child = block.getInputTargetBlock("VALUE");
      stmt = { type: "Return", id, value: child ? exprOf(child, names) : null };
      break;
    }
    case "cz_try": {
      const kind = block.getFieldValue("KIND").trim();
      const as = block.getFieldValue("AS").trim();
      stmt = {
        type: "Try",
        id,
        body: body("DO"),
        handlers: [
          {
            type: "ExceptHandler",
            id: `${id}.except`,
            kind: kind ? name(`${id}.kind`, kind) : null,
            name: as ? safeName(as) : null,
            body: body("EXCEPT"),
          },
        ],
        orelse: [],
        finalbody: [],
      };
      break;
    }
    case "cz_raise": {
      const child = block.getInputTargetBlock("MSG");
      stmt = {
        type: "Raise",
        id,
        exc: { type: "Call", id: `${id}.exc`, func: safeName(block.getFieldValue("KIND")), args: child ? [exprOf(child, names)] : [], keywords: [] },
      };
      break;
    }
    case "cz_for_each":
      stmt = { type: "For", id, target: name(`${id}.var`, block.getFieldValue("VAR")), iter: exprAt(block, "LIST", null, names), body: body("DO") };
      break;
    case "cz_append":
      stmt = {
        type: "ExprStmt",
        id,
        value: {
          type: "MethodCall",
          id: `${id}.call`,
          obj: name(`${id}.var`, block.getFieldValue("VAR")),
          method: "append",
          args: [exprAt(block, "VALUE", null, names)],
          keywords: [],
        },
      };
      break;
    case "cz_import":
      stmt = { type: "Import", id, module: safeName(block.getFieldValue("MODULE")), names: nameList(block.getFieldValue("NAMES")) };
      break;
    case "cz_global":
      stmt = { type: "Global", id, names: nameList(block.getFieldValue("NAMES")) };
      break;
    case "cz_trick": {
      const trick = block.getFieldValue("TRICK");
      stmt = call(id, names[trick] || trick);
      break;
    }
    case "cz_build":
      stmt = call(id, names.build || "build", [exprAt(block, "LOG", "oak", names)]);
      break;
    case "cz_raw":
      return data.raw ? reId(data.raw, id) : null;
    case "cz_outline":
      if (!data.head) return null;
      stmt = { ...reId(data.head, id), body: body("DO") };
      break;
    case "cz_yield":
      stmt = {
        type: "ExprStmt",
        id,
        value: { type: "Yield", id: `${id}.yield`, value: exprAt(block, "VALUE", 1, names) },
      };
      break;
    case "cz_await":
      stmt = {
        type: "ExprStmt",
        id,
        value: { type: "Await", id: `${id}.await`, value: exprAt(block, "VALUE", 1, names) },
      };
      break;
    case "cz_trick_number": {
      const trick = block.getFieldValue("TRICK");
      stmt = call(id, names[trick] || trick, [exprAt(block, "N", 1, names)]);
      break;
    }
    case "cz_class":
      stmt = {
        type: "ClassDef",
        id,
        name: safeName(block.getFieldValue("NAME")),
        bases: nameList(block.getFieldValue("BASES")).map((base, i) => name(`${id}.b${i}`, base)),
        keywords: [],
        body: body("DO"),
        decorators: [],
        type_params: [],
      };
      break;
    case "cz_async_def":
      stmt = {
        type: "FunctionDef",
        id,
        name: safeName(block.getFieldValue("NAME")),
        params: nameList(block.getFieldValue("PARAMS")).map((param, i) => ({ type: "Param", id: `${id}.p${i}`, name: param, default: null })),
        body: body("DO"),
        is_async: true,
      };
      break;
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

// "a, b" -> ["a", "b"]: the names typed into a field, each made safe
function nameList(text) {
  return String(text).split(",").map((part) => part.trim()).filter(Boolean).map(safeName);
}

function callArgs(block, names) {
  return ["A", "B"].map((slot) => block.getInputTargetBlock(slot)).filter(Boolean).map((child) => exprOf(child, names));
}

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
