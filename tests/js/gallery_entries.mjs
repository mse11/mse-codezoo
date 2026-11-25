// Builds every gallery entry (web/blocks.js galleryEntries) with the real Blockly, headless,
// for each animal's command names, and prints them as JSON for tests/test_gallery.py, which
// prints each one with the engine and checks it. Run: node gallery_entries.mjs '<names json>'
// where the argument maps an animal to its command names ({"penguin": {"grab": "catch"}}).

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import vm from "node:vm";

const here = path.dirname(fileURLToPath(import.meta.url));
const web = path.resolve(here, "..", "..", "mse_codezoo", "web");

// just enough of a browser for blocks.js and i18n.js to load (no drawing happens headless)
const store = new Map();
globalThis.window = globalThis;
globalThis.self = globalThis;
globalThis.localStorage = {
  getItem: (key) => (store.has(key) ? store.get(key) : null),
  setItem: (key, value) => store.set(key, String(value)),
  removeItem: (key) => store.delete(key),
};
globalThis.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
const element = () => ({ dataset: {}, style: {}, append() {}, setAttribute() {}, classList: { add() {}, remove() {}, toggle() {} } });
// Blockly keeps a socket's default value (a shadow block) as a small XML element: a tiny
// stand-in for the browser's XML nodes is enough for that
class XmlNode {
  constructor(name) {
    this.nodeName = this.tagName = name;
    this.nodeType = 1;
    this.attributes = new Map();
    this.childNodes = [];
    this.parentNode = null;
  }
  get children() {
    return this.childNodes.filter((node) => node.nodeType === 1);
  }
  get firstChild() {
    return this.childNodes[0] || null;
  }
  get textContent() {
    return this.childNodes.map((node) => node.textContent).join("");
  }
  set textContent(value) {
    this.childNodes = [{ nodeType: 3, nodeName: "#text", textContent: String(value), data: String(value) }];
  }
  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }
  getAttribute(name) {
    return this.attributes.has(name) ? this.attributes.get(name) : null;
  }
  hasAttribute(name) {
    return this.attributes.has(name);
  }
  removeAttribute(name) {
    this.attributes.delete(name);
  }
  appendChild(node) {
    node.parentNode = this;
    this.childNodes.push(node);
    return node;
  }
  removeChild(node) {
    this.childNodes = this.childNodes.filter((child) => child !== node);
    return node;
  }
  insertBefore(node, before) {
    const at = before ? this.childNodes.indexOf(before) : -1;
    node.parentNode = this;
    if (at < 0) this.childNodes.push(node);
    else this.childNodes.splice(at, 0, node);
    return node;
  }
  cloneNode(deep) {
    const copy = new XmlNode(this.nodeName);
    for (const [name, value] of this.attributes) copy.setAttribute(name, value);
    if (deep) for (const child of this.childNodes) copy.appendChild(child.cloneNode ? child.cloneNode(true) : { ...child });
    return copy;
  }
}

globalThis.document = {
  documentElement: element(),
  createElement: element,
  createElementNS: (_namespace, name) => new XmlNode(name),
  createTextNode: (text) => ({ nodeType: 3, nodeName: "#text", textContent: String(text), data: String(text) }),
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener() {},
};
globalThis.addEventListener = () => {};
globalThis.dispatchEvent = () => {};
globalThis.CustomEvent = class CustomEvent {};

vm.runInThisContext(fs.readFileSync(path.join(web, "vendor", "blockly", "blockly.min.js"), "utf8"), {
  filename: "blockly.min.js",
});

const { galleryEntries } = await import(pathToFileURL(path.join(web, "blocks.js")).href);
const animals = JSON.parse(process.argv[2] || '{"monkey": {}}');
const out = {};
const skipped = {};
for (const [animal, names] of Object.entries(animals)) {
  const entries = galleryEntries(names, { game: true }); // the game blocks too
  skipped[animal] = entries.skipped;
  out[animal] = entries.map((entry) => ({
    key: entry.key,
    statement: entry.statement,
    words: entry.words,
    meaning: entry.meaning,
    stmts: entry.stmts,
  }));
}
process.stdout.write(JSON.stringify({ entries: out, skipped }));
