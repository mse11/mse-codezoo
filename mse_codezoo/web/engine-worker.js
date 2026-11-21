// The CodeZoo engine in the browser: Pyodide (CPython in WebAssembly) runs the same
// mse_codezoo package as `codezoo serve`, and answers the same API through
// server.dispatch(). Progress is kept in IndexedDB (Pyodide's IDBFS), on this device only.

let pyodide = null;
let dispatch = null;
const DATA = "/codezoo";

async function start(config) {
  importScripts(`${config.pyodide}pyodide.js`);
  pyodide = await self.loadPyodide({ indexURL: config.pyodide });
  const engine = await fetch(config.engine);
  if (!engine.ok) throw new Error(`could not load ${config.engine}`);
  pyodide.unpackArchive(await engine.arrayBuffer(), "zip", { extractDir: "/engine" });
  pyodide.FS.mkdirTree(DATA);
  pyodide.FS.mount(pyodide.FS.filesystems.IDBFS, {}, DATA);
  await sync(true);
  dispatch = pyodide.runPython(`
import sys
sys.path.insert(0, "/engine")
from pathlib import Path
from mse_codezoo.profiles import ProfileStore
from mse_codezoo.server import dispatch_json

store = ProfileStore(Path("${DATA}"))

def answer(method, path, query, body, lang):
    return dispatch_json(method, path, query, body, store, lang)

answer
`);
  return { python: pyodide.runPython("import sys; sys.version.split()[0]") };
}

function sync(load) {
  return new Promise((resolve) => pyodide.FS.syncfs(load, () => resolve()));
}

async function request({ method, path, query, body, lang }) {
  const text = dispatch(method, path, JSON.stringify(query || {}), JSON.stringify(body || {}), lang);
  if (method !== "GET") await sync(false); // keep the players' progress
  return JSON.parse(text);
}

self.addEventListener("message", async (event) => {
  const { id, kind } = event.data;
  try {
    const result = kind === "start" ? await start(event.data.config) : await request(event.data);
    self.postMessage({ id, result });
  } catch (error) {
    self.postMessage({ id, error: String(error?.message || error) });
  }
});
