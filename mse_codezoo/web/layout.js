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

export function setupSplitters({ panes, stageSplit, paneSplit, headSplit, consoleSplit, onResize }) {
  const sizes = load();
  // the console pane (and its gap) to the right of the code takes room from the blocks
  const consoleWidth = () => {
    const pane = panes.querySelector(".console-pane");
    return pane && pane.offsetWidth ? pane.offsetWidth + 12 : 0;
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
    if (sizes.stage) panes.style.setProperty("--stage-h", `${sizes.stage}px`);
    else panes.style.removeProperty("--stage-h");
    // the goal column beside the stage ("beside the stage" layout): its width
    const stagePane = panes.querySelector(".stage-pane");
    if (sizes.head && stagePane) {
      const most = Math.max(220, stagePane.clientWidth - 300);
      stagePane.style.setProperty("--head-w", `${Math.max(220, Math.min(sizes.head, most))}px`);
    } else stagePane?.style.removeProperty("--head-w");
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
  // "Everything back to normal size" (zoom.js): the bars go back to their places too
  window.addEventListener("codezoo-zoom-reset", () => {
    for (const key of Object.keys(sizes)) delete sizes[key];
    save(sizes);
    apply();
  });
  apply();
}
