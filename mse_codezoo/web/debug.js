// The debugger: what the variables hold after each step of a run. The engine sends only
// what changed at each step (interpreter.Runner._watch); Watch adds the changes up while
// the run plays, steps or jumps back. Two views read it:
// - the Variables bar in the console pane: the file's variables, the call that runs now
//   with its own variables, what the last step did, and step back / step on buttons;
// - "show values" in the Python pane: the newest values written beside each line.

import { t } from "./i18n.js";

// The 🐞 switches: one just before Run for all panes, and one in each pane's title
// (Blocks: line numbers on the blocks; Python: values beside the code; Console: the
// Variables bar). All off by default; kept in this browser.
const DEBUG_KEY = "codezoo.debug";
const PANES = ["blocks", "code", "console"];
const PANE_LABELS = {
  blocks: "Debug: line numbers on the blocks",
  code: "Debug: values beside the code",
  console: "Debug: the Variables bar",
};

// `main`: the switch for all panes (just before Run), or a list of such switches
export function setupDebugSwitches(main, paneButtons, onChange) {
  const mains = Array.isArray(main) ? main : [main];
  let state = Object.fromEntries(PANES.map((pane) => [pane, false]));
  try {
    const saved = JSON.parse(localStorage.getItem(DEBUG_KEY) || "{}");
    for (const pane of PANES) state[pane] = saved[pane] === true;
  } catch {
    // storage blocked or unreadable: all off
  }
  const show = () => {
    const any = PANES.some((pane) => state[pane]);
    for (const button of mains) button.setAttribute("aria-pressed", String(any));
    const label = any ? t("Debugging on") : t("Debugging off");
    for (const button of mains) {
      button.title = label;
      button.setAttribute("aria-label", label);
    }
    for (const button of paneButtons) {
      const pane = button.dataset.debug;
      button.setAttribute("aria-pressed", String(state[pane]));
      button.title = t(PANE_LABELS[pane]);
      button.setAttribute("aria-label", t(PANE_LABELS[pane]));
    }
    document.documentElement.dataset.debugBlocks = String(state.blocks);
  };
  const set = (next) => {
    state = next;
    try {
      localStorage.setItem(DEBUG_KEY, JSON.stringify(state));
    } catch {
      // storage blocked: the switches reset next time
    }
    show();
    onChange(state);
  };
  // the main switch: anything on turns everything off, otherwise everything on
  for (const button of mains) button.addEventListener("click", () => {
    const on = !PANES.some((pane) => state[pane]);
    set(Object.fromEntries(PANES.map((pane) => [pane, on])));
  });
  for (const button of paneButtons) {
    button.addEventListener("click", () => set({ ...state, [button.dataset.debug]: !state[button.dataset.debug] }));
  }
  show();
  return {
    get: () => state,
    relabel: show,
    // a level about the debugger opens with every pane's 🐞 on (the child can switch them off)
    turnAllOn() {
      if (PANES.some((pane) => !state[pane])) set(Object.fromEntries(PANES.map((pane) => [pane, true])));
    },
  };
}

const MAX_LINE_TEXT = 48;

export class Watch {
  constructor() {
    this.reset();
  }

  reset() {
    this.globals = new Map(); // name -> value as Python text
    this.locals = new Map(); // the newest call's variables
    this.calls = []; // names of the calls running now, outermost first
    this.changed = new Set(); // "g:name" / "l:name" changed by the last step
    this.lines = new Map(); // line -> "fish = 2, i = 1" (the newest time it ran)
    this.step = null;
    this.index = 0; // steps played so far
    this.next = 0; // the line that runs next (0: none, the run ended or broke)
  }

  get empty() {
    return !this.step;
  }

  // one step, in order; `index` counts the steps played including this one
  apply(step, index) {
    this.step = step;
    this.index = index;
    this.changed = new Set();
    const scope = step.scope || {};
    const shown = [];
    for (const name of scope["g-"] || []) this.globals.delete(name);
    for (const [name, value] of Object.entries(scope.g || {})) {
      this.globals.set(name, value);
      this.changed.add(`g:${name}`);
      shown.push(`${name} = ${value}`);
    }
    // a new call starts with all of its variables new; back in the caller they're old
    const entering = scope.f && scope.f.length > this.calls.length;
    if (scope.f) {
      this.calls = scope.f;
      this.locals = new Map();
    }
    for (const name of scope["l-"] || []) this.locals.delete(name);
    for (const [name, value] of Object.entries(scope.l || {})) {
      this.locals.set(name, value);
      if (!scope.f || entering) {
        this.changed.add(`l:${name}`);
        shown.push(`${name} = ${value}`);
      }
    }
    if (!step.line || step.error) return;
    let text = shown.join(", ");
    if (!text && step.note?.startsWith("-> ")) text = `→ ${step.note.slice(3)}`;
    if (text) this.lines.set(step.line, text.length > MAX_LINE_TEXT ? `${text.slice(0, MAX_LINE_TEXT - 1)}…` : text);
  }
}

function make(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  node.append(...children);
  return node;
}

function table(values, prefix, changed, label) {
  const rows = [...values].map(([name, value]) =>
    make(
      "tr",
      changed.has(`${prefix}:${name}`) ? { class: "changed" } : {},
      make("th", { scope: "row" }, name),
      make("td", {}, value),
    ),
  );
  return make("table", { class: "watch-table", "aria-label": label }, make("tbody", {}, ...rows));
}

// The Variables bar. `box` holds the parts made here; `onBack` / `onNext` move a step.
export class WatchBar {
  constructor(box, { onBack, onNext }) {
    this.box = box;
    this.count = make("span", { class: "watch-count" });
    this.back = make("button", { type: "button", class: "watch-back" }, "◀");
    this.next = make("button", { type: "button", class: "watch-next" }, "▶");
    this.back.addEventListener("click", () => onBack());
    this.next.addEventListener("click", () => onNext());
    this.note = make("p", { class: "watch-note" });
    this.body = make("div", { class: "watch-body" });
    box.replaceChildren(
      make("div", { class: "watch-head" }, make("span", { class: "watch-title" }, `🔍 ${t("Variables")}`), this.count, this.back, this.next),
      this.note,
      this.body,
    );
  }

  render(watch, total, over = false) {
    this.box.querySelector(".watch-title").textContent = `🔍 ${t("Variables")}`;
    this.back.title = t("Step back");
    this.back.setAttribute("aria-label", t("Step back"));
    this.next.title = t("Step");
    this.next.setAttribute("aria-label", t("Step"));
    this.back.disabled = watch.index <= 0;
    this.next.disabled = over || (total > 0 && watch.index >= total);
    this.count.textContent = total ? t("step {n} of {total}", { n: watch.index, total }) : "";
    this.note.className = watch.empty ? "watch-note hint" : "watch-note";
    if (watch.empty) {
      this.note.textContent = t("Press Step to run one line and see what your variables hold.");
      this.body.replaceChildren();
      return;
    }
    const step = watch.step;
    const what = step.error ? `⚠ ${step.error}` : step.note || "";
    // the values are what they hold after this line ran; say so, and which line is next
    const ran = !step.line
      ? what
      : step.error
        ? t("line {line}: {message}", { line: step.line, message: what })
        : `${t("line {line} ran", { line: step.line })}${what ? `: ${what}` : ""}`;
    this.note.replaceChildren(ran);
    if (watch.next) this.note.append(make("span", { class: "watch-next-line" }, `▶ ${t("next: line {line}", { line: watch.next })}`));
    this.note.classList.toggle("error", Boolean(step.error));
    const parts = [];
    if (watch.calls.length) {
      const name = watch.calls[watch.calls.length - 1];
      parts.push(
        make("div", { class: "watch-calls" }, watch.calls.map((c) => `${c}()`).join(" → ")),
        make("h3", {}, t("Inside {name}()", { name })),
        watch.locals.size
          ? table(watch.locals, "l", watch.changed, t("Inside {name}()", { name }))
          : make("p", { class: "watch-none" }, t("No variables yet.")),
      );
    }
    parts.push(
      make("h3", {}, t("In the file")),
      watch.globals.size
        ? table(watch.globals, "g", watch.changed, t("In the file"))
        : make("p", { class: "watch-none" }, t("No variables yet.")),
    );
    this.body.replaceChildren(...parts);
  }
}
