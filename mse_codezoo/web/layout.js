// Draggable splitters between the panes. Sizes are a per-browser convenience in localStorage.

const KEY = "codezoo.layout";

function load() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || {};
  } catch {
    return {};
  }
}

function save(sizes) {
  try {
    localStorage.setItem(KEY, JSON.stringify(sizes));
  } catch {
    // private window or storage blocked: sizes just aren't remembered
  }
}

// The window-tall layout (style.css, wider than a phone): the stage's drawing takes the
// room its pane has left after the goal, the tools and the call stack, so nothing needs
// scrolling. Elsewhere the drawing keeps its own height.
const FITTED = "(min-width: 801px) and (min-height: 520px)";
const MIN_STAGE = 160;

export function fitStage(panes) {
  const pane = panes.querySelector(".stage-pane");
  const stage = pane?.querySelector("#stage");
  if (!pane || !stage) return;
  if (!window.matchMedia(FITTED).matches) {
    pane.style.removeProperty("--stage-fit");
    return;
  }
  // Only the stage's own column counts: beside the stage, a long goal or result scrolls in
  // its own column and must not make the drawing smaller.
  const zoom = parseFloat(window.getComputedStyle(stage).getPropertyValue("--stage-zoom")) || 1;
  const bottomLine = () => {
    const box = pane.getBoundingClientRect();
    return box.top + pane.clientTop + pane.clientHeight - parseFloat(window.getComputedStyle(pane).paddingBottom);
  };
  const columnBottom = () => {
    let bottom = stage.getBoundingClientRect().bottom;
    for (const part of pane.children) {
      if (part === stage || part.matches(".stage-head, #split-head, .sr-only, #callstack") || !part.offsetParent) continue;
      const rect = part.getBoundingClientRect();
      bottom = Math.max(bottom, rect.bottom + parseFloat(window.getComputedStyle(part).marginBottom));
    }
    return bottom;
  };
  // the drawing gets what is free under its column (or gives back what overflows); two
  // rounds, because a different height can move what sits below it
  for (let round = 0; round < 2; round++) {
    const slack = bottomLine() - columnBottom() - 1;
    if (Math.abs(slack) < 1) break;
    // at a zoom of z the drawing is fit * z tall; the fit is its height at the zoom of 1
    const drawn = stage.getBoundingClientRect().height;
    const fit = Math.max(MIN_STAGE, Math.floor(drawn + slack - (zoom - 1) * (drawn / zoom)));
    pane.style.setProperty("--stage-fit", `${fit}px`);
  }
}

export function setupSplitters({ panes, stageSplit, paneSplit, headSplit, consoleSplit, onResize }) {
  const sizes = load();
  // the console pane (and its gap) to the right of the code takes room from the blocks
  const consoleWidth = () => {
    // only when it has its own column beside the code (not when it fills the blocks' place)
    const pane = panes.querySelector(".console-pane");
    const code = panes.querySelector(".code-pane");
    return pane && pane.offsetWidth && code?.offsetWidth ? pane.offsetWidth + 12 : 0;
  };
  const apply = () => {
    // a width saved in a wider window must not make the page wider than this one
    const room = document.documentElement.clientWidth - 32 - 12 - 220 - consoleWidth();
    if (sizes.left) panes.style.setProperty("--left", `${Math.max(220, Math.min(sizes.left, room))}px`);
    else panes.style.removeProperty("--left");
    // the console's width (the bar between the code and the console)
    if (sizes.console) {
      const most = Math.max(170, document.documentElement.clientWidth - 32 - 24 - 440);
      panes.style.setProperty("--console-w", `${Math.max(170, Math.min(sizes.console, most))}px`);
    } else panes.style.removeProperty("--console-w");
    if (sizes.stage) {
      // in the window-tall layout the panes below keep their 180px (the page never scrolls)
      const room = window.matchMedia(FITTED).matches ? panes.clientHeight - 12 - 28 - 180 : Infinity;
      panes.style.setProperty("--stage-h", `${Math.max(MIN_STAGE, Math.min(sizes.stage, room))}px`);
    }
    else panes.style.removeProperty("--stage-h");
    // the goal column beside the stage ("beside the stage" layout): its width
    const stagePane = panes.querySelector(".stage-pane");
    if (sizes.head && stagePane) {
      const most = Math.max(220, stagePane.clientWidth - 300);
      stagePane.style.setProperty("--head-w", `${Math.max(220, Math.min(sizes.head, most))}px`);
    } else stagePane?.style.removeProperty("--head-w");
    fitStage(panes);
    onResize();
  };

  function drag(splitter, update) {
    splitter.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      splitter.setPointerCapture(event.pointerId);
      splitter.classList.add("dragging");
      const move = (e) => {
        update(e);
        apply();
      };
      const up = () => {
        splitter.classList.remove("dragging");
        splitter.removeEventListener("pointermove", move);
        splitter.removeEventListener("pointerup", up);
        save(sizes);
      };
      splitter.addEventListener("pointermove", move);
      splitter.addEventListener("pointerup", up);
    });
  }

  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

  drag(paneSplit, (e) => {
    const box = panes.getBoundingClientRect();
    sizes.left = Math.round(clamp(e.clientX - box.left - 16, 220, box.width - 32 - 12 - 220 - consoleWidth()));
  });
  if (consoleSplit) {
    drag(consoleSplit, (e) => {
      const box = panes.getBoundingClientRect();
      sizes.console = Math.round(clamp(box.right - e.clientX - 16 - 6, 170, box.width - 32 - 24 - 440));
    });
  }
  if (headSplit) {
    drag(headSplit, (e) => {
      const box = panes.querySelector(".stage-pane").getBoundingClientRect();
      sizes.head = Math.round(clamp(box.right - e.clientX - 18, 220, box.width - 300));
    });
  }
  drag(stageSplit, (e) => {
    const box = panes.getBoundingClientRect();
    sizes.stage = Math.round(clamp(e.clientY - box.top - 12, 160, window.innerHeight * 0.8));
  });

  // keyboard: arrows move the splitter, Home resets it
  const keys = (splitter, axis) =>
    splitter.addEventListener("keydown", (e) => {
      const box = panes.getBoundingClientRect();
      const step = e.shiftKey ? 64 : 16;
      if (e.key === "Home") {
        delete sizes[axis];
      } else if (axis === "left" && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
        const current = sizes.left || (box.width - 44) / 2;
        sizes.left = clamp(current + (e.key === "ArrowLeft" ? -step : step), 220, box.width - 264 - consoleWidth());
      } else if (axis === "console" && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
        const current = sizes.console || panes.querySelector(".console-pane").getBoundingClientRect().width;
        sizes.console = clamp(current + (e.key === "ArrowLeft" ? step : -step), 170, box.width - 32 - 24 - 440);
      } else if (axis === "head" && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
        const pane = panes.querySelector(".stage-pane");
        const current = sizes.head || pane.querySelector(".stage-head").getBoundingClientRect().width;
        sizes.head = clamp(current + (e.key === "ArrowLeft" ? step : -step), 220, pane.clientWidth - 300);
      } else if (axis === "stage" && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
        const current = sizes.stage || panes.querySelector(".stage-pane").getBoundingClientRect().height;
        sizes.stage = clamp(current + (e.key === "ArrowUp" ? -step : step), 160, window.innerHeight * 0.8);
      } else {
        return;
      }
      e.preventDefault();
      apply();
      save(sizes);
    });
  keys(paneSplit, "left");
  keys(stageSplit, "stage");
  paneSplit.addEventListener("dblclick", () => { delete sizes.left; apply(); save(sizes); });
  stageSplit.addEventListener("dblclick", () => { delete sizes.stage; apply(); save(sizes); });
  if (consoleSplit) {
    keys(consoleSplit, "console");
    consoleSplit.addEventListener("dblclick", () => { delete sizes.console; apply(); save(sizes); });
  }
  if (headSplit) {
    keys(headSplit, "head");
    headSplit.addEventListener("dblclick", () => { delete sizes.head; apply(); save(sizes); });
  }

  window.addEventListener("resize", apply);
  // the stage pane changes size when the top bar wraps, the goal grows or a run shows the
  // call stack: the drawing follows (a frame later, so a drag doesn't measure twice)
  let pending = 0;
  const refit = () => {
    cancelAnimationFrame(pending);
    pending = requestAnimationFrame(() => {
      const before = panes.querySelector(".stage-pane")?.style.getPropertyValue("--stage-fit");
      fitStage(panes);
      if (panes.querySelector(".stage-pane")?.style.getPropertyValue("--stage-fit") !== before) onResize();
    });
  };
  if (window.ResizeObserver) {
    const watch = new ResizeObserver(refit);
    const pane = panes.querySelector(".stage-pane");
    if (pane) {
      watch.observe(pane);
      for (const part of pane.children) watch.observe(part);
    }
  }
  // "Everything back to normal size" (zoom.js): the bars go back to their places too
  window.addEventListener("codezoo-zoom-reset", () => {
    for (const key of Object.keys(sizes)) delete sizes[key];
    save(sizes);
    apply();
  });
  apply();
}

// --- which panes are shown (the Blocks / Python / Console toggles in the top bar) ----------

const PANES_KEY = "codezoo.panes";
const ORDER = ["blocks", "code", "console"];

// The bottom row is built from the panes that are shown, left to right, with a bar between
// two neighbours: the blocks' bar (its width, --left) or, between the code and the console,
// the console's bar (--console-w). With every pane hidden the stage takes the whole page.
// Cub mode always shows its two panes (blocks and code) and no toggles.
export function setupPaneToggles({ panes, buttons, stageSplit, paneSplit, consoleSplit, tabs }) {
  let shown = Object.fromEntries(ORDER.map((pane) => [pane, true]));
  // the panes a classroom's teacher allows (classroom.js); the rest are hidden, with their toggles
  let allowed = [...ORDER];
  try {
    const saved = JSON.parse(localStorage.getItem(PANES_KEY) || "{}");
    for (const pane of ORDER) if (saved[pane] === false) shown[pane] = false;
  } catch {
    // storage blocked: every pane shown
  }
  const cub = () => document.documentElement.dataset.cub === "true";
  // a single allowed pane is always shown (a child can't hide everything the class uses)
  const visible = () =>
    cub()
      ? ["blocks", "code"].filter((pane) => allowed.includes(pane) || allowed.length === ORDER.length)
      : ORDER.filter((pane) => allowed.includes(pane) && (shown[pane] || allowed.length === 1));

  const width = (pane, list) => {
    if (list.length === 1) return "minmax(0, 1fr)";
    if (pane === "blocks") return "minmax(220px, var(--left, 1fr))";
    if (pane === "code") return "minmax(220px, 1fr)";
    return list.includes("code") ? "var(--console-w, minmax(170px, 0.45fr))" : "minmax(170px, 1fr)";
  };

  const apply = () => {
    const list = visible();
    const columns = [];
    const row = [];
    list.forEach((pane, i) => {
      if (i) {
        columns.push("12px");
        row.push(list[i - 1] === "code" && pane === "console" ? "csplit" : "vsplit");
      }
      columns.push(width(pane, list));
      row.push(pane);
    });
    const count = Math.max(1, columns.length);
    const across = (name) => `"${Array(count).fill(name).join(" ")}"`;
    if (list.length) {
      panes.style.gridTemplateColumns = columns.join(" ");
      panes.style.gridTemplateAreas = `${across("stage")} ${across("hsplit")} "${row.join(" ")}"`;
      panes.style.removeProperty("grid-template-rows");
    } else {
      panes.style.gridTemplateColumns = "minmax(0, 1fr)";
      panes.style.gridTemplateAreas = '"stage"';
      panes.style.gridTemplateRows = "minmax(0, 1fr)";
    }
    stageSplit.classList.toggle("pane-off", !list.length);
    paneSplit.classList.toggle("pane-off", !row.includes("vsplit"));
    consoleSplit?.classList.toggle("pane-off", !row.includes("csplit"));
    for (const pane of ORDER) {
      const off = !list.includes(pane);
      panes.querySelector(`[data-pane="${pane}"]`)?.classList.toggle("pane-off", off);
      tabs?.querySelector(`[data-tab="${pane}"]`)?.classList.toggle("pane-off", off);
    }
    // a phone showing a pane that was just hidden goes back to the stage
    const active = tabs?.querySelector("button.active");
    if (active?.classList.contains("pane-off")) tabs.querySelector('[data-tab="stage"]')?.click();
    for (const button of buttons) {
      button.setAttribute("aria-pressed", String(list.includes(button.dataset.show)));
      button.classList.toggle("pane-off", !allowed.includes(button.dataset.show) || allowed.length === 1);
    }
    buttons[0]?.parentElement?.classList.toggle("pane-off", allowed.length === 1);
    // the splitters, the stage's drawing and the blocks measure again
    window.dispatchEvent(new Event("resize"));
  };

  for (const button of buttons) {
    button.addEventListener("click", () => {
      shown = { ...shown, [button.dataset.show]: !shown[button.dataset.show] };
      try {
        localStorage.setItem(PANES_KEY, JSON.stringify(shown));
      } catch {
        // storage blocked: the choice lasts until the page is closed
      }
      apply();
    });
  }
  // Cub mode switches on and off with the player: its own two panes
  new MutationObserver(apply).observe(document.documentElement, { attributes: true, attributeFilter: ["data-cub"] });
  apply();
  return {
    setAllowed(list) {
      const next = ORDER.filter((pane) => list?.includes(pane));
      allowed = next.length ? next : [...ORDER];
      apply();
    },
  };
}
