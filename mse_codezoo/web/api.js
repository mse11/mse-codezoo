// Thin client for the JSON API served by `codezoo serve` (see mse_codezoo/server.py).
// Every request carries the interface language, so titles, hints and messages match it.

import { lang } from "./i18n.js";

// The Python release programs are written for (null: the newest the engine can read).
let python = null;
export function setPython(version) {
  python = version || null;
}

// On a classroom hub (`codezoo class serve`) every request carries the class code, and on
// the teacher's computer also the teacher's key (so the level editor works there too).
// Both are kept only in this browser; a new hub start makes new ones.
const CLASS_KEY = "codezoo.class";
const TEACHER_KEY = "codezoo.teacher";

function stored(storage, key) {
  try {
    return storage.getItem(key);
  } catch {
    return null;
  }
}

function store(storage, key, value) {
  try {
    if (value) storage.setItem(key, value);
    else storage.removeItem(key);
  } catch {
    // storage blocked: asked again next time
  }
}

let classCode = stored(localStorage, CLASS_KEY);
let teacherKey = stored(localStorage, TEACHER_KEY); // the teacher's own computer only

export function setClassCode(code) {
  classCode = code || null;
  store(localStorage, CLASS_KEY, classCode);
}
export const getClassCode = () => classCode;

export function setTeacherKey(key) {
  teacherKey = key || null;
  store(localStorage, TEACHER_KEY, teacherKey);
}

// The offline build (`codezoo build-web`) runs the engine in the browser, in a web worker,
// instead of asking `codezoo serve`.
const offline = window.CODEZOO_OFFLINE ? import("./offline.js") : null;

async function call(method, path, body) {
  if (python && body !== undefined) body = { ...body, python };
  if (offline) {
    const engine = await offline;
    const [route, search = ""] = path.split("?");
    const query = Object.fromEntries(new URLSearchParams(search));
    if (python) query.python = python;
    const { status, data } = await engine.request(method, route, query, body || {}, lang());
    if (status !== 200) {
      const error = new Error(data.error || `error ${status}`);
      error.status = status;
      throw error;
    }
    return data;
  }
  const options = { method, headers: {} };
  if (classCode) options.headers["X-Class-Code"] = classCode;
  if (teacherKey) options.headers["X-Teacher-Token"] = teacherKey;
  const separator = path.includes("?") ? "&" : "?";
  let url = `${path}${separator}lang=${encodeURIComponent(lang())}`;
  if (python) url += `&python=${encodeURIComponent(python)}`;
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || response.statusText);
    error.status = response.status;
    throw error;
  }
  return data;
}

export const api = {
  info: () => call("GET", "/api/info"),
  levels: (animal) => call("GET", `/api/levels${animal ? `?animal=${encodeURIComponent(animal)}` : ""}`),
  level: (id, animal) =>
    call("GET", `/api/levels/${encodeURIComponent(id)}${animal ? `?animal=${encodeURIComponent(animal)}` : ""}`),
  animals: () => call("GET", "/api/animals"),
  parse: (source) => call("POST", "/api/parse", { source }),
  print: (program) => call("POST", "/api/print", { program }),
  run: (level, source, profile, variant = 0, extra = {}) =>
    call("POST", "/api/run", { level, source, profile, variant, save: true, ...extra }),
  runLevelData: (levelData, source, variant = 0) => call("POST", "/api/run", { levelData, source, variant }),
  checkLevel: (level, solution) => call("POST", "/api/levels/check", { level, solution }),
  previewLevel: (level, animal) => call("POST", "/api/levels/preview", { level, animal }),
  story: (run) => call("POST", "/api/story", { run }),

  profiles: () => call("GET", "/api/profiles"),
  addProfile: (name, picture) => call("POST", "/api/profiles", { name, picture }),
  progress: (id) => call("GET", `/api/profiles/${id}/progress`),
  addTime: (id, seconds) => call("POST", `/api/profiles/${id}/time`, { seconds }),
  parent: (action, body = {}) => call("POST", `/api/parent/${action}`, body),
  unlock: (id, code) => call("POST", `/api/profiles/${id}/unlock`, { code }),
  habitat: (id) => call("GET", `/api/profiles/${id}/habitat`),
  setHabitat: (id, body) => call("POST", `/api/profiles/${id}/habitat`, body),

  // pilots (phase 6)
  pilotEvent: (id, body) => call("POST", `/api/profiles/${id}/pilot`, body),
  checkQuestions: (module) => call("GET", `/api/checks/${encodeURIComponent(module)}`),
  answerCheck: (id, module, phase, answers) => call("POST", `/api/profiles/${id}/check`, { module, phase, answers }),

  // the classroom hub (phase 5)
  joinClass: (code) => call("POST", "/api/class/join", { code }),
  classState: () => call("GET", "/api/class/state"),
  classMe: (picture, name) => call("POST", "/api/class/me", { picture, name }),
  classImport: (data) => call("POST", "/api/class/import", { data }),
  classExport: (profile) => call("POST", "/api/class/export", { profile }),
  classShares: () => call("GET", "/api/class/shares"),
  share: (profile, kind, title, payload) => call("POST", "/api/class/share", { profile, kind, title, payload }),
  reportShare: (share) => call("POST", "/api/class/report", { share }),
  teacher: (route, body) =>
    body === undefined ? call("GET", `/api/teacher/${route}`) : call("POST", `/api/teacher/${route}`, body),
};
