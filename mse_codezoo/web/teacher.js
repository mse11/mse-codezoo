// The teacher's screen of a classroom hub (`codezoo class serve`, phase 5): the class code
// and QR code, who joined and how far they got, who is stuck, today's levels, the "eyes on
// me" pause, shares to approve, the class's own levels and a class report.
// The teacher's key comes in the address (#key=...) printed in the terminal.

import { api, setTeacherKey } from "./api.js";
import { describeGoal } from "./goals.js";
import { LANGS, concept, initialLang, lang, langLabel, setLang, t, translatePage } from "./i18n.js";
import { openLook, setupThemeButton } from "./look.js";
import { displayName, FACES } from "./players.js";
import { encodeShare } from "./share.js";

// a shared game opens on the game page of this computer, ready for the projector
const gameLink = (payload) => `game.html#play=${encodeShare(payload)}`;

const $ = (id) => document.getElementById(id);
const POLL_MS = 5000;
const LIBRARY_KEY = "codezoo.my-levels"; // the level editor's "My levels" in this browser

let data = null; // the last /api/teacher/overview
let levelsDrawn = false; // today's levels are drawn once, so ticks aren't lost while polling
let settingsDrawn = false; // the same for the settings checkboxes
const drawn = {}; // part of the page -> the data it was last drawn from

function changed(part, value) {
  const text = JSON.stringify(value);
  if (drawn[part] === text) return false;
  drawn[part] = text;
  return true;
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

function download(name, value) {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: "application/json" });
  const link = el("a", { href: URL.createObjectURL(blob), download: name });
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
}

function showError(error) {
  $("t-error").textContent = error ? error.message || String(error) : "";
}

async function act(route, body, after = refresh) {
  try {
    const result = await api.teacher(route, body);
    showError(null);
    await after(result);
    return result;
  } catch (error) {
    showError(error);
    return null;
  }
}

const face = (picture) => FACES[picture] || "🐾";
const safeName = (text) => String(text).replace(/[^\p{L}\p{N}_-]+/gu, "-");

// --- drawing --------------------------------------------------------------------------

// the game worlds children opened (Game mode, G3): a row each, with "Close"
function renderRooms() {
  const rooms = data.rooms || [];
  if (!rooms.length) {
    $("t-rooms").replaceChildren(el("p", { class: "hint" }, t("No game worlds are open.")));
    return;
  }
  const status = { lobby: t("waiting for players"), playing: t("playing"), ended: t("the end") };
  $("t-rooms").replaceChildren(
    el(
      "table",
      { class: "t-table" },
      el(
        "thead",
        {},
        el("tr", {}, ...[t("World"), t("Players"), t("Status"), t("Tick"), t("Score"), t("Minutes"), ""].map((h) => el("th", {}, h))),
      ),
      el(
        "tbody",
        {},
        ...rooms.map((room) => {
          const close = el("button", { type: "button", class: "small" }, t("Close"));
          close.addEventListener("click", () => act("room/close", { room: room.id }));
          return el(
            "tr",
            {},
            el("td", {}, room.title),
            el("td", {}, room.players.map((p) => p.name).join(", ") || "—"),
            el("td", {}, status[room.status] || room.status),
            el("td", {}, String(room.tick)),
            el("td", {}, String(room.score)),
            el("td", {}, String(room.minutes)),
            el("td", {}, close),
          );
        }),
      ),
    ),
  );
}

function render() {
  const info = data.class;
  $("t-class").textContent = `${info.name} · ${t(info.type === "workshop" ? "workshop" : "class")}`;
  document.title = `${info.name} · CodeZoo`;
  $("t-qr").innerHTML = data.qr; // made by the engine's own QR encoder (mse_codezoo/qr.py)
  $("t-url").textContent = data.joinUrl.split("?")[0];
  $("t-code").textContent = data.code;
  $("t-link").textContent = data.joinUrl; // the QR code's link: opens the class with the code filled in
  $("t-link").href = data.joinUrl;
  // the hub starts paused: the teacher sets up the lesson, then starts it
  $("t-pause").textContent = !data.started
    ? t("▶ Start the lesson")
    : data.paused
      ? t("▶ Let everyone play again")
      : t("⏸ Pause everyone");
  // red stops the class, green lets it play
  $("t-pause").classList.toggle("stop", !data.paused);
  pauseButtonState();
  $("t-waiting").hidden = data.started;
  $("t-end").textContent = info.settings.deleteAtEnd ? t("End the workshop and delete its data") : t("End the class");
  // redraw a part only when its data changed: a click must never land on a button
  // that a refresh is just replacing
  changed("players", [data.players, data.pictures, data.pilot, lang()]) && renderPlayers();
  changed("shares", [data.shares, lang()]) && renderShares();
  changed("rooms", [data.rooms, lang()]) && renderRooms();
  changed("own", [data.levels, lang()]) && renderOwn();
  changed("report", [data.concepts, data.mistakes, data.levelStats, lang()]) && renderReport();
  if (!levelsDrawn) renderLevels();
  levelsEditable();
  needsPause();
  if (!settingsDrawn) renderSettings();
}

function renderPlayers() {
  const head = el(
    "tr",
    {},
    el("th", {}, t("Player")),
    el("th", {}, "★"),
    el("th", {}, t("Solved")),
    el("th", {}, t("Modules")),
    el("th", {}, t("Stuck on")),
    el("th", {}, t("Minutes today")),
    el("th", {}, t("Cub mode")),
    el("th", {}, t("Stage and language")),
    data.pilot ? el("th", {}, t("Age band")) : null,
    el("th", {}, ""),
  );
  const rows = data.players.map((p) => {
    const modules = Object.entries(p.modules).map(([id, m]) => {
      const name = data.modules.find((mod) => mod.id === id)?.name || id;
      return el(
        "span",
        { class: "t-module", title: t("{name}: {solved} of {levels} levels", { name, ...m }) },
        el("span", { class: "t-bar" }, el("span", { style: `width:${Math.round((100 * m.solved) / m.levels)}%` })),
        name,
      );
    });
    const stuck = p.stuck.map((s) => el("span", { class: "t-stuck", title: t("{n} tries", { n: s.fails }) }, s.title));
    return el(
      "tr",
      { class: p.stuck.length ? "is-stuck" : "" },
      el("td", {}, el("span", { class: "t-face" }, face(p.picture)), " ", displayName(p)),
      el("td", {}, String(p.stars)),
      el("td", {}, String(p.solved)),
      el("td", { class: "t-modules-cell" }, ...modules),
      el("td", {}, ...(stuck.length ? stuck : ["–"])),
      el("td", {}, String(p.minutesToday)),
      el("td", {}, cubBox(p)),
      el("td", { class: "t-own" }, ownSettings(p)),
      data.pilot ? el("td", {}, ageSelect(p)) : null,
      el(
        "td",
        { class: "t-actions" },
        el("button", { type: "button", class: "small", onclick: () => openReport(p) }, t("Report")),
        el("button", { type: "button", class: "small", onclick: () => renamePlayer(p) }, t("Rename")),
        el("button", { type: "button", class: "small", onclick: () => exportPlayer(p) }, t("Save to a file")),
        el("button", { type: "button", class: "small", "data-needs-pause": "", onclick: () => removePlayer(p) }, t("Remove")),
      ),
    );
  });
  $("t-players").replaceChildren(
    el("thead", {}, head),
    el("tbody", {}, ...(rows.length ? rows : [el("tr", {}, el("td", { colspan: "9" }, t("Nobody has joined yet.")))])),
  );
  const select = $("t-add-picture");
  const keep = select.value;
  select.replaceChildren(
    ...data.pictures
      .map((picture) => el("option", { value: picture }, `${face(picture)} ${displayName({ name: picture, picture })}`)),
  );
  if ([...select.options].some((o) => o.value === keep)) select.value = keep;
}

// Cub mode (ages 6-8, phase 7) per child: picture blocks, read aloud, the cub levels
function cubBox(player) {
  const box = el("input", { type: "checkbox", "data-needs-pause": "", "aria-label": t("Cub mode for {name}", { name: displayName(player) }), ...(player.cub ? { checked: "" } : {}) });
  box.addEventListener("change", () => act("player/cub", { profile: player.id, on: box.checked }));
  return box;
}

// This child's own stage view and language, over the class's settings ("as the class")
function ownSettings(player) {
  const own = player.own || {};
  const views = el(
    "select",
    { "aria-label": t("Stage for {name}", { name: displayName(player) }) },
    el("option", { value: "class" }, t("Stage as the class")),
    el("option", { value: "2d" }, "2D"),
    el("option", { value: "3d" }, "3D"),
    el("option", { value: "both" }, t("2D and 3D")),
  );
  views.value = !own.views ? "class" : own.views.length === 2 ? "both" : own.views[0];
  views.addEventListener("change", () => act("player/settings", { profile: player.id, views: views.value }));
  const language = el(
    "select",
    { "aria-label": t("Language for {name}", { name: displayName(player) }) },
    el("option", { value: "class" }, t("Language as the class")),
    el("option", { value: "device" }, `🌐 ${t("Each device's own language")}`),
    ...Object.keys(LANGS).map((code) => el("option", { value: code }, langLabel(code))),
  );
  language.value = !("lang" in own) ? "class" : own.lang === null ? "device" : own.lang;
  language.addEventListener("change", () => act("player/settings", { profile: player.id, lang: language.value }));
  for (const box of [views, language]) box.classList.toggle("t-own-set", box.value !== "class");
  return el("div", { class: "t-own-settings" }, views, language);
}

function ageSelect(player) {
  const select = el(
    "select",
    { "aria-label": t("Age band") },
    el("option", { value: "" }, t("age band?")),
    ...data.ageBands.map((band) => el("option", { value: band }, t(band))),
  );
  select.value = player.ageBand || "";
  select.addEventListener("change", () => act("player/age", { profile: player.id, ageBand: select.value }));
  return select;
}

function renderLevels() {
  levelsDrawn = true;
  const assigned = new Set(data.class.settings.assigned);
  $("t-locked").checked = data.class.settings.locked;
  const drawn = data.modules.map((module) => {
      const boxes = module.levels.map((level) =>
        el(
          "label",
          { class: "check" },
          el("input", { type: "checkbox", value: level.id, ...(assigned.has(level.id) ? { checked: "" } : {}) }),
          ` ${level.id} · ${level.title}`,
        ),
      );
      const count = module.levels.filter((l) => assigned.has(l.id)).length;
      const all = el("button", { type: "button", class: "small" }, t("Tick all"));
      all.addEventListener("click", () => {
        // only the levels the filter shows
        for (const label of details.querySelectorAll(".t-level-boxes label:not([hidden])")) label.querySelector("input").checked = true;
        levelsTicked();
      });
      const details = el(
        "details",
        { "data-module": module.id, "data-name": module.name, ...(count ? { open: "" } : {}) },
        el("summary", {}, el("span", {}, module.name), " ", el("span", { class: "t-count" })),
        all,
        el("div", { class: "t-level-boxes" }, ...boxes),
      );
      return details;
  });
  // the built-in modules, then the class's own levels in their own part of the card
  $("t-modules").replaceChildren(...drawn.filter((details) => details.dataset.module !== "mine"));
  const own = drawn.filter((details) => details.dataset.module === "mine");
  for (const details of own) details.open = true;
  $("t-modules-own").replaceChildren(...own);
  if (!own.length) $("t-modules-own").replaceChildren(el("p", { class: "hint" }, t("None yet. Make one in the level editor, then add it here.")));
  levelsTicked();
  filterLevels();
}

// Do the ticks (or "Only these levels") differ from what the children get?
function levelsUnsaved() {
  if (!levelsDrawn) return false;
  const saved = new Set(data.class.settings.assigned);
  const ticked = savedLevels();
  return (
    ticked.length !== saved.size ||
    ticked.some((id) => !saved.has(id)) ||
    $("t-locked").checked !== Boolean(data.class.settings.locked)
  );
}

// What is ticked right now (saved or not): a count per module and one line for all of them.
function levelsTicked() {
  const saved = new Set(data.class.settings.assigned);
  const ticked = savedLevels();
  const parts = [];
  for (const details of document.querySelectorAll(".t-modules details")) {
    const boxes = [...details.querySelectorAll("input")];
    const on = boxes.filter((box) => box.checked).length;
    const count = details.querySelector(".t-count");
    count.textContent = on ? `${on} / ${boxes.length}` : "";
    count.classList.toggle("on", on > 0);
    if (on) parts.push(`${details.dataset.name} ${on}`);
  }
  const changed = levelsUnsaved();
  let text = ticked.length
    ? t("Ticked: {n} ({list})", { n: ticked.length, list: parts.join(", ") })
    : t("Nothing ticked: children can play every level.");
  if (changed) text += ` ${t("Not saved yet.")}`;
  $("t-picked").textContent = text;
  $("t-picked").classList.toggle("unsaved", changed);
  $("t-save-levels").classList.toggle("attention", changed); // children see only what is saved
  $("t-discard-levels").hidden = !changed;
  pauseButtonState();
  if ($("t-only-picked").checked) filterLevels();
}

// letters without accents and case, so "kroky" finds "Kroky" and "otocky" finds "otočky"
const plain = (text) => text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();

// The search box and "Only ticked": hide what doesn't match, open the modules that do.
function filterLevels() {
  const words = plain($("t-level-filter").value.trim());
  const onlyTicked = $("t-only-picked").checked;
  const filtering = Boolean(words) || onlyTicked;
  for (const details of document.querySelectorAll(".t-modules details")) {
    const moduleHit = words && plain(details.dataset.name).includes(words);
    let shown = 0;
    for (const label of details.querySelectorAll(".t-level-boxes label")) {
      const box = label.querySelector("input");
      const hit = (!words || moduleHit || plain(label.textContent).includes(words)) && (!onlyTicked || box.checked);
      label.hidden = !hit;
      shown += hit ? 1 : 0;
    }
    details.hidden = filtering && shown === 0;
    if (filtering && shown) details.open = true;
  }
}

function renderShares() {
  const order = { reported: 0, pending: 1, approved: 2, rejected: 3 };
  const shares = [...data.shares].sort((a, b) => order[a.status] - order[b.status]);
  $("t-shares").replaceChildren(
    ...(shares.length
      ? shares.map(shareCard)
      : [el("p", { class: "hint" }, t("Nothing shared yet. After a run, children can press “Share with the class”."))]),
  );
}

const KINDS = { level: "a level", program: "a program", game: "a game" };
const STATUS = { pending: "waiting for you", approved: "the class can see it", rejected: "not shown", reported: "a child asked you to look" };

function shareCard(share) {
  const buttons = [];
  if (share.status !== "approved") {
    buttons.push(el("button", { type: "button", class: "small primary", onclick: () => setShare(share, "approved") }, t("Yes, show the class")));
  }
  if (share.status === "pending" || share.status === "approved" || share.status === "reported") {
    buttons.push(el("button", { type: "button", class: "small", onclick: () => setShare(share, "rejected") }, t("Don't show")));
  }
  buttons.push(el("button", { type: "button", class: "small", onclick: () => project(share) }, t("On the projector")));
  if (share.kind === "level" && share.payload.solution) {
    buttons.push(el("button", { type: "button", class: "small", onclick: () => addLevel(share.payload.level, share.payload.solution) }, t("Add to our levels")));
  }
  buttons.push(el("button", { type: "button", class: "small", onclick: () => setShare(share, "deleted") }, t("Delete")));
  return el(
    "div",
    { class: `share-card status-${share.status}` },
    el("span", { class: "face", "aria-hidden": "true" }, face(share.picture)),
    shareText(share),
    el("div", { class: "share-actions" }, ...buttons),
  );
}

// The level behind a share, ready to describe: a program names a level by id, a shared
// level carries itself. Kept per level, so the 5-second refresh doesn't load it again.
const shareLevels = new Map();
function shareLevel(share) {
  const { level, animal } = share.payload || {};
  if (share.kind === "game") return Promise.resolve(null); // a game carries its own world
  const key = share.kind === "level" ? `share:${share.id}` : `${level}:${animal || ""}:${lang()}`;
  if (!shareLevels.has(key)) {
    const load = share.kind === "level" ? api.previewLevel(level, animal) : api.level(level, animal);
    shareLevels.set(key, load.catch(() => null));
  }
  return shareLevels.get(key);
}

// What was shared: the level (id, title and its goal) and the program itself, so the
// teacher knows what they are approving
function shareText(share) {
  const title = el("strong", {}, share.title);
  const goal = el("span", { class: "share-goal" });
  const box = el(
    "div",
    { class: "share-text" },
    title,
    goal,
    el("span", { class: "hint" }, `${displayName(share)} · ${t(KINDS[share.kind] || "a program")} · ${t(STATUS[share.status])}`),
  );
  if (share.kind === "game") {
    // what the child wants the game to be (the design card), so the teacher can say yes
    const { idea, win, lose } = share.payload?.design || {};
    goal.textContent = [idea, win && `🏆 ${win}`, lose && `💥 ${lose}`].filter(Boolean).join(" · ");
  }
  if ((share.kind === "program" || share.kind === "game") && share.payload?.source) {
    box.append(el("details", { class: "share-code" }, el("summary", {}, t("Show the program")), el("pre", {}, share.payload.source)));
  }
  shareLevel(share).then((level) => {
    if (!level) return;
    title.textContent = share.kind === "level" ? `${share.title} · ${level.title}` : `${level.id} · ${level.title}`;
    goal.textContent = `${describeGoal(level, level.goal)}.`;
  });
  return box;
}

function renderOwn() {
  $("t-own").replaceChildren(
    ...(data.levels.length
      ? data.levels.map((level) =>
          el(
            "li",
            {},
            `${level.id} · ${level.title} `,
            el("button", { type: "button", class: "small", "data-needs-pause": "", onclick: () => act("level/remove", { id: level.id }) }, t("Remove")),
          ),
        )
      : []),
  );
  if (!data.levels.length) document.querySelector(".t-own-manage").open = true; // show how to add one
  let library = {};
  try {
    library = JSON.parse(localStorage.getItem(LIBRARY_KEY) || "{}");
  } catch {
    library = {};
  }
  const entries = Object.values(library);
  $("t-library").replaceChildren(
    ...(entries.length
      ? entries.map(({ level, solution }) =>
          el(
            "li",
            {},
            `${level.id} · ${level.title || ""} `,
            el("button", { type: "button", class: "small", onclick: () => addLevel(level, solution) }, t("Add to the class")),
          ),
        )
      : [el("li", { class: "hint" }, t("No levels kept in this browser yet."))]),
  );
}

function renderReport() {
  $("t-concepts").replaceChildren(
    el("thead", {}, el("tr", {}, el("th", {}, t("Idea")), el("th", {}, t("met")), el("th", {}, t("practised")), el("th", {}, t("mastered")))),
    el(
      "tbody",
      {},
      ...(data.concepts.length
        ? data.concepts.map((row) =>
            el("tr", {}, el("td", {}, concept(row.concept)), el("td", {}, String(row.met)), el("td", {}, String(row.practised)), el("td", {}, String(row.mastered))),
          )
        : [el("tr", {}, el("td", { colspan: "4" }, t("Nothing played yet.")))]),
    ),
  );
  $("t-mistakes").textContent = data.mistakes.length
    ? t("Often in this class: {list}.", { list: data.mistakes.map((m) => `${m.text} (${m.count})`).join("; ") })
    : "";
  const stats = [...data.levelStats].sort((a, b) => b.tried - b.solved - (a.tried - a.solved));
  $("t-level-stats").replaceChildren(
    el("thead", {}, el("tr", {}, el("th", {}, t("Level")), el("th", {}, t("Tried")), el("th", {}, t("Solved")), el("th", {}, t("Not yet")))),
    el(
      "tbody",
      {},
      ...stats.map((row) =>
        el("tr", {}, el("td", {}, `${row.level} · ${row.title}`), el("td", {}, String(row.tried)), el("td", {}, String(row.solved)), el("td", {}, String(row.tried - row.solved))),
      ),
    ),
  );
}

function renderSettings() {
  settingsDrawn = true;
  const s = data.class.settings;
  $("t-roster").checked = s.roster;
  $("t-names").checked = s.names;
  $("t-delete").checked = s.deleteAtEnd;
  $("t-cub").checked = Boolean(s.cub);
  $("t-class-lang").value = data.class.lang || "";
  $("t-view-2d").checked = data.class.views.includes("2d");
  $("t-view-3d").checked = data.class.views.includes("3d");
  $("t-sound-on").checked = data.class.sounds.includes("on");
  $("t-sound-off").checked = data.class.sounds.includes("off");
  $("t-theme-light").checked = data.class.themes.includes("light");
  $("t-theme-dark").checked = data.class.themes.includes("dark");
  for (const pane of ["blocks", "code", "console"]) $(`t-pane-${pane}`).checked = (data.class.panes || ["blocks", "code", "console"]).includes(pane);
  $("t-pilot").checked = data.pilot;
  $("t-pilot-box").hidden = !data.pilot;
}

// --- actions --------------------------------------------------------------------------

async function refresh() {
  if (document.querySelector("dialog[open]")) return;
  try {
    data = await api.teacher("overview");
    showError(null);
    $("t-main").hidden = false;
    render();
  } catch (error) {
    showError(error);
    if (error.status === 410 || error.status === 403) $("t-main").hidden = true;
  }
}

async function setShare(share, status) {
  if (status === "deleted" && !window.confirm(t("Delete this share?"))) return;
  await act("share", { share: share.id, status });
}

function project(share) {
  $("t-projector-title").textContent = share.title;
  $("t-projector-who").textContent = displayName(share);
  $("t-projector-code").textContent =
    share.kind === "level" ? JSON.stringify(share.payload.level.world, null, 2) : share.payload.source;
  $("t-projector-play").hidden = share.kind !== "game";
  $("t-projector-play").onclick = () => window.open(gameLink(share.payload), "_blank");
  $("t-projector").showModal();
}

async function addLevel(level, solution) {
  const result = await act("level", { level, solution });
  if (!result) return;
  $("t-own-msg").replaceChildren(
    result.ok
      ? t("Added {id}. Tick it under “Today's levels” to give it to the class.", { id: level.id })
      : el("span", { class: "error" }, t("Not yet:"), " ", result.errors.join("; ")),
  );
  if (result.ok) levelsDrawn = false;
}

async function addLevelFiles(files) {
  const byName = Object.fromEntries([...files].map((f) => [f.name, f]));
  const jsons = [...files].filter((f) => f.name.endsWith(".json"));
  if (!jsons.length) {
    $("t-own-msg").replaceChildren(el("span", { class: "error" }, t("Pick the level's .json file and its .solution.py file together.")));
    return;
  }
  for (const file of jsons) {
    const solutionFile = byName[file.name.replace(/\.json$/, ".solution.py")] || [...files].find((f) => f.name.endsWith(".py"));
    try {
      const level = JSON.parse(await file.text());
      await addLevel(level, solutionFile ? await solutionFile.text() : null);
    } catch (error) {
      $("t-own-msg").replaceChildren(el("span", { class: "error" }, error.message));
    }
  }
}

async function openReport(player) {
  const report = await act("player/report", { profile: player.id }, () => {});
  if (!report) return;
  $("t-report-name").textContent = `${face(player.picture)} ${displayName(player)}`;
  $("t-report-body").replaceChildren(
    el("p", {}, t("{levels} levels solved · {stars} stars", { levels: report.levelsSolved, stars: report.stars })),
    el(
      "table",
      { class: "t-table" },
      el("thead", {}, el("tr", {}, el("th", {}, t("Idea")), el("th", {}, t("Status")), el("th", {}, t("Progress")))),
      el(
        "tbody",
        {},
        ...report.concepts
          .filter((row) => row.status !== "not yet")
          .map((row) =>
            el("tr", {}, el("td", {}, concept(row.concept)), el("td", { class: `status-${row.status}` }, t(row.status)), el("td", {}, t("{solved} of {levels} levels", row))),
          ),
      ),
    ),
    report.mistakes.length ? el("p", {}, t("Often: {list}.", { list: report.mistakes.map((m) => m.text).join("; ") })) : null,
  );
  $("t-report-dialog").showModal();
}

async function renamePlayer(player) {
  const name = window.prompt(t("New name for {name}:", { name: displayName(player) }), player.name === player.picture ? "" : player.name);
  if (name) await act("player/rename", { profile: player.id, name });
}

async function exportPlayer(player) {
  await act("player/export", { profile: player.id }, (file) => download(`codezoo-${safeName(displayName(player))}.json`, file));
}

async function removePlayer(player) {
  if (!window.confirm(t("Remove {name} and all their progress? This can't be undone.", { name: displayName(player) }))) return;
  await act("player/remove", { profile: player.id });
}

async function endClass() {
  const deletes = data.class.settings.deleteAtEnd;
  const question = deletes
    ? t("End the workshop? All its players and their progress are deleted from this computer. Save the class to a file first if you want to keep it.")
    : t("End the class? The code stops working; players and progress stay for next time.");
  if (!window.confirm(question)) return;
  const result = await act("end", {}, () => {});
  if (!result) return;
  if (result.deleted) {
    $("t-main").hidden = true;
    $("t-error").textContent = t("The workshop has ended and its data was deleted. You can close this page.");
  } else {
    await refresh();
  }
}

function savedLevels() {
  return [...document.querySelectorAll(".t-modules input:checked")].map((box) => box.value);
}

// --- wiring ---------------------------------------------------------------------------

// Taking something away from a child who may be using it (their player, a level, the class
// code, Cub mode mid-program) waits for a pause, like today's levels. Marked in the markup
// with data-needs-pause; drawn parts are refreshed, so this runs after every render.
function needsPause() {
  const playing = !data?.paused;
  for (const control of document.querySelectorAll("[data-needs-pause]")) {
    control.disabled = playing;
    control.title = playing ? t("Pause everyone first") : "";
  }
  for (const note of document.querySelectorAll(".t-needs-pause-note")) note.hidden = !playing;
}

// Today's levels change only while the class is paused: a child could be in the middle of a
// level that the new list takes away. Searching and opening modules still work while playing.
function levelsEditable() {
  const open = Boolean(data?.paused);
  const card = $("t-levels-title").closest("section");
  for (const control of card.querySelectorAll(".t-modules input, .t-modules button, #t-locked, #t-save-levels, #t-clear-levels, #t-discard-levels")) {
    control.disabled = !open;
  }
  $("t-levels-playing").hidden = open;
}

// Children may only be let in on a saved list: while today's levels have unsaved changes,
// "Start the lesson" / "Let everyone play again" waits for Save or Discard. Pausing always works.
function pauseButtonState() {
  const blocked = Boolean(data?.paused) && levelsUnsaved();
  $("t-pause").disabled = blocked;
  $("t-unsaved-note").hidden = !blocked;
}
$("t-pause").addEventListener("click", async () => {
  if (data.paused && levelsUnsaved()) return;
  await act("pause", { paused: !data.paused });
});
$("t-discard-levels").addEventListener("click", () => {
  levelsDrawn = false; // draw the saved list again
  render();
  $("t-levels-msg").textContent = t("Changes discarded.");
});
$("t-newcode").addEventListener("click", () => act("code", {}));
$("t-copy-link").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("t-link").href);
    $("t-copy-msg").textContent = t("Copied.");
  } catch {
    // no clipboard here: select the link so Ctrl+C copies it
    getSelection().selectAllChildren($("t-link"));
    $("t-copy-msg").textContent = t("Press Ctrl+C to copy.");
  }
  setTimeout(() => ($("t-copy-msg").textContent = ""), 3000);
});
$("t-end").addEventListener("click", endClass);
$("t-add").addEventListener("submit", async (event) => {
  event.preventDefault();
  const result = await act("player", { name: $("t-add-name").value, picture: $("t-add-picture").value });
  if (result) $("t-add-name").value = "";
});
async function saveLevels() {
  const result = await act("settings", { assigned: savedLevels(), locked: $("t-locked").checked });
  if (result) {
    $("t-levels-msg").textContent = t("Saved. Players see the new list in a few seconds.");
    levelsDrawn = false;
    await refresh();
  }
  return Boolean(result);
}
$("t-save-levels").addEventListener("click", saveLevels);
$("t-clear-levels").addEventListener("click", () => {
  for (const box of document.querySelectorAll(".t-modules input")) box.checked = false;
  levelsTicked();
});
$("t-modules").addEventListener("change", levelsTicked);
$("t-modules-own").addEventListener("change", levelsTicked);
$("t-locked").addEventListener("change", levelsTicked);
$("t-level-filter").addEventListener("input", filterLevels);
$("t-only-picked").addEventListener("change", filterLevels);
$("t-expand").addEventListener("click", () => {
  for (const details of document.querySelectorAll(".t-modules details:not([hidden])")) details.open = true;
});
$("t-collapse").addEventListener("click", () => {
  for (const details of document.querySelectorAll(".t-modules details")) details.open = false;
});
$("t-save-settings").addEventListener("click", async () => {
  const result = await act("settings", {
    roster: $("t-roster").checked,
    names: $("t-names").checked,
    deleteAtEnd: $("t-delete").checked,
    cub: $("t-cub").checked,
    lang: $("t-class-lang").value,
    views: ["2d", "3d"].filter((view) => $(`t-view-${view}`).checked),
    sounds: ["on", "off"].filter((sound) => $(`t-sound-${sound}`).checked),
    themes: ["light", "dark"].filter((theme) => $(`t-theme-${theme}`).checked),
    panes: ["blocks", "code", "console"].filter((pane) => $(`t-pane-${pane}`).checked),
    pilot: $("t-pilot").checked,
  });
  if (result) {
    $("t-settings-msg").textContent = t("Saved.");
    settingsDrawn = false;
    drawn.players = null; // the age band column follows the pilot switch
    render();
  }
});
$("t-export").addEventListener("click", () =>
  act("export", {}, (file) => download(`codezoo-class-${safeName(data.class.name)}.json`, file)),
);
let pilotFile = null;
$("t-pilot-export").addEventListener("click", async () => {
  const result = await act("pilot-export", {}, () => {});
  if (!result) return;
  pilotFile = result.file;
  $("t-pilot-contents").replaceChildren(...result.contents.map((line) => el("li", {}, line)));
  $("t-pilot-agree").checked = false;
  $("t-pilot-save").disabled = true;
  $("t-pilot-consent").hidden = false;
});
$("t-pilot-agree").addEventListener("change", (event) => ($("t-pilot-save").disabled = !event.target.checked));
$("t-pilot-save").addEventListener("click", () => {
  if (!pilotFile || !$("t-pilot-agree").checked) return;
  download(`codezoo-pilot-${safeName(data.class.name)}-${pilotFile.exported}.json`, pilotFile);
  $("t-pilot-consent").hidden = true;
});
$("t-level-files").addEventListener("change", (event) => {
  addLevelFiles(event.target.files);
  event.target.value = "";
});
$("look").addEventListener("click", openLook);
setupThemeButton($("theme"));
$("t-projector-close").addEventListener("click", () => $("t-projector").close());
$("t-report-close").addEventListener("click", () => $("t-report-dialog").close());
$("lang").addEventListener("change", (event) => {
  setLang(event.target.value);
  translatePage();
  fillClassLang();
  levelsDrawn = false;
  refresh();
});

// the class's language menu, in the teacher's language; keeps what is picked
function fillClassLang() {
  const keep = $("t-class-lang").value;
  $("t-class-lang").replaceChildren(
    el("option", { value: "" }, `🌐 ${t("Each device's own language")}`),
    ...Object.keys(LANGS).map((code) => el("option", { value: code }, langLabel(code))),
  );
  $("t-class-lang").value = keep;
}

function hasKey() {
  try {
    return Boolean(localStorage.getItem("codezoo.teacher"));
  } catch {
    return false;
  }
}

function start() {
  setLang(initialLang(), { save: false });
  translatePage();
  $("lang").replaceChildren(...Object.keys(LANGS).map((code) => el("option", { value: code }, langLabel(code))));
  fillClassLang();
  $("lang").value = lang();
  const key = new URLSearchParams(location.hash.slice(1)).get("key");
  if (key) {
    setTeacherKey(key);
    history.replaceState(null, "", location.pathname); // keep the key out of sight
  } else if (!hasKey()) {
    $("t-nokey").hidden = false;
    return;
  }
  refresh();
  setInterval(refresh, POLL_MS);
}

start();
