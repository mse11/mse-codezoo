// The offline build: the engine runs in this browser, in a web worker (engine-worker.js),
// instead of on `codezoo serve`. Only loaded when the page was made by `codezoo build-web`.

const config = window.CODEZOO_OFFLINE;
const worker = new Worker("engine-worker.js");
const waiting = new Map();
let counter = 0;

worker.addEventListener("message", (event) => {
  const { id, result, error } = event.data;
  const pending = waiting.get(id);
  if (!pending) return;
  waiting.delete(id);
  if (error) pending.reject(new Error(error));
  else pending.resolve(result);
});

function ask(message) {
  const id = ++counter;
  return new Promise((resolve, reject) => {
    waiting.set(id, { resolve, reject });
    worker.postMessage({ id, ...message });
  });
}

const ready = ask({ kind: "start", config });

// Same answers as the HTTP API: {status, data}.
export async function request(method, path, query, body, lang) {
  await ready;
  return ask({ kind: "request", method, path, query, body, lang });
}

// Keep every file for offline use after the first visit.
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {
    // no service worker (a private window, file://): it still works while online
  });
}
