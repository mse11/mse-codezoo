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

export function setupSplitters({ panes, stageSplit, paneSplit, onResize }) {
  const sizes = load();
  const apply = () => {
    // a width saved in a wider window must not make the page wider than this one
    const room = document.documentElement.clientWidth - 32 - 12 - 220;
    if (sizes.left) panes.style.setProperty("--left", `${Math.max(220, Math.min(sizes.left, room))}px`);
    else panes.style.removeProperty("--left");
    if (sizes.stage) panes.style.setProperty("--stage-h", `${sizes.stage}px`);
    else panes.style.removeProperty("--stage-h");
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
    sizes.left = Math.round(clamp(e.clientX - box.left - 16, 220, box.width - 32 - 12 - 220));
  });
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
        sizes.left = clamp(current + (e.key === "ArrowLeft" ? -step : step), 220, box.width - 264);
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

  window.addEventListener("resize", apply);
  apply();
}
