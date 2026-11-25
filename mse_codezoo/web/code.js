// The code pane: a textarea with line numbers, a line highlight and Python colours
// (syntax.js draws the coloured text just under the textarea's transparent letters).
// In Cub mode (phase 7) the lines are tinted in their block's colour, with a bar whose
// pattern names the family too (colour is never the only signal); new lines glow.
// The debugger adds a step arrow ▶ beside the line number of the marked line, which (as in
// an IDE's debugger) is the line that runs next; and
// "show values": the newest values of each line written after its code (debug.js).

import { colourTextarea, setCommandNames } from "./syntax.js";

export class CodeView {
  constructor({ textarea, gutter, mark, onInput, onLineTap }) {
    this.textarea = textarea;
    this.gutter = gutter;
    this.mark = mark;
    this.markedLine = 0;
    this.tintList = [];
    this.tintLayer = document.createElement("div");
    this.tintLayer.className = "code-tints";
    this.tintLayer.setAttribute("aria-hidden", "true");
    mark.parentElement.insertBefore(this.tintLayer, mark);
    const arrow = (kind, symbol) => {
      const node = document.createElement("span");
      node.className = `step-arrow ${kind}`;
      node.textContent = symbol;
      node.hidden = true;
      node.setAttribute("aria-hidden", "true");
      gutter.parentElement.insertBefore(node, gutter);
      return node;
    };
    this.pointer = arrow("next", "▶");
    this.values = new Map();
    this.valuesNow = 0;
    this.valueLayer = document.createElement("div");
    this.valueLayer.className = "code-values";
    this.valueLayer.setAttribute("aria-hidden", "true");
    textarea.parentElement.insertBefore(this.valueLayer, textarea);
    this.colours = colourTextarea(textarea);
    // a tap (or the cursor) on a line: which line, for its block to wiggle
    const tapped = () => {
      const line = textarea.value.slice(0, textarea.selectionStart).split("\n").length;
      onLineTap?.(line);
    };
    textarea.addEventListener("click", tapped);
    textarea.addEventListener("input", () => {
      this.renderGutter();
      onInput(textarea.value);
    });
    textarea.addEventListener("scroll", () => {
      gutter.scrollTop = textarea.scrollTop;
      this.positionMark();
      this.positionTints();
      this.renderValues();
    });
    textarea.addEventListener("keydown", (event) => {
      if (event.key === "Tab" && !textarea.readOnly && !event.shiftKey) {
        event.preventDefault();
        textarea.setRangeText("    ", textarea.selectionStart, textarea.selectionEnd, "end");
        textarea.dispatchEvent(new Event("input"));
      }
    });
  }

  get text() {
    return this.textarea.value;
  }

  setText(text) {
    if (this.textarea.value !== text) {
      this.textarea.value = text;
      this.colours.render(); // setting the value sends no input event
    }
    this.renderGutter();
  }

  // the level's animal names its commands ({"grab": "catch"} for the penguin)
  setCommands(actions) {
    setCommandNames(actions);
    this.colours.render();
  }

  setEditable(editable) {
    this.textarea.readOnly = !editable;
  }

  renderGutter() {
    const count = Math.max(1, this.textarea.value.split("\n").length - (this.textarea.value.endsWith("\n") ? 1 : 0));
    this.gutter.textContent = Array.from({ length: count }, (_, i) => i + 1).join("\n");
  }

  metrics() {
    const style = getComputedStyle(this.textarea);
    return { lineHeight: parseFloat(style.lineHeight), padding: parseFloat(style.paddingTop) };
  }

  // the line to mark with a fill and ▶: the one that runs next (kind "error": the one that broke)
  highlight(line, kind = "run") {
    this.markedLine = line || 0;
    this.pointer.hidden = !line;
    if (!line) {
      this.mark.hidden = true;
      return;
    }
    this.mark.className = `line-mark ${kind}`;
    this.mark.hidden = false;
    this.pointer.className = `step-arrow next ${kind}`;
    const { lineHeight } = this.metrics();
    const top = (line - 1) * lineHeight;
    const view = this.textarea;
    if (top < view.scrollTop || top + lineHeight > view.scrollTop + view.clientHeight) {
      view.scrollTop = Math.max(0, top - view.clientHeight / 2);
    }
    this.positionMark();
  }

  // [{line, endLine, family, fresh}] for the lines of each block; [] turns tints off
  setTints(list) {
    this.tintList = list;
    this.tintLayer.replaceChildren(
      ...list.map((tint) => {
        const node = document.createElement("div");
        node.className = `code-tint family-${tint.family}${tint.fresh ? " fresh" : ""}`;
        return node;
      }),
    );
    this.positionTints();
  }

  positionTints() {
    if (!this.tintList.length) return;
    const { lineHeight, padding } = this.metrics();
    this.tintList.forEach((tint, i) => {
      const node = this.tintLayer.children[i];
      node.style.top = `${padding + (tint.line - 1) * lineHeight - this.textarea.scrollTop}px`;
      node.style.height = `${(tint.endLine - tint.line + 1) * lineHeight}px`;
      node.style.left = `${(tint.depth || 0) * 8}px`;
    });
  }

  positionMark() {
    if (!this.markedLine) return;
    const { lineHeight, padding } = this.metrics();
    this.mark.style.top = `${padding + (this.markedLine - 1) * lineHeight - this.textarea.scrollTop}px`;
    this.mark.style.height = `${lineHeight}px`;
    this.pointer.style.top = this.mark.style.top;
    this.pointer.style.height = this.pointer.style.lineHeight = `${lineHeight}px`;
  }

  // "show values": Map(line -> text), written after each line's code; `now` is the line
  // that just ran (drawn stronger). An empty map clears them.
  setValues(values, now = 0) {
    this.values = values;
    this.valuesNow = now;
    this.renderValues();
  }

  renderValues() {
    if (!this.values.size) {
      if (this.valueLayer.childElementCount) this.valueLayer.replaceChildren();
      return;
    }
    const style = getComputedStyle(this.textarea);
    const lineHeight = parseFloat(style.lineHeight);
    const top = parseFloat(style.paddingTop);
    const left = parseFloat(style.paddingLeft);
    this.measure ||= document.createElement("canvas").getContext("2d");
    this.measure.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    const charWidth = this.measure.measureText("0000000000").width / 10;
    const lines = this.textarea.value.split("\n");
    const nodes = [];
    for (const [line, text] of this.values) {
      const source = lines[line - 1];
      if (source === undefined) continue;
      const width = source.replace(/\t/g, "    ").trimEnd().length;
      const node = document.createElement("span");
      node.className = `code-value${line === this.valuesNow ? " now" : ""}`;
      node.textContent = text;
      node.style.top = `${top + (line - 1) * lineHeight - this.textarea.scrollTop}px`;
      node.style.left = `${left + (width + 2) * charWidth - this.textarea.scrollLeft}px`;
      node.style.height = `${lineHeight}px`;
      node.style.lineHeight = `${lineHeight}px`;
      nodes.push(node);
    }
    this.valueLayer.replaceChildren(...nodes);
  }
}
