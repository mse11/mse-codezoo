// Zoom for the parts of the main page: −, + and a reset button, and Ctrl (⌘ on a Mac) +
// mouse wheel over the part. Each part keeps its own size in this browser.
//
//   Top bar          Ctrl + wheel only (no buttons: the bar is full already)
//   Blocks           Blockly's own scale (its canvas buttons are turned off)
//   Python, Console  the text (--zoom on the pane)
//   Pane titles      Ctrl + wheel over any title: all the titles together (--title-zoom), so
//                    Blocks, Python and Console always match
//   Stage            the 2D board or the 3D view (--stage-zoom), anywhere in the stage pane
//   Goal and result  the column or row with the goal (--head-zoom)
//
// The page's base size already grows with the window (style.css); zoom is on top of that.
// Ctrl + wheel never zooms the whole page here (it used to, once a part had shrunk out from
// under the mouse); "Zoom back to normal" in Look and feel resets every part.

import { t } from "./i18n.js";

const KEY = "codezoo.zoom";
const MIN = 0.4;
const MAX = 4;
const STEP = 1.15; // each step grows or shrinks by 15%, so big sizes are quick to reach
const RESET = "codezoo-zoom-reset";

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
    // storage blocked: the size lasts until the page closes
  }
}

// every part back to its normal size, and the movable bars back to their places
// (layout.js listens too): the ⤢ button in the top bar and Look and feel
export function resetAllZoom() {
  save({});
  window.dispatchEvent(new CustomEvent(RESET));
}

function button(text, label, onClick) {
  const node = document.createElement("button");
  node.type = "button";
  node.className = "zoom-button";
  node.textContent = text;
  node.title = t(label);
  node.setAttribute("aria-label", t(label));
  node.dataset.i18nTitle = label;
  node.dataset.i18nLabel = label;
  node.addEventListener("click", onClick);
  return node;
}

// −, + and the reset (or fit) button, added at the end of `place`
function addButtons(place, { zoomOut, zoomIn, fit, fitLabel, label = "Zoom" }) {
  const group = document.createElement("span");
  group.className = "zoom-tools";
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", t(label));
  group.dataset.i18nLabel = label;
  group.append(button("−", "Zoom out", zoomOut), button("+", "Zoom in", zoomIn), button("⤢", fitLabel, fit));
  place.append(group);
  return group;
}

// Ctrl + wheel (and a trackpad pinch, which browsers send as Ctrl + wheel) over `area`.
// Parts inside other parts (the goal inside the stage pane) listen while the event bubbles
// and stop it, so the outer part zooms only where the inner one isn't. Blockly handles the
// wheel itself, so the Blocks pane listens before it does (`capture`).
function onCtrlWheel(area, zoom, { capture = false, skip = null } = {}) {
  area.addEventListener(
    "wheel",
    (event) => {
      if (!event.ctrlKey && !event.metaKey) return;
      if (skip && event.target.closest?.(skip)) return; // a part inside has its own zoom
      event.preventDefault(); // not the browser's own page zoom
      event.stopPropagation();
      if (event.deltaY) zoom(event.deltaY < 0 ? 1 : -1);
    },
    { passive: false, capture },
  );
}

// Anywhere else on the page (gaps between panes, the edges): Ctrl + wheel does nothing,
// rather than suddenly zooming the whole page.
export function keepPageZoom() {
  document.addEventListener(
    "wheel",
    (event) => {
      if (event.ctrlKey || event.metaKey) event.preventDefault();
    },
    { passive: false },
  );
}

// A part whose size is a CSS variable (`variable`) on `target`; the buttons go into `place`
// (none without a place).
// `area` may be several elements (every pane title).
export function setupZoom({ area, target = area, place, name, variable = "--zoom", label, onChange = () => {} }) {
  let sizes = load();
  const apply = () => {
    target.style.setProperty(variable, String(sizes[name] || 1));
    onChange();
  };
  const zoom = (direction) => {
    sizes = load(); // another part may have saved meanwhile
    const now = sizes[name] || 1;
    let next = Math.round((direction > 0 ? now * STEP : now / STEP) * 100) / 100;
    if (Math.abs(next - 1) < 0.05) next = 1; // the normal size is always one of the steps
    sizes[name] = Math.min(MAX, Math.max(MIN, next));
    if (sizes[name] === 1) delete sizes[name];
    save(sizes);
    apply();
  };
  if (place) {
    addButtons(place, {
      zoomOut: () => zoom(-1),
      zoomIn: () => zoom(1),
      fit: () => {
        sizes = load();
        delete sizes[name];
        save(sizes);
        apply();
      },
      fitLabel: "Normal size",
      label,
    });
  }
  for (const one of area instanceof Element ? [area] : area) onCtrlWheel(one, zoom);
  window.addEventListener(RESET, () => {
    sizes = {};
    apply();
  });
  apply();
}

// The Blocks pane: Blockly's own zoom.
export function setupBlocksZoom({ pane, workspace, startScale = 0.8 }) {
  const group = addButtons(pane.querySelector(".pane-title"), {
    zoomOut: () => workspace.zoomCenter(-1),
    zoomIn: () => workspace.zoomCenter(1),
    fit: () => {
      if (workspace.getTopBlocks(false).length) workspace.zoomToFit();
      else workspace.scrollCenter();
    },
    fitLabel: "Fit the blocks in view",
  });
  // The trash can sits with these buttons, not in a corner of the blocks (style.css hides
  // Blockly's own): a tap opens the deleted blocks, to drag one back. Deleting stays the
  // same: drag a block back to the list on the left.
  const trash = workspace.trashcan;
  if (trash) {
    const bin = button("🗑", "Deleted blocks: tap to get one back", () => {
      if (trash.contentsIsOpen()) trash.closeFlyout();
      else if (trash.hasContents()) trash.openFlyout();
    });
    bin.classList.add("trash-button");
    group.prepend(bin);
    const update = () => {
      bin.disabled = !trash.hasContents();
    };
    workspace.addChangeListener(update);
    update();
  }
  // the title has its own zoom (all titles together), so it is left to that
  onCtrlWheel(pane, (direction) => workspace.zoomCenter(direction), { capture: true, skip: ".pane-title" });
  window.addEventListener(RESET, () => {
    workspace.setScale(startScale);
    workspace.scrollCenter();
  });
}
