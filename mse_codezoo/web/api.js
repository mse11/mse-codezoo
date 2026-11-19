// Thin client for the JSON API served by `codezoo serve` (see mse_codezoo/server.py).

async function call(method, path, body) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || response.statusText);
    error.status = response.status;
    throw error;
  }
  return data;
}

export const api = {
  levels: () => call("GET", "/api/levels"),
  level: (id) => call("GET", `/api/levels/${encodeURIComponent(id)}`),
  parse: (source) => call("POST", "/api/parse", { source }),
  print: (program) => call("POST", "/api/print", { program }),
  run: (level, source, profile) => call("POST", "/api/run", { level, source, profile }),

  profiles: () => call("GET", "/api/profiles"),
  addProfile: (name, picture) => call("POST", "/api/profiles", { name, picture }),
  progress: (id) => call("GET", `/api/profiles/${id}/progress`),
  addTime: (id, seconds) => call("POST", `/api/profiles/${id}/time`, { seconds }),
  parent: (action, body = {}) => call("POST", `/api/parent/${action}`, body),
};
