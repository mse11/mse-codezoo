// The 2D stage: an SVG grid world that animates the world events from a run.
// Used when 3D is off or WebGL is missing; same interface as Stage3D in stage3d.js.

import { t } from "./i18n.js";

const CELL = 64;
const TOP = 44; // room above the grid for speech bubbles
const NS = "http://www.w3.org/2000/svg";
const ANGLE = { north: -90, east: 0, south: 90, west: 180 };
export const EMOJI = {
  monkey: "🐒", penguin: "🐧", beaver: "🦫", fox: "🦊", octopus: "🐙", bee: "🐝",
  banana: "🍌", coconut: "🥥", rotten: "🤢", fish: "🐟", log: "🪵", shell: "🐚", flower: "🌼",
  pebble: "🪨", crab: "🦀", stick: "🪵", leaf: "🍃", thorn: "🌵", oak: "🪵", pine: "🌲",
  birch: "🌳", berry: "🫐", mushroom: "🍄", trap: "🪤", egg: "🥚",
  pearl: "⚪", jellyfish: "🪼", clover: "🍀", nettle: "🌿",
};
// what the animal says when grab() finds nothing, by where the item really was
export function missBubble(near) {
  if (near === "ahead") return t("Too far!");
  if (near === "behind") return t("Missed it!");
  if (near === "left" || near === "right") return t("Over there!");
  if (near === "up") return t("Up there!");
  return t("Nothing here");
}
// animals whose emoji looks at us rather than to one side
const FRONT_FACING = new Set(["penguin", "octopus"]);
// the octopus's arms, clockwise from north (as in world.py)
const ARMS = [[0, -1], [1, -1], [1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0], [-1, -1]];
// events that only matter to the lanes and the result, not the stage
const QUIET = new Set(["task", "thread", "lock", "file", "input", "import", "call", "return", "print"]);
// terrain: ~ water or a gap, t tree, - thin ice, o a guard's watch, = a log bridge
const TERRAIN = { "~": ["water", ""], t: ["tree", "🌴"], "-": ["thin-ice", ""], o: ["watched", "👁️"], "=": ["bridge", ""] };

// Squares the animal must reach, for a goal flag.
function reachTargets(goal) {
  if (!goal) return [];
  if (goal.type === "reach") return [goal.at];
  if (goal.type === "all") return goal.goals.flatMap(reachTargets);
  return [];
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function svg(name, attrs = {}, text) {
  const node = document.createElementNS(NS, name);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  if (text !== undefined) node.textContent = text;
  return node;
}

export class Stage {
  constructor(container) {
    this.container = container;
    this.duration = 250;
  }

  attach() {}

  detach() {}

  setSpeed(level) {
    this.duration = [700, 450, 250, 140, 60][level - 1] ?? 250;
    this.container.style.setProperty("--dur", `${this.duration}ms`);
  }

  load(level, world, goal) {
    this.level = level;
    this.world = world || level.world;
    this.targets = reachTargets(goal || level.goal);
    this.reset();
  }

  reset() {
    const { pack } = this.level;
    const world = this.world;
    const [width, height] = world.size;
    const root = svg("svg", {
      viewBox: `0 ${-TOP} ${width * CELL} ${height * CELL + TOP}`,
      class: "stage-svg",
      role: "img",
      "aria-label": `${pack.worldName || pack.world}: ${width} × ${height}`,
    });

    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const alt = (x + y) % 2 ? " alt" : "";
        root.append(svg("rect", { x: x * CELL, y: y * CELL, width: CELL, height: CELL, class: `tile${alt}` }));
      }
    }
    this.terrain = new Map();
    for (const [x, y, kind] of world.terrain || []) this.drawTerrain(root, x, y, kind);
    for (const [x, y] of world.walls) {
      root.append(svg("rect", { x: x * CELL + 2, y: y * CELL + 2, width: CELL - 4, height: CELL - 4, rx: 10, class: "wall" }));
      root.append(svg("text", { x: x * CELL + CELL / 2, y: y * CELL + CELL / 2, class: "emoji" }, "🪨"));
    }

    for (const [x, y] of this.targets) {
      root.append(svg("rect", { x: x * CELL + 3, y: y * CELL + 3, width: CELL - 6, height: CELL - 6, rx: 12, class: "target" }));
      root.append(svg("text", { x: x * CELL + CELL - 14, y: y * CELL + 16, class: "emoji flag" }, "🏁"));
    }

    this.items = new Map();
    for (const [x, y, tile] of world.items) {
      const noun = pack.items[tile] || "item";
      const item = svg("text", { x: x * CELL + CELL / 2, y: y * CELL + CELL / 2, class: "emoji item" }, EMOJI[noun] || "⭐");
      item.append(svg("title", {}, pack.itemNames?.[tile]?.one || noun));
      this.items.set(`${x},${y}`, item);
      root.append(item);
    }

    this.arms = new Map(); // arm number -> the stretched arm, while it is out
    this.armLayer = svg("g", { class: "arms" });
    root.append(this.armLayer);
    this.animal = svg("g", { class: "animal" });
    this.body = svg("g", { class: "body" });
    this.facingGroup = svg("g", { class: "facing" });
    this.facingGroup.append(svg("polygon", { points: "52,24 62,32 52,40", class: "arrow" }));
    this.body.append(this.facingGroup);
    this.face = svg("text", { x: CELL / 2, y: CELL / 2, class: "emoji animal-face" }, pack.emoji || EMOJI[pack.animal] || "🐾");
    this.body.append(this.face);
    this.outfitText = svg("text", { x: CELL / 2, y: 6, class: "emoji outfit" }, this.outfit || "");
    this.body.append(this.outfitText);
    this.bubble = svg("g", { class: "bubble", visibility: "hidden" });
    this.bubbleRect = svg("rect", { x: 0, y: -38, rx: 10, height: 30 });
    this.bubbleText = svg("text", { x: CELL / 2, y: -23 });
    this.bubble.append(this.bubbleRect, this.bubbleText);
    this.animal.append(this.body, this.bubble);
    root.append(this.animal);

    this.container.replaceChildren(root);
    this.position = [...world.position];
    this.facing = world.facing;
    this.angle = ANGLE[this.facing];
    this.place();
  }

  drawTerrain(root, x, y, kind) {
    const [name, mark] = TERRAIN[kind] || ["tile", ""];
    const group = svg("g", { class: `terrain ${name}` });
    group.append(svg("rect", { x: x * CELL + 1, y: y * CELL + 1, width: CELL - 2, height: CELL - 2, rx: 8 }));
    if (mark) group.append(svg("text", { x: x * CELL + CELL / 2, y: y * CELL + CELL / 2, class: "emoji" }, mark));
    this.terrain.get(`${x},${y}`)?.remove();
    this.terrain.set(`${x},${y}`, group);
    const firstItem = [...root.children].find((node) => node.classList?.contains("wall") || node.classList?.contains("item"));
    root.insertBefore(group, firstItem || null);
  }

  // What the animal wears (from the habitat): an emoji above its head.
  setOutfit(emoji) {
    this.outfit = emoji || "";
    if (this.outfitText) this.outfitText.textContent = this.outfit;
  }

  place() {
    const [x, y] = this.position;
    this.animal.style.transform = `translate(${x * CELL}px, ${y * CELL}px)`;
    this.facingGroup.style.transform = `rotate(${this.angle}deg)`;
    this.lookTowards(this.facing);
  }

  // Emoji animals mostly look to the left: mirror the picture when it walks east, and keep
  // the last side when it walks north or south. Animals drawn from the front stay as they are.
  lookTowards(direction) {
    if (!this.face || FRONT_FACING.has(this.level?.pack.id)) return;
    if (direction === "east") this.face.classList.add("mirrored");
    else if (direction === "west") this.face.classList.remove("mirrored");
  }

  say(text) {
    const width = Math.max(44, text.length * 9 + 24);
    this.bubbleRect.setAttribute("width", width);
    this.bubbleRect.setAttribute("x", CELL / 2 - width / 2);
    this.bubbleText.textContent = text;
    this.bubble.setAttribute("visibility", "visible");
  }

  hideBubble() {
    this.bubble.setAttribute("visibility", "hidden");
  }

  // where the animal is on the screen (for "+1" texts and confetti, fun.js)
  animalPoint() {
    const box = this.face?.getBoundingClientRect();
    if (!box || !box.width) return null;
    return { x: box.left + box.width / 2, y: box.top + box.height / 2 };
  }

  hitAnimal(event) {
    return Boolean(event.target.closest?.(".animal"));
  }

  // poked while nothing runs: a hop and a word; every tenth poke is a dance
  poke(text, { dance = false } = {}) {
    clearTimeout(this.pokeTimer);
    this.say(text);
    const move = dance ? "dance" : "poked";
    this.body.classList.remove("poked", "dance");
    void this.body.getBoundingClientRect(); // restart the animation
    this.body.classList.add(move);
    this.pokeTimer = setTimeout(() => {
      this.body.classList.remove(move);
      this.hideBubble();
    }, dance ? 2600 : 1600);
  }

  showFeeling(feeling) {
    if (!feeling) return;
    this.say(feeling.face);
    this.body.classList.add(`mood-${feeling.mood}`);
    setTimeout(() => {
      this.body.classList.remove(`mood-${feeling.mood}`);
      this.hideBubble();
    }, 2500);
  }

  // grab() found nothing: reach for the item, look back, look around or up, or shrug,
  // and show where the item really is with a dashed square
  async missed(event) {
    const d = Math.max(this.duration, 200);
    const near = event.near || "none";
    let ghost = null;
    if (event.to) {
      ghost = svg("rect", {
        x: event.to[0] * CELL + 4, y: event.to[1] * CELL + 4, width: CELL - 8, height: CELL - 8,
        rx: 12, class: "ghost-target",
      });
      this.animal.before(ghost);
    }
    this.say(missBubble(near));
    const [x, y] = this.position;
    if (near === "ahead" && event.to) {
      // lean towards the item, then back: it's out of reach
      const [tx, ty] = event.to;
      const reach = 0.3 / Math.max(Math.abs(tx - x) + Math.abs(ty - y), 1);
      this.animal.style.transform = `translate(${(x + (tx - x) * reach) * CELL}px, ${(y + (ty - y) * reach) * CELL}px)`;
      await wait(d * 1.5);
      this.place();
      await wait(d);
    } else if (event.to && near !== "up") {
      // turn to look at it, then back
      const [tx, ty] = event.to;
      const look = (Math.atan2(ty - y, tx - x) * 180) / Math.PI;
      this.facingGroup.style.transform = `rotate(${look}deg)`;
      if (tx !== x) this.lookTowards(tx > x ? "east" : "west");
      await wait(d * 2);
      this.place();
      await wait(d);
    } else {
      const mood = near === "up" ? "look-up" : "shrug";
      this.body.classList.add(mood);
      await wait(d * 2.5);
      this.body.classList.remove(mood);
    }
    this.hideBubble();
    ghost?.remove();
  }

  async play(event) {
    const d = this.duration;
    if (QUIET.has(event.type)) return;
    switch (event.type) {
      case "reach": {
        // an arm stretches out to its tip; it stays out until its grab comes back
        const [x, y] = this.position;
        const [tx, ty] = event.to;
        const line = svg("line", {
          x1: x * CELL + CELL / 2, y1: y * CELL + CELL / 2,
          x2: x * CELL + CELL / 2, y2: y * CELL + CELL / 2, class: "arm",
        });
        this.armLayer.append(line);
        this.arms.get(event.arm)?.remove();
        this.arms.set(event.arm, line);
        await wait(20);
        line.setAttribute("x2", tx * CELL + CELL / 2);
        line.setAttribute("y2", ty * CELL + CELL / 2);
        await wait(d);
        break;
      }
      case "fly":
        this.body.classList.add("swing");
        this.position = event.to;
        this.place();
        await wait(d * 1.4);
        this.body.classList.remove("swing");
        break;
      case "block":
        this.say("⏳");
        await wait(d * 2);
        this.hideBubble();
        break;
      case "move":
        this.position = event.to;
        this.place();
        await wait(event.slide ? d * 0.6 : d);
        break;
      case "swing":
        this.body.classList.add("swing");
        this.position = event.to;
        this.place();
        await wait(d * 1.6);
        this.body.classList.remove("swing");
        break;
      case "climb": {
        const key = event.at.join(",");
        const item = this.items.get(key);
        this.body.classList.add("sense");
        await wait(d);
        if (item) {
          item.classList.add("grabbed");
          await wait(d);
          item.remove();
          this.items.delete(key);
        }
        this.body.classList.remove("sense");
        break;
      }
      case "build": {
        const root = this.container.querySelector("svg");
        this.drawTerrain(root, event.at[0], event.at[1], "=");
        await wait(d * 1.2);
        break;
      }
      case "crack": {
        const tile = this.terrain.get(event.at.join(","));
        tile?.classList.add("cracked");
        this.body.classList.add("bump");
        await wait(700);
        this.body.classList.remove("bump");
        break;
      }
      case "hide":
        this.body.classList.add("hidden-animal");
        await wait(d);
        break;
      case "turn": {
        this.body.classList.remove("hidden-animal");
        const delta = ((ANGLE[event.facing] - ANGLE[this.facing] + 540) % 360) - 180;
        this.angle += delta;
        this.facing = event.facing;
        this.place();
        await wait(d * 0.8);
        break;
      }
      case "grab": {
        const key = event.at.join(",");
        const item = this.items.get(key);
        if (event.arm !== undefined) {
          const line = this.arms.get(event.arm);
          if (item && event.item) item.classList.add("grabbed");
          if (line) {
            const [x, y] = this.position;
            line.setAttribute("x2", x * CELL + CELL / 2);
            line.setAttribute("y2", y * CELL + CELL / 2);
          }
          await wait(d);
          line?.remove();
          this.arms.delete(event.arm);
          if (item && event.item) {
            item.remove();
            this.items.delete(key);
          }
          break;
        }
        if (event.item && item) {
          item.classList.add("grabbed");
          await wait(d);
          item.remove();
          this.items.delete(key);
        } else {
          await this.missed(event);
        }
        break;
      }
      case "say":
        this.say(event.text);
        await wait(d * 4);
        this.hideBubble();
        break;
      case "bump":
        this.body.classList.add("bump");
        await wait(650);
        this.body.classList.remove("bump");
        break;
      case "sense":
        this.body.classList.add("sense");
        await wait(d * 0.8);
        this.body.classList.remove("sense");
        break;
      default:
        await wait(d / 2);
    }
  }
}
