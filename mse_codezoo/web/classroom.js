// The child's side of a classroom hub (`codezoo class serve`, phase 5): join with the class
// code and a picture, the teacher's "eyes on me" pause, the levels the teacher picked, and
// programs and levels classmates shared (shown once the teacher approves them).
// Everything stays on the teacher's computer, on the local network.

import { api, getClassCode, setClassCode } from "./api.js";
import { displayName, FACES } from "./players.js";
import { t } from "./i18n.js";
import { encodeShare } from "./share.js";

const $ = (id) => document.getElementById(id);
const POLL_MS = 4000;

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

function download(name, text) {
  const link = el("a", { href: URL.createObjectURL(new Blob([text], { type: "application/json" })), download: name });
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
}

export class Classroom {
  constructor({ players, onLevelsChanged, onPause, onPlayProgram, onPlayLevel, onViews, onSounds, onThemes, onPanes, onLang }) {
    this.players = players;
    this.onLang = onLang; // the language the teacher set for the class or this child changed
    this.onThemes = onThemes; // colours the teacher allows: ["light", "dark"], or just one
    this.onPanes = onPanes; // the panes the teacher allows: ["blocks", "code", "console"] or fewer
    this.onSounds = onSounds; // sounds the teacher allows: ["on", "off"], or just one
    this.onViews = onViews; // the stage views the teacher allows: ["2d", "3d"], or just one
    this.onLevelsChanged = onLevelsChanged;
    this.onPause = onPause;
    this.onPlayProgram = onPlayProgram;
    this.onPlayLevel = onPlayLevel;
    this.state = null;
    this.joined = null; // the answer to /api/class/join
    this.picture = null;
    this.seenShares = 0;
    this.ready = new Promise((resolve) => (this.markReady = resolve)); // the code was right

    $("join-form").addEventListener("submit", (event) => {
      event.preventDefault();
      this.join($("join-code").value);
    });
    $("join-new").addEventListener("submit", (event) => {
      event.preventDefault();
      this.createPlayer();
    });
    $("join-import").addEventListener("change", (event) => {
      if (event.target.files[0]) this.importPlayer(event.target.files[0]);
      event.target.value = "";
    });
    $("join-dialog").addEventListener("cancel", (event) => {
      if (!this.players.current) event.preventDefault(); // a player has to be picked first
    });
    $("pause-dialog").addEventListener("cancel", (event) => event.preventDefault());
    $("ended-dialog").addEventListener("cancel", (event) => event.preventDefault());
    $("class-button").addEventListener("click", () => this.openClass());
    $("class-close").addEventListener("click", () => $("class-dialog").close());
    $("class-switch").addEventListener("click", () => {
      $("class-dialog").close();
      this.choose();
    });
    $("class-export").addEventListener("click", () => this.exportMine());
  }

  // --- joining ---------------------------------------------------------------------

  async start(info) {
    $("class-button").hidden = false;
    $("class-name").textContent = info.hub.name;
    $("class-name").hidden = false;
    const params = new URLSearchParams(location.search);
    const fromLink = params.get("class");
    if (fromLink) {
      // scanned from the teacher's screen: keep the code, but not in the address bar
      params.delete("class");
      const rest = params.toString();
      history.replaceState(null, "", `${location.pathname}${rest ? `?${rest}` : ""}${location.hash}`);
    }
    const code = fromLink || getClassCode();
    if (!(code && (await this.join(code, { quiet: true, auto: true })))) this.showJoin();
    await this.ready; // the levels and players need the class code
    setInterval(() => this.poll(), POLL_MS);
  }

  showJoin(message = "") {
    $("join-form").hidden = false;
    $("join-pick").hidden = true;
    $("join-error").textContent = message;
    $("join-code").value = "";
    if (!$("join-dialog").open) $("join-dialog").showModal();
    $("join-code").focus();
  }

  async join(code, { quiet = false, auto = false } = {}) {
    try {
      this.joined = await api.joinClass(code);
    } catch (error) {
      if (quiet) return false;
      $("join-error").textContent = error.message;
      return false;
    }
    setClassCode(this.joined.code);
    this.markReady();
    const remembered = this.players.rememberedId();
    const known = this.joined.players.find((p) => p.id === remembered);
    if (auto && known) {
      if ($("join-dialog").open) $("join-dialog").close();
      this.players.select(known);
    } else {
      this.renderPick();
    }
    return true;
  }

  async choose() {
    try {
      this.joined = await api.joinClass(getClassCode());
      this.renderPick();
    } catch {
      this.showJoin();
    }
  }

  renderPick() {
    const data = this.joined;
    $("join-form").hidden = true;
    $("join-pick").hidden = false;
    $("join-error").textContent = "";
    $("join-class-name").textContent = data.class.name;
    $("join-players").replaceChildren(
      ...data.players.map((p) =>
        el(
          "button",
          { type: "button", class: "picture-tile", onclick: () => this.pick(p) },
          el("span", { class: "face", "aria-hidden": "true" }, FACES[p.picture] || "🐾"),
          el("span", { class: "name" }, displayName(p)),
        ),
      ),
    );
    $("join-players-note").hidden = !data.players.length;
    const open = !data.class.roster;
    $("join-new").hidden = !open;
    $("join-roster-note").hidden = open;
    $("join-name-row").hidden = !data.class.names;
    $("join-name").value = "";
    // every picture can be picked, even one a classmate has (the name tells them apart);
    // the first one nobody has yet is picked to start with
    const used = new Set(data.players.map((p) => p.picture));
    this.picture = data.pictures.find((picture) => !used.has(picture)) || data.pictures[0];
    const buttons = data.pictures.map((picture) => {
      const button = el(
        "button",
        { type: "button", class: "picture-tile", role: "radio", "aria-label": displayName({ name: picture, picture }),
          "aria-checked": String(picture === this.picture) },
        el("span", { class: "face", "aria-hidden": "true" }, FACES[picture] || "🐾"),
      );
      button.addEventListener("click", () => {
        this.picture = picture;
        for (const other of buttons) other.setAttribute("aria-checked", String(other === button));
      });
      return button;
    });
    $("join-pictures").replaceChildren(...buttons);
    if (!$("join-dialog").open) $("join-dialog").showModal();
  }

  pick(profile) {
    $("join-dialog").close();
    this.players.select(profile);
  }

  async createPlayer() {
    if (!this.picture) {
      $("join-error").textContent = t("Pick a picture first.");
      return;
    }
    try {
      const profile = await api.classMe(this.picture, $("join-name").value);
      this.pick(profile);
    } catch (error) {
      $("join-error").textContent = error.message;
      // e.g. a classmate already typed that name: the message says so, the form stays
    }
  }

  async importPlayer(file) {
    try {
      const data = JSON.parse(await file.text());
      this.pick(await api.classImport(data));
    } catch (error) {
      $("join-error").textContent = error instanceof SyntaxError ? t("This is not a CodeZoo profile file.") : error.message;
    }
  }

  // --- the teacher's controls ------------------------------------------------------------

  async poll() {
    let state;
    try {
      state = await api.classState(this.players.current?.id);
    } catch (error) {
      if (error.status === 410) this.showEnded();
      else if (error.status === 403 && !$("join-dialog").open) this.showJoin(t("The class has a new code. Look at the teacher's screen."));
      return;
    }
    const before = this.state;
    this.state = state;
    if (state.paused !== Boolean(before?.paused)) {
      if (state.paused) {
        this.onPause();
        // before the first start the teacher is still setting up the lesson
        const ready = state.started === false;
        $("pause-dialog").querySelector(".goodbye-animal").textContent = ready ? "⏳" : "👀";
        $("pause-title").textContent = ready ? t("Getting ready…") : t("Eyes on the teacher!");
        $("pause-text").textContent = ready
          ? t("The teacher is getting the lesson ready. It starts in a moment.")
          : t("The teacher paused the class for a moment. Your program is safe.");
        if (!$("pause-dialog").open) $("pause-dialog").showModal();
      } else if ($("pause-dialog").open) {
        $("pause-dialog").close();
      }
    }
    if (state.views && state.views.join() !== before?.views?.join()) this.onViews?.(state.views);
    if (state.sounds && state.sounds.join() !== before?.sounds?.join()) this.onSounds?.(state.sounds);
    if (state.themes && state.themes.join() !== before?.themes?.join()) this.onThemes?.(state.themes);
    if (state.panes && state.panes.join() !== before?.panes?.join()) this.onPanes?.(state.panes);
    // when the player is picked, or the teacher changes it; a child who switched language
    // in between keeps their choice
    if ("lang" in state) {
      const key = `${this.players.current?.id}:${state.lang}`;
      if (key !== this.langKey) {
        this.langKey = key;
        this.onLang?.(state.lang);
      }
    }
    const levelsChanged =
      before && (before.locked !== state.locked || before.assigned.join() !== state.assigned.join());
    if (levelsChanged) this.onLevelsChanged();
    const fresh = state.shares - this.seenShares;
    $("class-badge").textContent = fresh > 0 ? String(fresh) : "";
    $("class-badge").hidden = fresh <= 0;
  }

  showEnded() {
    for (const dialog of document.querySelectorAll("dialog[open]")) dialog.close();
    setClassCode(null);
    if (!$("ended-dialog").open) $("ended-dialog").showModal();
  }

  // --- sharing ------------------------------------------------------------------------

  async shareProgram(level, source, animal) {
    const player = this.players.current;
    if (!player) return t("Pick your picture first, then share.");
    try {
      await api.share(player.id, "program", level.title, { level: level.id, source, animal });
      return t("Sent! Your program shows up for the class once the teacher says yes.");
    } catch (error) {
      return error.message;
    }
  }

  async openClass() {
    let shares = [];
    try {
      ({ shares } = await api.classShares());
    } catch (error) {
      $("gallery").replaceChildren(el("p", { class: "error" }, error.message));
    }
    this.seenShares = shares.length;
    $("class-badge").hidden = true;
    $("gallery").replaceChildren(
      ...(shares.length
        ? shares.map((share) => this.galleryCard(share))
        : [el("p", { class: "note" }, t("Nothing shared yet. After a run, press “Share with the class”."))]),
    );
    $("class-export").disabled = !this.players.current;
    $("class-error").textContent = "";
    $("class-dialog").showModal();
  }

  galleryCard(share) {
    const play = el("button", { type: "button", class: "small primary" }, t("▶ Try it"));
    play.addEventListener("click", () => {
      $("class-dialog").close();
      if (share.kind === "program") this.onPlayProgram(share.payload);
      else if (share.kind === "game") location.href = `game.html#play=${encodeShare(share.payload)}`;
      else this.onPlayLevel(share.payload.level);
    });
    const report = el("button", { type: "button", class: "small" }, t("🚩 Tell the teacher"));
    report.addEventListener("click", async () => {
      if (!window.confirm(t("Hide this for everyone until the teacher looks at it?"))) return;
      try {
        await api.reportShare(share.id);
        card.remove();
      } catch (error) {
        $("class-error").textContent = error.message;
      }
    });
    const card = el(
      "div",
      { class: "share-card" },
      el("span", { class: "face", "aria-hidden": "true" }, FACES[share.picture] || "🐾"),
      el(
        "div",
        { class: "share-text" },
        el("strong", {}, share.title),
        el("span", { class: "note" }, `${displayName(share)} · ${t({ level: "a level", game: "a game" }[share.kind] || "a program")}`),
      ),
      el("div", { class: "share-actions" }, play, report),
    );
    return card;
  }

  async exportMine() {
    const player = this.players.current;
    if (!player) return;
    try {
      const data = await api.classExport(player.id);
      download(`codezoo-${displayName(player)}.json`, JSON.stringify(data, null, 2));
    } catch (error) {
      $("class-error").textContent = error.message;
    }
  }
}
