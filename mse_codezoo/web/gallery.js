// The block and command gallery: one picture book of everything the child can use, opened
// with 📖 from the Blocks pane or the Python pane. Every card shows the block and the Python
// it becomes side by side, so the two always reflect each other: both come from the palette
// entry itself (blocks.js galleryEntries), and the code is printed by the engine from the
// block's IR, never written by hand. Opened from Blocks the block leads; from Python the code.

import { api } from "./api.js";
import { GALLERY_GROUPS, createPreview, galleryEntries } from "./blocks.js";
import { Watch } from "./debug.js";
import { t } from "./i18n.js";
import { speak } from "./speech.js";
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
    // 🖨 a sheet of the cards shown (for a teacher: the blocks of a module, on paper)
    this.print = make("button", { type: "button", class: "gallery-print" }, "🖨");
    this.print.addEventListener("click", () => this.printSheet());
    this.list = make("nav", { class: "gallery-list" });
    this.card = make("section", { class: "gallery-card", "aria-live": "polite" });
    this.blockBox = make("div", { class: "gallery-block" });
    dialog.replaceChildren(
      make("div", { class: "gallery-head" }, this.title, this.search, this.print, this.close),
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
    // other animals' tricks are not this level's business; a cub sees only their own blocks
    this.cub = document.documentElement.dataset.cub === "true";
    this.entries = everything.filter((e) => (this.cub ? e.unlocked : e.unlocked || !TRICKS.has(e.key)));
    this.title.textContent = `📖 ${t("Blocks and commands")}`;
    this.search.placeholder = t("Find a block or a word");
    this.search.setAttribute("aria-label", t("Find a block or a word"));
    this.print.title = t("Print these cards");
    this.print.setAttribute("aria-label", t("Print these cards"));
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
    button.addEventListener("click", () => {
      this.select(entry.key);
      if (this.cub) speak(this.spoken(entry), { force: true }); // a cub hears what they tapped
    });
    return button;
  }

  // what 🔊 says: the block's words, then what it does (no code: it reads oddly aloud)
  spoken(entry) {
    return `${entry.words || entry.key}. ${entry.meaning || ""}`;
  }

  // the cards shown (after a search, too) as a sheet for paper: block words, code, meaning
  printSheet() {
    const shown = new Set([...this.list.querySelectorAll(".gallery-item")].map((node) => node.dataset.key));
    const sheet = make("div", { id: "gallery-print" }, make("h1", {}, `📖 ${t("Blocks and commands")}`));
    let heading = null;
    // this level's blocks first, then by the module that unlocks them (unknown ones last)
    const order = (e) => (e.unlocked ? 0 : e.module || 99);
    const cards = this.entries.filter((e) => shown.has(e.key)).sort((a, b) => order(a) - order(b));
    for (const entry of cards) {
      const section = entry.unlocked ? t("In this level") : entry.module ? t("Module {n}", { n: entry.module }) : t("Later");
      if (section !== heading) {
        heading = section;
        sheet.append(make("h2", {}, section));
      }
      sheet.append(
        make(
          "div",
          { class: "print-card", style: `--c:${entry.colour}` },
          make("span", { class: "gallery-chip" }, entry.words || entry.key),
          make("pre", { class: "print-code" }, entry.code || entry.python || ""),
          make("p", {}, entry.meaning || ""),
        ),
      );
    }
    document.getElementById("gallery-print")?.remove();
    document.body.append(sheet);
    document.documentElement.classList.add("printing-gallery");
    this.dialog.close(); // a modal dialog would print on top of everything
    const done = () => {
      document.documentElement.classList.remove("printing-gallery");
      sheet.remove();
      window.removeEventListener("afterprint", done);
    };
    window.addEventListener("afterprint", done);
    window.print();
  }

  // ▶ the example plays once: the code runs (in this level's world, nothing is recorded), and
  // the card's code shows the debugger's ▶ on the line that runs next and the values beside
  // the lines that ran, one step at a time
  async playExample(entry, pre, button) {
    const token = (this.playing = (this.playing || 0) + 1);
    const { levelId } = this.context();
    const source = entry.code || entry.python || "";
    if (!levelId || !source) return;
    button.disabled = true;
    let run;
    try {
      run = await api.run(levelId, `${source}\n`, undefined, 0);
    } catch {
      button.disabled = false;
      return;
    }
    const lines = source.split("\n");
    const watch = new Watch();
    const draw = (index) => {
      const next = run.steps?.[index]?.line || 0;
      pre.replaceChildren(
        ...lines.map((text, i) => {
          const line = i + 1;
          const value = watch.lines.get(line);
          return make(
            "div",
            { class: `play-line${line === next ? " next" : ""}` },
            make("span", { class: "play-arrow", "aria-hidden": "true" }, line === next ? "▶" : ""),
            make("span", { html: highlightPython(text).replace(/\n $/, "") }),
            value ? make("span", { class: "code-value" }, value) : "",
          );
        }),
      );
    };
    draw(0);
    for (const [index, step] of (run.steps || []).entries()) {
      await new Promise((resolve) => setTimeout(resolve, 650));
      if (token !== this.playing || !this.dialog.open) return;
      watch.apply(step, index + 1);
      draw(index + 1);
    }
    button.disabled = false;
  }

  select(key) {
    const entry = this.entries.find((e) => e.key === key);
    if (!entry) return;
    this.selected = key;
    this.playing = (this.playing || 0) + 1; // another card: an example still playing stops
    for (const node of this.list.querySelectorAll(".gallery-item")) node.classList.toggle("selected", node.dataset.key === key);
    this.list.querySelector(".gallery-item.selected")?.scrollIntoView({ block: "nearest" });
    const { typing } = this.context();
    const code = make("pre", { class: "gallery-python", html: highlightPython(entry.code || entry.python || "").replace(/\n $/, "") });
    const parts = this.from === "code" ? [code, this.blockBox] : [this.blockBox, code];
    // a block of a later module can be added too: to try it out, or for a teacher to show it
    const canUse = typing || entry.statement;
    const say = make("button", { type: "button", class: "gallery-say", title: t("Read it aloud"), "aria-label": t("Read it aloud") }, "🔊");
    say.addEventListener("click", () => speak(this.spoken(entry), { force: true }));
    const use = make("button", { type: "button", class: "gallery-use primary" }, typing ? `✏️ ${t("Write it in my code")}` : `➕ ${t("Add it to my program")}`);
    use.disabled = !canUse;
    use.addEventListener("click", () => {
      if (this.onUse(entry, typing)) this.dialog.close();
    });
    const later = entry.module ? t("This one unlocks in module {n}.", { n: entry.module }) : t("This one unlocks in a later level.");
    const why = !canUse
      ? t("This block goes into a socket of another block, so it can't stand on its own.")
      : !entry.unlocked
        ? `${later} ${t("You can still try it out now.")}`
        : "";
    // a block that can stand on its own can show what it does
    const play = make("button", { type: "button", class: "gallery-play" }, `▶ ${t("Play the example")}`);
    play.hidden = !entry.statement;
    play.addEventListener("click", () => this.playExample(entry, code, play));
    this.card.replaceChildren(
      make("h3", { style: `--c:${entry.colour}` }, entry.words || entry.key, say),
      ...parts,
      make("p", { class: "gallery-meaning" }, entry.meaning || ""),
      make("div", { class: "gallery-actions" }, use, play, why ? make("span", { class: "gallery-why" }, why) : ""),
    );
    this.preview ||= createPreview(this.blockBox);
    this.preview.resize();
    this.preview.show(key);
  }
}
