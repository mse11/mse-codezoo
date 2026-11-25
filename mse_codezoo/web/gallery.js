// The block and command gallery: one picture book of everything the child can use, opened
// with 📖 from the Blocks pane or the Python pane. Every card shows the block and the Python
// it becomes side by side, so the two always reflect each other: both come from the palette
// entry itself (blocks.js galleryEntries), and the code is printed by the engine from the
// block's IR, never written by hand. Opened from Blocks the block leads; from Python the code.

import { api } from "./api.js";
import { GALLERY_GROUPS, createPreview, galleryEntries } from "./blocks.js";
import { t } from "./i18n.js";
import { highlightPython } from "./syntax.js";

const GROUP_NAMES = {
  motion: "Moving",
  action: "Actions",
  trick: "The animal's tricks",
  say: "Saying and printing",
  loop: "Loops",
  logic: "Questions and choices",
  sensor: "Looking around",
  variable: "Variables",
  math: "Numbers and maths",
  text: "Text",
  list: "Lists and dictionaries",
  func: "Commands of your own",
  error: "Errors",
  note: "Notes and more",
};
// an animal's own trick: shown only when the level's animal has it
const TRICKS = new Set(["swing", "climb", "slide", "hide", "build", "inventory", "sniff", "guard_ahead", "fly", "stretch", "reach"]);

function make(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "html") node.innerHTML = value;
    else node.setAttribute(key, value);
  }
  node.append(...children);
  return node;
}

// The code each entry becomes, printed by the engine: one program with every entry, cut
// back into pieces by the source map. If that fails (one odd entry), each on its own.
async function printEntries(entries) {
  const cut = (text, map, entry) => {
    const ids = entry.stmts.map((s) => s.id);
    const spans = ids.map((id) => map[id]).filter(Boolean);
    if (!spans.length) return "";
    const lines = text.split("\n");
    const from = Math.min(...spans.map((s) => s.line));
    const to = Math.max(...spans.map((s) => s.end_line || s.line));
    return lines.slice(from - 1, to).join("\n");
  };
  try {
    const printed = await api.print({ type: "Program", id: "gallery", body: entries.flatMap((e) => e.stmts) });
    for (const entry of entries) entry.code = cut(printed.text, printed.sourceMap, entry) || entry.python;
  } catch {
    await Promise.all(
      entries.map(async (entry) => {
        try {
          const printed = await api.print({ type: "Program", id: "gallery", body: entry.stmts });
          entry.code = printed.text.trimEnd();
        } catch {
          entry.code = entry.python;
        }
      }),
    );
  }
}

export class Gallery {
  // context(): {names, unlocked: [palette keys], modules: {key: module number}, typing: bool};
  // onUse(entry, typing) adds it
  constructor(dialog, { context, onUse }) {
    this.dialog = dialog;
    this.context = context;
    this.onUse = onUse;
    this.entries = [];
    this.selected = null;
    this.from = "blocks";
    this.preview = null;
    this.title = make("h2", { id: "gallery-title" });
    this.search = make("input", { type: "search", class: "gallery-search", autocomplete: "off", spellcheck: "false" });
    this.close = make("button", { type: "button", class: "gallery-close" }, "✕");
    this.list = make("nav", { class: "gallery-list" });
    this.card = make("section", { class: "gallery-card", "aria-live": "polite" });
    this.blockBox = make("div", { class: "gallery-block" });
    dialog.replaceChildren(
      make("div", { class: "gallery-head" }, this.title, this.search, this.close),
      make("div", { class: "gallery-body" }, this.list, this.card),
    );
    dialog.setAttribute("aria-labelledby", "gallery-title");
    this.close.addEventListener("click", () => dialog.close());
    // a tap on the backdrop (outside the box) closes it too
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
    this.search.addEventListener("input", () => this.renderList());
  }

  async open({ from = "blocks", key = null, word = null } = {}) {
    this.from = from;
    const { names, unlocked, modules = {} } = this.context();
    const open = new Set(unlocked || []);
    const everything = galleryEntries(names);
    for (const entry of everything) {
      entry.unlocked = !open.size || open.has(entry.key);
      entry.module = modules[entry.key] || null; // the module that unlocks it
    }
    // other animals' tricks are not this level's business
    this.entries = everything.filter((e) => e.unlocked || !TRICKS.has(e.key));
    this.title.textContent = `📖 ${t("Blocks and commands")}`;
    this.search.placeholder = t("Find a block or a word");
    this.search.setAttribute("aria-label", t("Find a block or a word"));
    this.close.title = t("Close");
    this.close.setAttribute("aria-label", t("Close"));
    this.search.value = "";
    if (!this.dialog.open) this.dialog.showModal();
    this.list.replaceChildren(make("p", { class: "gallery-wait" }, t("Loading...")));
    await printEntries(this.entries);
    const wanted =
      (key && this.entries.find((e) => e.key === key)) ||
      (word && this.findWord(word)) ||
      this.entries.find((e) => e.unlocked) ||
      this.entries[0];
    this.renderList();
    if (wanted) this.select(wanted.key);
  }

  // the entry whose code starts with (or names) this word: `while`, `step`, `append`
  findWord(word) {
    if (!word) return null;
    const starts = (e) => new RegExp(`^\\s*(\\w+\\.)?${word}\\b`).test(e.code || "");
    const names = (e) => new RegExp(`\\b${word}\\b`).test(e.code || "");
    return this.entries.find((e) => e.unlocked && starts(e)) || this.entries.find(starts) || this.entries.find((e) => e.unlocked && names(e)) || null;
  }

  matches(entry, query) {
    if (!query) return true;
    const hay = `${entry.words} ${entry.code} ${entry.meaning} ${entry.key} ${t(GROUP_NAMES[entry.family] || "")}`.toLowerCase();
    return query.toLowerCase().split(/\s+/).every((part) => hay.includes(part));
  }

  renderList() {
    const query = this.search.value.trim();
    const section = (title, entries, later) => {
      const groups = GALLERY_GROUPS.map((family) => [family, entries.filter((e) => e.family === family)]).filter(([, list]) => list.length);
      if (!groups.length) return null;
      return make(
        "div",
        { class: `gallery-section${later ? " later" : ""}` },
        make("h3", {}, title),
        ...groups.map(([family, list]) =>
          make(
            "div",
            { class: "gallery-group" },
            make("h4", { style: `--c:${list[0].colour}` }, t(GROUP_NAMES[family] || family)),
            ...list.map((entry) => this.item(entry)),
          ),
        ),
      );
    };
    const shown = this.entries.filter((e) => this.matches(e, query));
    // later ones by the module that unlocks them ("Module 6"), in order; unknown ones last
    const later = shown.filter((e) => !e.unlocked);
    const modules = [...new Set(later.map((e) => e.module))].sort((a, b) => (a ?? 99) - (b ?? 99));
    const parts = [
      section(t("In this level"), shown.filter((e) => e.unlocked), false),
      ...modules.map((n) => section(`🔒 ${n ? t("Module {n}", { n }) : t("Later")}`, later.filter((e) => e.module === n), true)),
    ].filter(Boolean);
    this.list.replaceChildren(...(parts.length ? parts : [make("p", { class: "gallery-wait" }, t("Nothing found."))]));
  }

  item(entry) {
    const first = (entry.code || entry.python || "").split("\n")[0];
    const button = make(
      "button",
      { type: "button", class: `gallery-item${entry.key === this.selected ? " selected" : ""}`, style: `--c:${entry.colour}`, "data-key": entry.key },
      make("span", { class: "gallery-chip" }, entry.words || entry.key),
      make("code", { class: "gallery-code" }, first),
    );
    if (!entry.unlocked) button.title = entry.module ? t("This one unlocks in module {n}.", { n: entry.module }) : t("This one unlocks in a later level.");
    button.addEventListener("click", () => this.select(entry.key));
    return button;
  }

  select(key) {
    const entry = this.entries.find((e) => e.key === key);
    if (!entry) return;
    this.selected = key;
    for (const node of this.list.querySelectorAll(".gallery-item")) node.classList.toggle("selected", node.dataset.key === key);
    this.list.querySelector(".gallery-item.selected")?.scrollIntoView({ block: "nearest" });
    const { typing } = this.context();
    const code = make("pre", { class: "gallery-python", html: highlightPython(entry.code || entry.python || "").replace(/\n $/, "") });
    const parts = this.from === "code" ? [code, this.blockBox] : [this.blockBox, code];
    const canUse = entry.unlocked && (typing || entry.statement);
    const use = make("button", { type: "button", class: "gallery-use primary" }, typing ? `✏️ ${t("Write it in my code")}` : `➕ ${t("Add it to my program")}`);
    use.disabled = !canUse;
    use.addEventListener("click", () => {
      if (this.onUse(entry, typing)) this.dialog.close();
    });
    const why = !entry.unlocked
      ? entry.module
        ? t("This one unlocks in module {n}.", { n: entry.module })
        : t("This one unlocks in a later level.")
      : !canUse
        ? t("This block goes into a socket of another block, so it can't stand on its own.")
        : "";
    this.card.replaceChildren(
      make("h3", { style: `--c:${entry.colour}` }, entry.words || entry.key),
      ...parts,
      make("p", { class: "gallery-meaning" }, entry.meaning || ""),
      make("div", { class: "gallery-actions" }, use, why ? make("span", { class: "gallery-why" }, why) : ""),
    );
    this.preview ||= createPreview(this.blockBox);
    this.preview.resize();
    this.preview.show(key);
  }
}
