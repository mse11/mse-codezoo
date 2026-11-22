// Players (picture login), the grown-up gate and panel, and the daily goodbye screen.
// Everything is stored by the local server in the user's data folder; nothing leaves the device.

import { api } from "./api.js";
import { concept, lang, t } from "./i18n.js";

export const FACES = {
  monkey: "🐒", penguin: "🐧", beaver: "🦫", fox: "🦊", octopus: "🐙", bee: "🐝", turtle: "🐢", owl: "🦉",
  // a class has 32 pictures (mse_codezoo/classes.py)
  cat: "🐱", dog: "🐶", frog: "🐸", lion: "🦁", tiger: "🐯", panda: "🐼", koala: "🐨", rabbit: "🐰",
  mouse: "🐭", hedgehog: "🦔", unicorn: "🦄", dragon: "🐲", whale: "🐳", dolphin: "🐬", crab: "🦀", snail: "🐌",
  butterfly: "🦋", ladybug: "🐞", parrot: "🦜", flamingo: "🦩", chick: "🐤", pig: "🐷", horse: "🐴", sloth: "🦥",
};

// In a workshop without names, a player is called after their picture.
const PICTURE_NAMES = {
  monkey: "Monkey", penguin: "Penguin", beaver: "Beaver", fox: "Fox", octopus: "Octopus", bee: "Bee",
  turtle: "Turtle", owl: "Owl", cat: "Cat", dog: "Dog", frog: "Frog", lion: "Lion", tiger: "Tiger",
  panda: "Panda", koala: "Koala", rabbit: "Rabbit", mouse: "Mouse", hedgehog: "Hedgehog", unicorn: "Unicorn",
  dragon: "Dragon", whale: "Whale", dolphin: "Dolphin", crab: "Crab", snail: "Snail", butterfly: "Butterfly",
  ladybug: "Ladybug", parrot: "Parrot", flamingo: "Flamingo", chick: "Chick", pig: "Pig", horse: "Horse",
  sloth: "Sloth",
};

// a child without a typed name is called after the picture: "cat" -> "Cat", "cat 2" -> "Cat 2"
export function displayName(profile) {
  const animal = PICTURE_NAMES[profile.picture];
  if (animal && profile.name === profile.picture) return t(animal);
  const number = animal && profile.name.startsWith(`${profile.picture} `) ? profile.name.slice(profile.picture.length + 1) : "";
  if (/^\d+$/.test(number)) return `${t(animal)} ${number}`;
  return profile.name;
}

const NUMBER_WORDS = {
  en: ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"],
  sk: ["nula", "jeden", "dva", "tri", "štyri", "päť", "šesť", "sedem", "osem", "deväť"],
};

const AT_HOME = {
  bump: "Play “robot” on the floor: one of you gives step and turn commands, the other walks them.",
  unknown_name: "Spell a command together before typing it, then check it letter by letter.",
  syntax: "Look for pairs together: every ( needs a ).",
  not_finished: "Before pressing Run, ask: where will the animal stop?",
  too_long: "Ask: can we do the same with fewer blocks?",
  missing_concept: "Ask: which blocks repeat? Could a loop do that for us?",
  endless_loop: "Play “Simon says, but only if”: act only when a rule is true, like “jump if I hold up a banana”.",
  type_mixup: "Sort objects at home into boxes and label them: is this a number, a word, or yes/no?",
  endless_recursion: "Russian dolls: open one, then the next, until the smallest. That is a base case!",
  uncaught_error: "Plan a “what if it goes wrong?” together: if it rains, we take an umbrella.",
  grab_miss: "Put a toy on the floor and count the steps to it out loud before walking there.",
};

const PLAYER_KEY = "codezoo.player";

function remembered() {
  try {
    return localStorage.getItem(PLAYER_KEY);
  } catch {
    return null;
  }
}

function remember(id) {
  try {
    if (id) localStorage.setItem(PLAYER_KEY, id);
    else localStorage.removeItem(PLAYER_KEY);
  } catch {
    // storage blocked: the player is asked again next time
  }
}

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

const $ = (id) => document.getElementById(id);
const plural = (n, word) => `${n} ${t(n === 1 ? word : `${word}s`)}`;

export class Players {
  constructor({ onChoose, onSettingsChanged }) {
    this.onChoose = onChoose;
    this.onSettingsChanged = onSettingsChanged;
    this.current = null;
    this.pin = null;
    this.picture = "monkey";
    this.classroom = null; // set on a classroom hub: joining replaces "Who's playing?"

    this.playerDialog = $("player-dialog");
    this.grownupDialog = $("grownup-dialog");
    this.goodbyeDialog = $("goodbye-dialog");

    this.playerDialog.addEventListener("cancel", (event) => {
      if (!this.chosen) event.preventDefault(); // someone has to be picked first
    });
    this.goodbyeDialog.addEventListener("cancel", (event) => event.preventDefault());
    $("new-player").addEventListener("submit", (event) => {
      event.preventDefault();
      this.createPlayer();
    });
    $("gate").addEventListener("submit", (event) => {
      event.preventDefault();
      this.openGate();
    });
    for (const button of document.querySelectorAll("#grownup-dialog [data-close]")) {
      button.addEventListener("click", () => this.closeGrownups());
    }
    this.grownupDialog.addEventListener("close", () => this.onSettingsChanged());
    $("save-settings").addEventListener("click", () => this.saveSettings());
    $("pilot-export").addEventListener("click", () => this.preparePilotExport());
    $("pilot-agree").addEventListener("change", (event) => ($("pilot-save").disabled = !event.target.checked));
    $("pilot-save").addEventListener("click", () => this.savePilotExport());
    $("import-player").addEventListener("change", (event) => {
      if (event.target.files[0]) this.importPlayer(event.target.files[0]);
      event.target.value = "";
    });
    $("goodbye-grownups").addEventListener("click", () => {
      this.goodbyeDialog.close();
      this.openGrownups();
    });
    $("goodbye-switch").addEventListener("click", () => {
      this.goodbyeDialog.close();
      this.choose();
    });
  }

  get chosen() {
    return this.current !== undefined && this.current !== null ? true : this.guest === true;
  }

  // --- picking a player ------------------------------------------------------------

  rememberedId() {
    return remembered();
  }

  async start() {
    const data = await api.profiles();
    const id = remembered();
    const known = data.profiles.find((p) => p.id === id);
    if (known) {
      this.select(known);
    } else {
      this.choose();
    }
  }

  select(profile) {
    this.current = profile;
    this.guest = !profile;
    remember(profile?.id);
    this.relabel();
    this.onChoose(profile);
  }

  relabel() {
    const profile = this.current;
    if (profile) $("player").textContent = `${FACES[profile.picture] || "🐾"} ${displayName(profile)}`;
    else $("player").textContent = `🐾 ${t(this.guest ? "Guest" : "Who's playing?")}`;
  }

  async choose() {
    if (this.classroom) return this.classroom.choose();
    const data = await api.profiles();
    const tiles = data.profiles.map((p) =>
      el(
        "button",
        { type: "button", class: "picture-tile", onclick: () => { this.playerDialog.close(); this.select(p); } },
        el("span", { class: "face", "aria-hidden": "true" }, FACES[p.picture] || "🐾"),
        el("span", { class: "name" }, p.name),
        el("span", { class: "stars" }, `★ ${p.stars}`),
      ),
    );
    tiles.push(
      el(
        "button",
        { type: "button", class: "picture-tile", onclick: () => { this.playerDialog.close(); this.select(null); } },
        el("span", { class: "face", "aria-hidden": "true" }, "👀"),
        el("span", { class: "name" }, t("Just try it")),
        el("span", { class: "stars" }, t("nothing is saved")),
      ),
    );
    $("player-list").replaceChildren(...tiles);
    this.renderPictureChoice(data.pictures);
    $("new-error").textContent = "";
    $("new-name").value = "";
    $("new-cub").checked = false;
    this.playerDialog.showModal();
    if (!data.profiles.length) $("new-name").focus();
  }

  renderPictureChoice(pictures) {
    const buttons = pictures.map((picture) => {
      const button = el(
        "button",
        { type: "button", class: "picture-tile", role: "radio", "aria-label": picture,
          "aria-checked": String(picture === this.picture) },
        el("span", { class: "face", "aria-hidden": "true" }, FACES[picture] || "🐾"),
      );
      button.addEventListener("click", () => {
        this.picture = picture;
        for (const other of buttons) other.setAttribute("aria-checked", String(other === button));
      });
      return button;
    });
    $("new-picture").replaceChildren(...buttons);
  }

  async createPlayer() {
    try {
      const profile = await api.addProfile($("new-name").value, this.picture, $("new-cub").checked);
      this.playerDialog.close();
      this.select({ ...profile, stars: 0, solved: 0 });
    } catch (error) {
      $("new-error").textContent = error.message;
    }
  }

  // --- grown-ups ---------------------------------------------------------------------

  async openGrownups() {
    const data = await api.profiles();
    this.hasPin = data.parent.hasPin;
    const a = 3 + Math.floor(Math.random() * 7);
    const b = 3 + Math.floor(Math.random() * 7);
    this.answer = a * b;
    const words = NUMBER_WORDS[lang()] || NUMBER_WORDS.en;
    $("gate-question").textContent = t("What is {a} times {b}?", { a: words[a], b: words[b] });
    $("gate-answer").value = "";
    $("gate-pin").value = "";
    $("gate-pin-row").hidden = !this.hasPin;
    $("gate-error").textContent = "";
    $("gate").hidden = false;
    $("grownup-panel").hidden = true;
    this.grownupDialog.showModal();
    $("gate-answer").focus();
  }

  closeGrownups() {
    this.pin = null;
    this.grownupDialog.close();
  }

  async openGate() {
    if (Number($("gate-answer").value.trim()) !== this.answer) {
      $("gate-error").textContent = t("Not quite. This part is for grown-ups.");
      return;
    }
    const pin = this.hasPin ? $("gate-pin").value : null;
    try {
      const result = await api.parent("check", { pin });
      this.pin = pin;
      $("gate").hidden = true;
      $("grownup-panel").hidden = false;
      this.renderSettings(result.parent);
      this.renderReports();
    } catch (error) {
      $("gate-error").textContent = error.message;
    }
  }

  renderSettings(settings) {
    $("limit").value = settings.dailyMinutes ? String(settings.dailyMinutes) : "";
    if (settings.dailyMinutes && !$("limit").value) {
      $("limit").append(el("option", { value: String(settings.dailyMinutes) }, t("{n} minutes", { n: settings.dailyMinutes })));
      $("limit").value = String(settings.dailyMinutes);
    }
    $("private-mode").checked = settings.privateMode;
    $("pilot-mode").checked = settings.pilot;
    $("pilot-box").hidden = !settings.pilot;
    $("pilot-consent").hidden = true;
    $("new-pin").value = "";
    $("clear-pin").checked = false;
    $("clear-pin-row").hidden = !settings.hasPin;
    $("settings-msg").textContent = "";
  }

  async saveSettings() {
    const body = {
      pin: this.pin,
      dailyMinutes: $("limit").value ? Number($("limit").value) : null,
      privateMode: $("private-mode").checked,
      pilot: $("pilot-mode").checked,
    };
    const newPin = $("new-pin").value.trim();
    if (newPin) body.newPin = newPin;
    if ($("clear-pin").checked) body.clearPin = true;
    try {
      const settings = await api.parent("settings", body);
      if (newPin) this.pin = newPin;
      if (body.clearPin) this.pin = null;
      this.renderSettings(settings);
      $("settings-msg").textContent = t("Saved.");
    } catch (error) {
      $("settings-msg").textContent = "";
      $("settings-msg").append(el("span", { class: "error" }, error.message));
    }
  }

  async renderReports() {
    const data = await api.profiles();
    if (!data.profiles.length) {
      $("reports").replaceChildren(el("p", {}, t("No players yet.")));
      return;
    }
    const cards = [];
    for (const profile of data.profiles) {
      const report = await api.parent("report", { pin: this.pin, profile: profile.id });
      cards.push(this.reportCard(profile, report));
    }
    $("reports").replaceChildren(...cards);
  }

  reportCard(profile, report) {
    const rows = report.concepts.map((row) =>
      el(
        "tr",
        {},
        el("td", {}, concept(row.concept)),
        el("td", { class: `status-${row.status.replace(" ", "-")}` }, t(row.status)),
        el("td", {}, t("{solved} of {levels} levels", row)),
      ),
    );
    const top = report.mistakes[0];
    const card = el(
      "div",
      { class: "report" },
      el("h4", {}, `${FACES[profile.picture] || "🐾"} ${displayName(profile)}`),
      el("p", {}, t("{levels} solved · {stars} · {minutes} in the last 7 days", {
        levels: plural(report.levelsSolved, "level"),
        stars: plural(report.stars, "star"),
        minutes: plural(report.minutesThisWeek, "minute"),
      })),
      el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, t("Idea")), el("th", {}, t("Status")), el("th", {}, t("Progress")))), el("tbody", {}, ...rows)),
      report.mistakes.length
        ? el("p", {}, t("Often: {list}.", { list: report.mistakes.map((m) => m.text).join("; ") }))
        : null,
      top && AT_HOME[top.kind] ? el("p", {}, t("Try at home: {tip}", { tip: t(AT_HOME[top.kind]) })) : null,
      this.cubPart(profile, report.cub),
      this.pilotPart(profile, report.pilot),
    );
    const actions = el(
      "div",
      { class: "actions" },
      el("button", { type: "button", onclick: () => this.exportPlayer(profile) }, t("Save progress to a file")),
      el("button", { type: "button", onclick: () => this.removePlayer(profile) }, t("Remove player")),
    );
    card.append(actions);
    return card;
  }

  // Cub mode (phase 7): on or off per player; the grown-up decides when to move on
  cubPart(profile, cub) {
    if (!cub) return null;
    const box = el("input", { type: "checkbox", ...(cub.on ? { checked: "" } : {}) });
    const save = async (on) => {
      try {
        await api.parent("cub", { pin: this.pin, profile: profile.id, on });
        await this.renderReports();
      } catch {
        box.checked = !on;
      }
    };
    box.addEventListener("change", () => save(box.checked));
    const part = el(
      "div",
      { class: "cub-part" },
      el("label", { class: "check" }, box, " ", el("span", {}, t("Cub mode (ages 6–8): picture blocks, read aloud, the cub levels"))),
    );
    if (cub.on) {
      part.append(el("p", {}, t("Cub levels: {solved} of {levels} solved.", cub)));
    }
    if (cub.ready) {
      const move = el("button", { type: "button", class: "primary small" }, t("Move to the main course"));
      move.addEventListener("click", () => save(false));
      part.append(el("p", { class: "cub-ready" }, t("Every cub level is solved. Ready for the main course? Nothing is said to the child; you decide."), " ", move));
    }
    return part;
  }

  // pilot (phase 6): show what the file holds, then save it only after "I agree"
  async preparePilotExport() {
    const { file, contents } = await api.parent("pilot-export", { pin: this.pin });
    this.pilotFile = file;
    $("pilot-contents").replaceChildren(...contents.map((line) => el("li", {}, line)));
    $("pilot-agree").checked = false;
    $("pilot-save").disabled = true;
    $("pilot-consent").hidden = false;
  }

  savePilotExport() {
    if (!this.pilotFile || !$("pilot-agree").checked) return;
    const blob = new Blob([JSON.stringify(this.pilotFile, null, 2)], { type: "application/json" });
    const link = el("a", { href: URL.createObjectURL(blob), download: `codezoo-pilot-${this.pilotFile.exported}.json` });
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
    $("pilot-consent").hidden = true;
  }

  pilotPart(profile, pilot) {
    if (!pilot) return null;
    const select = el(
      "select",
      { "aria-label": t("Age band") },
      el("option", { value: "" }, t("age band?")),
      ...["6-7", "8-9", "10-12", "13-15", "16+", "adult"].map((band) => el("option", { value: band }, t(band))),
    );
    select.value = pilot.ageBand || "";
    select.addEventListener("change", () =>
      api.parent("age", { pin: this.pin, profile: profile.id, ageBand: select.value }).catch(() => {}),
    );
    const checks = Object.entries(pilot.checks).map(([module, phases]) => {
      const part = (phase) => (phases[phase] ? `${phases[phase][0]}/${phases[phase][1]}` : "–");
      return el("li", {}, t("{module}: before {before}, after {after}", { module, before: part("before"), after: part("after") }));
    });
    return el(
      "div",
      { class: "pilot-part" },
      el("p", {}, t("Pilot id: {id}", { id: pilot.id }), " ", select),
      checks.length ? el("ul", {}, ...checks) : null,
    );
  }

  // a player's progress from a file: brought home from a class, or from another computer
  async importPlayer(file) {
    $("import-msg").textContent = "";
    try {
      const data = JSON.parse(await file.text());
      const profile = await api.parent("import", { pin: this.pin, data });
      $("import-msg").textContent = t("Welcome, {name}!", { name: displayName(profile) });
      this.renderReports();
    } catch (error) {
      $("import-msg").textContent = error instanceof SyntaxError ? t("This is not a CodeZoo profile file.") : error.message;
    }
  }

  async exportPlayer(profile) {
    const data = await api.parent("export", { pin: this.pin, profile: profile.id });
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const link = el("a", { href: URL.createObjectURL(blob), download: `codezoo-${profile.name}.json` });
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
  }

  async removePlayer(profile) {
    if (!window.confirm(t("Remove {name} and all their progress? This can't be undone.", profile))) return;
    await api.parent("remove", { pin: this.pin, profile: profile.id });
    if (this.current?.id === profile.id) {
      this.current = null;
      remember(null);
    }
    this.renderReports();
  }

  // --- goodbye ------------------------------------------------------------------------

  showGoodbye(pack) {
    const animal = pack?.animalName || "monkey";
    $("goodbye-text").textContent = t("The {animal} is tired and going to sleep. Great work today — see you tomorrow!", { animal });
    if (!this.goodbyeDialog.open) this.goodbyeDialog.showModal();
  }
}
