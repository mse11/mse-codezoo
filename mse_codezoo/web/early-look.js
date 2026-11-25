// Runs before the page is first drawn: a plain script at the top of <head>, not a module
// (modules wait until the page is parsed, and app.js loads many). It puts the saved "Look and
// feel" on <html> at once, so a page set to dark colours doesn't flash light while the
// modules load. look.js applies the same settings again, with a teacher's locks on top;
// keep the two in step (the same storage key and attribute values as applyLook()).
(function () {
  var settings = {};
  try {
    settings = JSON.parse(localStorage.getItem("codezoo.look") || "{}") || {};
  } catch (e) {
    // storage blocked: the device's own colours, as without a saved choice
  }
  var root = document.documentElement;
  if (settings.theme === "light" || settings.theme === "dark") root.dataset.theme = settings.theme;
  root.dataset.text = settings.text || "normal";
  root.dataset.easy = String(Boolean(settings.easy));
  root.dataset.contrast = String(Boolean(settings.contrast));
  root.dataset.targets = String(Boolean(settings.targets));
  var reduce = settings.motion === "reduce" ||
    ((settings.motion || "system") === "system" && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  root.dataset.motion = reduce ? "reduce" : "full";
  // the goal beside the stage or above it, as look.js layout() decides
  var wide = window.matchMedia("(min-width: 1300px), (min-width: 1000px) and (min-aspect-ratio: 4/3)").matches;
  root.dataset.layout = settings.layout === "above" || settings.layout === "side" ? settings.layout : wide ? "side" : "above";
})();
