// Python colours for the code panes, in the colours of the blocks: `step` is as blue as the
// step block, `for` as green as the loop block, a variable as orange as the variable
// blocks. So a child sees which line belongs to which block at a glance.
//
// A textarea can only show one colour, so the coloured copy of the text lies exactly under
// it (the same font, padding and scroll) and the textarea's own letters are transparent;
// typing, the cursor and selecting work as before. No library and nothing downloaded: a
// small scanner is enough for the Python children write.

// the block families of blocks.js (COLOURS there; the colours are in style.css)
const FAMILY_WORDS = {
  motion: ["step", "turn_left", "turn_right"],
  action: ["grab"],
  say: ["print", "say"],
  sensor: ["is_blocked", "item_here", "item_ahead"],
  loop: ["for", "while", "break", "continue", "in", "range", "async", "await"],
  logic: ["if", "elif", "else", "and", "or", "not", "is", "True", "False", "None", "bool"],
  func: ["def", "return", "yield", "lambda", "import", "from", "as"],
  error: ["try", "except", "finally", "raise", "assert", "Exception", "ValueError", "TypeError", "KeyError", "IndexError"],
  list: [
    "class", "len", "list", "dict", "tuple", "set", "append", "pop", "insert", "remove", "sorted",
    "reversed", "items", "keys", "values", "enumerate", "zip", "min", "max", "sum", "get",
  ],
  variable: ["global", "nonlocal"],
  math: ["int", "float", "abs", "round"],
  text: ["str", "input", "upper", "lower", "split", "join", "strip", "replace", "format", "startswith", "endswith"],
};
// game mode's own words (gamemode.py): moving, sensing, winning, the critters' class
FAMILY_WORDS.motion.push("go");
FAMILY_WORDS.sensor.push("where", "ticks", "critters", "animals", "player");
FAMILY_WORDS.logic.push("win", "lose");
FAMILY_WORDS.list.push("Critter");
FAMILY_WORDS.say.push("sound");
const NEUTRAL_FAMILY = { step: "motion", turn_left: "motion", turn_right: "motion", grab: "action", say: "say" };
const SENSORS = new Set(FAMILY_WORDS.sensor);
// other Python words: no block of their own, just shown as keywords
const KEYWORDS = new Set(["with", "pass", "del", "match", "case", "type", "self", "super"]);

let families = new Map();
// The animal's own command names, from the level's pack: {neutral name: its name}, like
// {"grab": "catch"} for the penguin; anything that isn't a basic command is a trick.
export function setCommandNames(actions = {}) {
  families = new Map();
  for (const [family, words] of Object.entries(FAMILY_WORDS)) {
    for (const word of words) families.set(word, family);
  }
  for (const [neutral, name] of Object.entries(actions || {})) {
    const family = NEUTRAL_FAMILY[neutral] || (SENSORS.has(neutral) ? "sensor" : "trick");
    families.set(name, family);
  }
}
setCommandNames();

// comments, strings (with prefixes, triple quotes, unclosed ones up to the line's end),
// numbers, decorators, names
const TOKEN = new RegExp(
  [
    String.raw`(#[^\n]*)`,
    String.raw`((?:[rRbBuUfF]{1,2}(?=["']))?(?:"""[\s\S]*?(?:"""|$)|'''[\s\S]*?(?:'''|$)|"(?:[^"\\\n]|\\.)*"?|'(?:[^'\\\n]|\\.)*'?))`,
    String.raw`(\b\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d+)?\b)`,
    String.raw`(@[A-Za-z_][\w.]*)`,
    String.raw`([A-Za-z_]\w*)`,
  ].join("|"),
  "g",
);

const escape = (text) => text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const span = (kind, text) => `<span class="syn-${kind}">${escape(text)}</span>`;

export function highlightPython(text) {
  // the program's own functions and classes: purple like the function blocks, wherever
  // they are made or called
  const own = new Map();
  for (const [, word, name] of text.matchAll(/\b(def|class)\s+([A-Za-z_]\w*)/g)) {
    own.set(name, word === "def" ? "func" : "list");
  }
  let html = "";
  let last = 0;
  for (const match of text.matchAll(TOKEN)) {
    const [whole, comment, string, number, decorator, name] = match;
    html += escape(text.slice(last, match.index));
    last = match.index + whole.length;
    if (comment !== undefined) html += span("note", whole);
    else if (string !== undefined) html += span("text", whole);
    else if (number !== undefined) html += span("math", whole);
    else if (decorator !== undefined) html += span("func", whole);
    else if (name !== undefined) {
      const call = /^\s*\(/.test(text.slice(last, last + 40));
      const family = own.get(name) || families.get(name);
      if (family) html += span(call || KEYWORD_LIKE.has(name) ? `${family} syn-strong` : family, whole);
      else if (KEYWORDS.has(name)) html += span("keyword", whole);
      else if (call) html += span("func", whole); // a function from elsewhere (a module)
      else html += span("variable", whole);
    }
  }
  // a last empty line still takes room, so both layers scroll the same way
  return `${html}${escape(text.slice(last))}\n `;
}
// Python's own words are bold, like commands that are called; names stay plain
const KEYWORD_LIKE = new Set(
  ["for", "while", "break", "continue", "in", "async", "await", "if", "elif", "else", "and", "or", "not", "is",
   "def", "return", "yield", "lambda", "import", "from", "as", "try", "except", "finally", "raise", "assert",
   "class", "global", "nonlocal"],
);

// Colours for one textarea: a <pre> just under it, kept in step with its text and scroll.
export function colourTextarea(textarea) {
  const layer = document.createElement("pre");
  layer.className = "code-colours";
  layer.setAttribute("aria-hidden", "true");
  textarea.before(layer);
  textarea.classList.add("coloured");
  const scroll = () => {
    layer.scrollTop = textarea.scrollTop;
    layer.scrollLeft = textarea.scrollLeft;
  };
  const render = () => {
    layer.innerHTML = highlightPython(textarea.value);
    scroll();
  };
  textarea.addEventListener("input", render);
  textarea.addEventListener("scroll", scroll);
  render();
  return { render, layer };
}
