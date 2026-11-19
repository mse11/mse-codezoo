// The code pane: a plain textarea with line numbers and a line highlight.

export class CodeView {
  constructor({ textarea, gutter, mark, onInput }) {
    this.textarea = textarea;
    this.gutter = gutter;
    this.mark = mark;
    this.markedLine = 0;
    textarea.addEventListener("input", () => {
      this.renderGutter();
      onInput(textarea.value);
    });
    textarea.addEventListener("scroll", () => {
      gutter.scrollTop = textarea.scrollTop;
      this.positionMark();
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
    if (this.textarea.value !== text) this.textarea.value = text;
    this.renderGutter();
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

  highlight(line, kind = "run") {
    this.markedLine = line || 0;
    if (!line) {
      this.mark.hidden = true;
      return;
    }
    this.mark.className = `line-mark ${kind}`;
    this.mark.hidden = false;
    const { lineHeight } = this.metrics();
    const top = (line - 1) * lineHeight;
    const view = this.textarea;
    if (top < view.scrollTop || top + lineHeight > view.scrollTop + view.clientHeight) {
      view.scrollTop = Math.max(0, top - view.clientHeight / 2);
    }
    this.positionMark();
  }

  positionMark() {
    if (!this.markedLine) return;
    const { lineHeight, padding } = this.metrics();
    this.mark.style.top = `${padding + (this.markedLine - 1) * lineHeight - this.textarea.scrollTop}px`;
    this.mark.style.height = `${lineHeight}px`;
  }
}
