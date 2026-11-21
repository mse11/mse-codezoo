// Pilot readiness (phase 6), the child's side: only when a grown-up or the teacher turned
// "Take part in a pilot" on. A few picture-free questions before and after a module (never
// scored in front of the child), a once-a-day "would you play again?" smiley, and a count of
// errors the page saw. Everything is stored with the player's progress on this computer.

import { api } from "./api.js";
import { t } from "./i18n.js";

const $ = (id) => document.getElementById(id);
const SMILEYS = ["😞", "🙁", "😐", "🙂", "😄"];

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  node.append(...children.filter((child) => child !== null && child !== undefined));
  return node;
}

export class Pilot {
  constructor({ getPlayer }) {
    this.getPlayer = getPlayer;
    this.on = false;
    this.smileyDue = false;
    this.check = null; // {module, phase, questions}
    $("check-form").addEventListener("submit", (event) => {
      event.preventDefault();
      this.submit(false);
    });
    $("check-skip").addEventListener("click", () => this.submit(true));
    $("check-dialog").addEventListener("cancel", (event) => {
      event.preventDefault(); // Escape skips, so the answer is recorded as skipped
      this.submit(true);
    });
  }

  // from the player's progress: is the pilot on, is today's smiley still due
  setProgress(progress) {
    this.on = Boolean(progress?.pilot);
    this.smileyDue = Boolean(progress?.smileyDue);
  }

  async opened(level) {
    const player = this.getPlayer();
    if (!this.on || !player || !level) return;
    try {
      const answer = await api.pilotEvent(player.id, { event: "open", level: level.id });
      if (answer.check) await this.ask(answer.check);
    } catch {
      // the pilot never gets in the way of playing
    }
  }

  async afterRun(run) {
    if (this.on && run.pilotCheck) await this.ask(run.pilotCheck);
  }

  error() {
    const player = this.getPlayer();
    if (this.on && player) api.pilotEvent(player.id, { event: "error" }).catch(() => {});
  }

  async ask({ module, phase }) {
    if ($("check-dialog").open) return;
    const { questions } = await api.checkQuestions(module);
    if (!questions.length) return;
    this.check = { module, phase, questions };
    $("check-intro").textContent =
      phase === "before"
        ? t("Before you start: a few quick questions. It's not a test, just pick what you think.")
        : t("You did a lot! The same questions again: what do you think now?");
    $("check-questions").replaceChildren(...questions.map((q, i) => this.question(q, i)));
    $("check-dialog").showModal();
  }

  question(q, index) {
    const name = `check-${index}`;
    const choices = q.choices.map((choice, i) =>
      el(
        "label",
        { class: "check-choice" },
        el("input", { type: "radio", name, value: String(i) }),
        choice.code !== undefined ? el("code", {}, choice.code) : el("span", {}, choice.text),
      ),
    );
    return el(
      "fieldset",
      { class: "check-question" },
      el("legend", {}, `${index + 1}. ${q.prompt}`),
      q.code ? el("pre", { class: "check-code" }, q.code) : null,
      el("div", { class: "check-choices" }, ...choices),
    );
  }

  async submit(skip) {
    if (!this.check) return;
    const { module, phase, questions } = this.check;
    const answers = questions.map((_, i) => {
      const picked = skip ? null : document.querySelector(`input[name="check-${i}"]:checked`);
      return picked ? Number(picked.value) : null;
    });
    this.check = null;
    $("check-dialog").close();
    const player = this.getPlayer();
    if (player) await api.answerCheck(player.id, module, phase, answers).catch(() => {});
  }

  // a row of smileys under a solved run, once a day
  smileyRow() {
    const player = this.getPlayer();
    if (!this.on || !this.smileyDue || !player) return null;
    const row = el("div", { class: "smiley-row", role: "group", "aria-label": t("Would you like to play again?") });
    row.append(el("span", {}, t("Would you like to play again?")));
    SMILEYS.forEach((face, i) => {
      row.append(
        el(
          "button",
          {
            type: "button",
            class: "smiley",
            "aria-label": t("{n} of 5", { n: i + 1 }),
            onclick: async () => {
              this.smileyDue = false;
              row.replaceChildren(el("span", {}, t("Thank you!")));
              await api.pilotEvent(player.id, { event: "smiley", value: i + 1 }).catch(() => {});
            },
          },
          face,
        ),
      );
    });
    return row;
  }
}
