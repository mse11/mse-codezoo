// The 2D stage: an SVG grid world that animates the world events from a run.
// Used when 3D is off or WebGL is missing; same interface as Stage3D in stage3d.js.

const CELL = 64;
const TOP = 44; // room above the grid for speech bubbles
const NS = "http://www.w3.org/2000/svg";
const ANGLE = { north: -90, east: 0, south: 90, west: 180 };
export const EMOJI = {
  monkey: "🐒", penguin: "🐧", beaver: "🦫", fox: "🦊", octopus: "🐙", bee: "🐝",
  banana: "🍌", coconut: "🥥", rotten: "🤢", fish: "🐟", log: "🪵", shell: "🐚", flower: "🌼",
  pebble: "🪨", crab: "🦀", stick: "🥢", leaf: "🍃", thorn: "🌵", oak: "🪵", pine: "🌲",
  birch: "🌳", berry: "🫐", mushroom: "🍄", trap: "🪤", egg: "🥚",
};
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

    this.animal = svg("g", { class: "animal" });
    this.body = svg("g", { class: "body" });
    this.facingGroup = svg("g", { class: "facing" });
    this.facingGroup.append(svg("polygon", { points: "52,24 62,32 52,40", class: "arrow" }));
    this.body.append(this.facingGroup);
    this.body.append(svg("text", { x: CELL / 2, y: CELL / 2, class: "emoji" }, pack.emoji || EMOJI[pack.animal] || "🐾"));
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

  showFeeling(feeling) {
    if (!feeling) return;
    this.say(feeling.face);
    this.body.classList.add(`mood-${feeling.mood}`);
    setTimeout(() => {
      this.body.classList.remove(`mood-${feeling.mood}`);
      this.hideBubble();
    }, 2500);
  }

  async play(event) {
    const d = this.duration;
    switch (event.type) {
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
        if (event.item && item) {
          item.classList.add("grabbed");
          await wait(d);
          item.remove();
          this.items.delete(key);
        } else {
          this.say("?");
          await wait(d * 2);
          this.hideBubble();
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
