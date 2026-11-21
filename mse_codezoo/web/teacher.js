// The teacher's screen of a classroom hub (`codezoo class serve`, phase 5): the class code
// and QR code, who joined and how far they got, who is stuck, today's levels, the "eyes on
// me" pause, shares to approve, the class's own levels and a class report.
// The teacher's key comes in the address (#key=...) printed in the terminal.

import { api, setTeacherKey } from "./api.js";
import { LANGS, concept, initialLang, lang, setLang, t, translatePage } from "./i18n.js";
import { displayName, FACES } from "./players.js";

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

function render() {
  const info = data.class;
  $("t-class").textContent = `${info.name} · ${t(info.type === "workshop" ? "workshop" : "class")}`;
  document.title = `${info.name} · CodeZoo`;
  $("t-qr").innerHTML = data.qr; // made by the engine's own QR encoder (mse_codezoo/qr.py)
  $("t-url").textContent = data.joinUrl.split("?")[0];
  $("t-code").textContent = data.code;
  $("t-pause").textContent = data.paused ? t("▶ Let everyone play again") : t("⏸ Pause everyone");
  $("t-pause").classList.toggle("paused", data.paused);
  $("t-end").textContent = info.settings.deleteAtEnd ? t("End the workshop and delete its data") : t("End the class");
  // redraw a part only when its data changed: a click must never land on a button
  // that a refresh is just replacing
  changed("players", [data.players, data.pictures, lang()]) && renderPlayers();
  changed("shares", [data.shares, lang()]) && renderShares();
  changed("own", [data.levels, lang()]) && renderOwn();
  changed("report", [data.concepts, data.mistakes, data.levelStats, lang()]) && renderReport();
  if (!levelsDrawn) renderLevels();
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
      el(
        "td",
        { class: "t-actions" },
        el("button", { type: "button", class: "small", onclick: () => openReport(p) }, t("Report")),
        el("button", { type: "button", class: "small", onclick: () => renamePlayer(p) }, t("Rename")),
        el("button", { type: "button", class: "small", onclick: () => exportPlayer(p) }, t("Save to a file")),
        el("button", { type: "button", class: "small", onclick: () => removePlayer(p) }, t("Remove")),
      ),
    );
  });
  $("t-players").replaceChildren(
    el("thead", {}, head),
    el("tbody", {}, ...(rows.length ? rows : [el("tr", {}, el("td", { colspan: "7" }, t("Nobody has joined yet.")))])),
  );
  const used = new Set(data.players.map((p) => p.picture));
  const select = $("t-add-picture");
  const keep = select.value;
  select.replaceChildren(
    ...data.pictures
      .filter((picture) => !used.has(picture))
      .map((picture) => el("option", { value: picture }, `${face(picture)} ${displayName({ name: picture, picture })}`)),
  );
  if ([...select.options].some((o) => o.value === keep)) select.value = keep;
}

function renderLevels() {
  levelsDrawn = true;
  const assigned = new Set(data.class.settings.assigned);
  $("t-locked").checked = data.class.settings.locked;
  $("t-modules").replaceChildren(
    ...data.modules.map((module) => {
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
        for (const box of details.querySelectorAll("input")) box.checked = true;
      });
      const details = el(
        "details",
        count ? { open: "" } : {},
        el("summary", {}, `${module.name}${count ? ` (${count})` : ""}`),
        all,
        el("div", { class: "t-level-boxes" }, ...boxes),
      );
      return details;
    }),
  );
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
    el(
      "div",
      { class: "share-text" },
      el("strong", {}, share.title),
      el("span", { class: "hint" }, `${displayName(share)} · ${t(share.kind === "level" ? "a level" : "a program")} · ${t(STATUS[share.status])}`),
    ),
    el("div", { class: "share-actions" }, ...buttons),
  );
}

function renderOwn() {
  $("t-own").replaceChildren(
    ...(data.levels.length
      ? data.levels.map((level) =>
          el(
            "li",
            {},
            `${level.id} · ${level.title} `,
            el("button", { type: "button", class: "small", onclick: () => act("level/remove", { id: level.id }) }, t("Remove")),
          ),
        )
      : [el("li", { class: "hint" }, t("None yet. Make one in the level editor, then add it here."))]),
  );
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
    share.kind === "program" ? share.payload.source : JSON.stringify(share.payload.level.world, null, 2);
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
  return [...document.querySelectorAll("#t-modules input:checked")].map((box) => box.value);
}

// --- wiring ---------------------------------------------------------------------------

$("t-pause").addEventListener("click", () => act("pause", { paused: !data.paused }));
$("t-newcode").addEventListener("click", () => act("code", {}));
$("t-end").addEventListener("click", endClass);
$("t-add").addEventListener("submit", async (event) => {
  event.preventDefault();
  const result = await act("player", { name: $("t-add-name").value, picture: $("t-add-picture").value });
  if (result) $("t-add-name").value = "";
});
$("t-save-levels").addEventListener("click", async () => {
  const result = await act("settings", { assigned: savedLevels(), locked: $("t-locked").checked });
  if (result) {
    $("t-levels-msg").textContent = t("Saved. Players see the new list in a few seconds.");
    levelsDrawn = false;
    await refresh();
  }
});
$("t-clear-levels").addEventListener("click", () => {
  for (const box of document.querySelectorAll("#t-modules input")) box.checked = false;
});
$("t-save-settings").addEventListener("click", async () => {
  const result = await act("settings", {
    roster: $("t-roster").checked,
    names: $("t-names").checked,
    deleteAtEnd: $("t-delete").checked,
  });
  if (result) $("t-settings-msg").textContent = t("Saved.");
});
$("t-export").addEventListener("click", () =>
  act("export", {}, (file) => download(`codezoo-class-${safeName(data.class.name)}.json`, file)),
);
$("t-level-files").addEventListener("change", (event) => {
  addLevelFiles(event.target.files);
  event.target.value = "";
});
$("t-projector-close").addEventListener("click", () => $("t-projector").close());
$("t-report-close").addEventListener("click", () => $("t-report-dialog").close());
$("lang").addEventListener("change", (event) => {
  setLang(event.target.value);
  translatePage();
  levelsDrawn = false;
  refresh();
});

function hasKey() {
  try {
    return Boolean(localStorage.getItem("codezoo.teacher"));
  } catch {
    return false;
  }
}

function start() {
  setLang(initialLang());
  translatePage();
  $("lang").replaceChildren(...Object.entries(LANGS).map(([code, name]) => el("option", { value: code }, name)));
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
