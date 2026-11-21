// Share links for levels made in the editor: the level travels inside the link itself
// (index.html#play=...), so nothing is uploaded anywhere. The game checks it like a level
// file before it runs, and it only ever runs in the zoo's own interpreter.

const MAX_LINK = 60_000; // characters; bigger levels are shared as files

export function encodeShare(data) {
  const bytes = new TextEncoder().encode(JSON.stringify(data));
  let text = "";
  for (const byte of bytes) text += String.fromCharCode(byte);
  const link = btoa(text).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
  if (link.length > MAX_LINK) throw new Error("This level is too big for a link; download it instead.");
  return link;
}

export function decodeShare(link) {
  const base64 = link.replaceAll("-", "+").replaceAll("_", "/");
  const text = atob(base64 + "=".repeat((4 - (base64.length % 4)) % 4));
  const bytes = Uint8Array.from(text, (c) => c.charCodeAt(0));
  return JSON.parse(new TextDecoder().decode(bytes));
}
