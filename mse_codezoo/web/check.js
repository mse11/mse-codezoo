// Device check (phase 6): is this tablet, Chromebook or laptop ready for a pilot?
// WebGL and the 3D stage's frame rate, how long the engine takes to start (Pyodide in the
// offline build), one level run, storage, and whether a classroom hub answers. Nothing is
// sent anywhere; the results are for the pilot's device checklist.

import { api } from "./api.js";
import { initialLang, setLang, t, translatePage } from "./i18n.js";
import "./look.js";

const $ = (id) => document.getElementById(id);
const FRAME_SECONDS = 3;
const GOOD_FPS = 25; // below this the 2D stage is the better choice
const VIEW_KEY = "codezoo.view"; // the game's own 2D/3D setting (app.js)
const results = [];

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  node.append(...children);
  return node;
}

function show(name, value, ok) {
  results.push([name, value]);
  $("c-results").append(
    el("tr", {}, el("th", {}, name), el("td", {}, value), el("td", {}, ok === undefined ? "" : ok ? "✓" : "⚠")),
  );
}

async function timed(fn) {
  const start = performance.now();
  const value = await fn();
  return [value, (performance.now() - start) / 1000];
}

function frames(stage) {
  return new Promise((resolve) => {
    let count = 0;
    const end = performance.now() + FRAME_SECONDS * 1000;
    const tick = () => {
      count += 1;
      stage.render?.();
      if (performance.now() < end) requestAnimationFrame(tick);
      else resolve(count / FRAME_SECONDS);
    };
    requestAnimationFrame(tick);
  });
}

async function run() {
  $("c-start").disabled = true;
  $("c-results").replaceChildren();
  results.length = 0;
  const advice = [];
  show(t("Screen"), `${screen.width} × ${screen.height}, ${navigator.maxTouchPoints > 0 ? t("touch") : t("no touch")}`);
  show(t("Offline version"), window.CODEZOO_OFFLINE ? t("yes") : t("no (served by a computer)"));

  let info = null;
  try {
    const [answer, seconds] = await timed(() => api.info());
    info = answer;
    show(t("Engine start"), t("{s} s", { s: seconds.toFixed(1) }), seconds < 15);
    if (seconds >= 15) advice.push(t("The engine starts slowly here: open CodeZoo a minute before the session."));
  } catch (error) {
    show(t("Engine start"), error.message, false);
    advice.push(t("The engine did not start. Check the address, or the network for the first visit."));
  }
  if (info?.hub) show(t("Classroom hub"), info.hub.name, true);

  if (info) {
    try {
      const [, seconds] = await timed(() => api.run("m01-l01", "step(4)\ngrab()\n", null));
      show(t("Running a level"), t("{s} s", { s: seconds.toFixed(2) }), seconds < 2);
    } catch (error) {
      // in a class, levels need the class code: join on the game page first
      show(t("Running a level"), error.status === 403 ? t("join the class first") : error.message, error.status === 403 ? undefined : false);
    }
  }

  let fps = null;
  try {
    const module = await import("./stage3d.js");
    if (!module.webglAvailable()) throw new Error(t("no WebGL"));
    const level = await api.level("m01-l01");
    const stage = new module.Stage3D($("c-stage"));
    stage.load(level, level.world, level.goal);
    fps = await frames(stage);
    show(t("3D stage"), t("{n} frames a second", { n: Math.round(fps) }), fps >= GOOD_FPS);
    if (fps < GOOD_FPS) advice.push(t("3D is slow here: use the 2D stage on this device."));
  } catch (error) {
    show(t("3D stage"), error.message, false);
    advice.push(t("Use the 2D stage on this device."));
    fps = 0;
  }
  $("c-stage").replaceChildren();

  try {
    const estimate = await navigator.storage?.estimate?.();
    if (estimate) show(t("Free storage"), t("{n} MB", { n: Math.round((estimate.quota - estimate.usage) / 1e6) }), estimate.quota - estimate.usage > 50e6);
  } catch {
    // not reported by this browser
  }

  $("c-advice").textContent = advice.length ? advice.join(" ") : t("This device is ready.");
  $("c-copy").hidden = false;
  $("c-use2d").hidden = fps === null || fps >= GOOD_FPS;
  $("c-start").disabled = false;
}

$("c-start").addEventListener("click", run);
$("c-copy").addEventListener("click", async () => {
  const text = [`CodeZoo ${navigator.userAgent}`, ...results.map(([k, v]) => `${k}: ${v}`)].join("\n");
  try {
    await navigator.clipboard.writeText(text);
    $("c-advice").textContent = t("Copied.");
  } catch {
    $("c-advice").textContent = text;
  }
});
$("c-use2d").addEventListener("click", () => {
  try {
    localStorage.setItem(VIEW_KEY, "2d");
    $("c-advice").textContent = t("Done: the game opens with the 2D stage on this device.");
  } catch {
    // storage blocked
  }
});

setLang(initialLang());
translatePage();
