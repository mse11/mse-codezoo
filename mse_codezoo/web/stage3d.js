// The 3D stage: a low-poly jungle grid drawn with three.js (vendored, no network).
// Same interface as the 2D stage in stage.js: load(level, world), reset(), play(event),
// setSpeed(n), showFeeling(feeling), plus a `duration` in milliseconds.
// Models are built from simple shapes in code, so there are no asset files to load.

import * as THREE from "./vendor/three/three.module.min.js";

const ANGLE = { north: Math.PI, east: Math.PI / 2, south: 0, west: -Math.PI / 2 };
const STEP = { north: [0, -1], east: [1, 0], south: [0, 1], west: [-1, 0] };
const ITEM_EMOJI = { banana: "🍌", coconut: "🥥", rotten: "🤢" };
const reducedMotion =window.matchMedia("(prefers-reduced-motion: reduce)");

export function webglAvailable() {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(window.WebGLRenderingContext && (canvas.getContext("webgl2") || canvas.getContext("webgl")));
  } catch {
    return false;
  }
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const ease = (x) => (x < 0.5 ? 2 * x * x : 1 - (-2 * x + 2) ** 2 / 2);

function material(color, options = {}) {
  return new THREE.MeshStandardMaterial({ color, flatShading: true, roughness: 0.85, ...options });
}

function mesh(geometry, color, options) {
  const result = new THREE.Mesh(geometry, material(color, options));
  result.castShadow = true;
  result.receiveShadow = true;
  return result;
}

// --- models -----------------------------------------------------------------------

function makeMonkey() {
  const monkey = new THREE.Group();
  const fur = 0x8b5a2b;
  const face = 0xe8c39e;
  const body = mesh(new THREE.IcosahedronGeometry(0.26, 1), fur);
  body.scale.set(1, 1.1, 0.9);
  body.position.y = 0.32;
  const head = mesh(new THREE.IcosahedronGeometry(0.2, 1), fur);
  head.position.set(0, 0.08, 0.02);
  const muzzle = mesh(new THREE.IcosahedronGeometry(0.12, 1), face);
  muzzle.scale.set(1.2, 0.85, 0.8);
  muzzle.position.set(0, 0.04, 0.17);
  const eyes = [-0.07, 0.07].map((x) => {
    const eye = mesh(new THREE.SphereGeometry(0.03, 8, 6), 0x1a1a1a);
    eye.position.set(x, 0.13, 0.18);
    return eye;
  });
  const ears = [-0.2, 0.2].map((x) => {
    const ear = mesh(new THREE.IcosahedronGeometry(0.07, 0), face);
    ear.position.set(x, 0.1, 0);
    return ear;
  });
  const tail = mesh(new THREE.TorusGeometry(0.18, 0.035, 6, 12, Math.PI * 1.3), fur);
  tail.position.set(0, 0.35, -0.25);
  tail.rotation.y = Math.PI / 2;
  const feet = [-0.12, 0.12].map((x) => {
    const foot = mesh(new THREE.IcosahedronGeometry(0.08, 0), fur);
    foot.position.set(x, 0.06, 0.06);
    return foot;
  });
  const headGroup = new THREE.Group(); // pivots at the neck, for nods and head tilts
  headGroup.position.y = 0.6;
  headGroup.add(head, muzzle, ...eyes, ...ears);
  monkey.add(body, headGroup, tail, ...feet);
  monkey.userData.head = headGroup;
  monkey.rotation.order = "YXZ"; // turn first, so bending forward follows the facing
  return monkey;
}

function makeBanana(color = 0xf4d03f) {
  const banana = new THREE.Group();
  const curve = mesh(new THREE.TorusGeometry(0.18, 0.06, 6, 10, Math.PI * 0.75), color);
  curve.rotation.set(Math.PI / 2, 0, Math.PI * 0.6);
  curve.position.y = 0.12;
  const tip = mesh(new THREE.ConeGeometry(0.03, 0.06, 5), 0x5d4037);
  tip.position.set(0.17, 0.12, 0.05);
  banana.add(curve, tip);
  return banana;
}

function makeCoconut() {
  const coconut = mesh(new THREE.IcosahedronGeometry(0.17, 1), 0x6d4c41);
  coconut.position.y = 0.17;
  return coconut;
}

function makeRock() {
  const rock = new THREE.Group();
  const big = mesh(new THREE.DodecahedronGeometry(0.38, 0), 0x8d8d86);
  big.scale.set(1, 0.85, 1);
  big.position.y = 0.3;
  const small = mesh(new THREE.DodecahedronGeometry(0.16, 0), 0x77776f);
  small.position.set(0.28, 0.12, 0.2);
  rock.add(big, small);
  return rock;
}

function makeItem(noun) {
  if (noun === "banana") return makeBanana();
  if (noun === "rotten") return makeBanana(0x6b5b2a);
  if (noun === "coconut") return makeCoconut();
  const gem = mesh(new THREE.OctahedronGeometry(0.15, 0), 0x4fc3f7);
  gem.position.y = 0.2;
  return gem;
}

function makePlant(seed) {
  const plant = new THREE.Group();
  const leaves = 3 + (seed % 3);
  for (let i = 0; i < leaves; i++) {
    const leaf = mesh(new THREE.ConeGeometry(0.08, 0.5, 4), i % 2 ? 0x2e7d32 : 0x388e3c);
    leaf.rotation.z = 0.5;
    leaf.rotation.y = (i / leaves) * Math.PI * 2;
    leaf.position.y = 0.2;
    const holder = new THREE.Group();
    holder.add(leaf);
    holder.rotation.y = (i / leaves) * Math.PI * 2;
    plant.add(holder);
  }
  return plant;
}

function makeFlag() {
  const flag = new THREE.Group();
  const ring = mesh(new THREE.TorusGeometry(0.36, 0.035, 6, 24), 0xffd54f);
  ring.rotation.x = Math.PI / 2;
  ring.position.y = 0.02;
  const pole = mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.8, 6), 0xeeeeee);
  pole.position.set(0.3, 0.4, -0.3);
  const cloth = mesh(new THREE.ConeGeometry(0.14, 0.3, 3), 0xe53935);
  cloth.rotation.z = -Math.PI / 2;
  cloth.position.set(0.44, 0.68, -0.3);
  flag.add(ring, pole, cloth);
  return flag;
}

// Squares the animal must reach, for a goal flag.
export function reachTargets(goal) {
  if (!goal) return [];
  if (goal.type === "reach") return [goal.at];
  if (goal.type === "all") return goal.goals.flatMap(reachTargets);
  return [];
}

// --- stage ------------------------------------------------------------------------

export class Stage3D {
  constructor(container) {
    this.container = container;
    this.duration = 250;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.domElement.className = "stage-canvas";
    this.overlay = document.createElement("div");
    this.overlay.className = "stage-overlay";
    this.bubble = document.createElement("div");
    this.bubble.className = "bubble3d";
    this.bubble.hidden = true;
    this.mood = document.createElement("div");
    this.mood.className = "mood3d";
    this.mood.hidden = true;
    this.overlay.append(this.bubble, this.mood);

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100);
    this.scene.add(new THREE.HemisphereLight(0xfff8e1, 0x2e4d2e, 1.6));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(-4, 9, 6);
    sun.castShadow = true;
    sun.shadow.mapSize.set(1024, 1024);
    this.sun = sun;
    this.scene.add(sun, sun.target);

    this.tweens = new Set();
    this.clock = new THREE.Clock();
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.loop = this.loop.bind(this);
  }

  attach() {
    this.container.replaceChildren(this.renderer.domElement, this.overlay);
    this.container.classList.add("stage-3d");
    this.resizeObserver.observe(this.container);
    this.running = true;
    requestAnimationFrame(this.loop);
  }

  detach() {
    this.running = false;
    this.resizeObserver.disconnect();
    this.container.classList.remove("stage-3d");
  }

  setSpeed(level) {
    this.duration = [700, 450, 250, 140, 60][level - 1] ?? 250;
  }

  load(level, world, goal) {
    this.level = level;
    this.world = world || level.world;
    this.targets = reachTargets(goal || level.goal);
    this.reset();
  }

  reset() {
    if (!this.running) this.attach();
    const { pack } = this.level;
    const world = this.world;
    if (this.board) this.scene.remove(this.board);
    this.tweens.clear();
    this.nudged = null;
    const board = new THREE.Group();
    const [width, height] = world.size;
    this.width = width;
    this.height = height;

    const ground = mesh(new THREE.BoxGeometry(width + 0.6, 0.3, height + 0.6), 0x3e6b2f);
    ground.position.set((width - 1) / 2, -0.2, (height - 1) / 2);
    board.add(ground);
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const tile = mesh(new THREE.BoxGeometry(0.96, 0.1, 0.96), (x + y) % 2 ? 0x7cb342 : 0x8bc34a);
        tile.position.set(x, -0.05, y);
        board.add(tile);
      }
    }
    // a few plants around the edge, placed the same way every time
    for (let i = 0; i < width + height; i++) {
      const plant = makePlant(i);
      const side = i % 4;
      const along = (i * 7) % Math.max(width, height);
      const x = side === 0 ? -0.75 : side === 1 ? width - 0.25 : Math.min(along, width - 1);
      const z = side === 2 ? -0.75 : side === 3 ? height - 0.25 : Math.min(along, height - 1);
      plant.position.set(x, 0, z);
      plant.scale.setScalar(0.8 + ((i * 13) % 5) / 10);
      board.add(plant);
    }
    for (const [x, y] of world.walls) {
      const rock = makeRock();
      rock.position.set(x, 0, y);
      rock.rotation.y = (x * 3 + y * 5) % 6;
      board.add(rock);
    }
    this.items = new Map();
    for (const [x, y, tile] of world.items) {
      const item = makeItem(pack.items[tile]);
      item.position.set(x, 0, y);
      item.userData.baseY = 0;
      board.add(item);
      this.items.set(`${x},${y}`, item);
    }
    for (const [x, y] of this.targets) {
      const flag = makeFlag();
      flag.position.set(x, 0, y);
      board.add(flag);
    }
    this.monkey = makeMonkey();
    board.add(this.monkey);
    this.scene.add(board);
    this.board = board;

    this.position = [...world.position];
    this.facing = world.facing;
    this.monkey.position.set(this.position[0], 0, this.position[1]);
    this.monkey.rotation.y = ANGLE[this.facing];
    this.hideBubble();
    this.mood.hidden = true;
    this.placeCamera();
    this.resize();
  }

  // Fit the whole board in view for the current window shape, seen from above at an angle.
  placeCamera() {
    if (!this.width) return;
    const cx = (this.width - 1) / 2;
    const cz = (this.height - 1) / 2;
    const aspect = this.camera.aspect || 1.6;
    const vertical = THREE.MathUtils.degToRad(this.camera.fov) / 2;
    const horizontal = Math.atan(Math.tan(vertical) * aspect);
    const fitWidth = (this.width + 2) / 2 / Math.tan(horizontal);
    const fitDepth = (this.height + 1.6) / 2 / Math.tan(vertical) / 1.15;
    const distance = Math.max(fitWidth, fitDepth, 3.4);
    const elevation = 0.95; // radians above the ground
    this.camera.position.set(cx, distance * Math.sin(elevation) + 0.4, cz + distance * Math.cos(elevation));
    this.camera.lookAt(cx, 0.25, cz);
    this.sun.target.position.set(cx, 0, cz);
    const span = Math.max(this.width, this.height) + 2;
    const shadow = this.sun.shadow.camera;
    shadow.left = shadow.bottom = -span;
    shadow.right = shadow.top = span;
    shadow.updateProjectionMatrix();
  }

  resize() {
    const { clientWidth: width, clientHeight: height } = this.container;
    if (!width || !height) return;
    this.size = `${width}x${height}`;
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.placeCamera();
  }

  loop() {
    if (!this.running) return;
    // backup for a missed ResizeObserver report: a stale size stretches and shifts the picture
    const { clientWidth, clientHeight } = this.container;
    if (`${clientWidth}x${clientHeight}` !== this.size) this.resize();
    const now = performance.now();
    for (const tween of [...this.tweens]) {
      const progress = Math.min(1, (now - tween.start) / tween.duration);
      tween.step(ease(progress), progress);
      if (progress >= 1) {
        this.tweens.delete(tween);
        tween.done();
      }
    }
    if (this.monkey && !reducedMotion.matches && this.tweens.size === 0) {
      const t = this.clock.getElapsedTime();
      this.monkey.userData.head.rotation.z = Math.sin(t * 1.6) * 0.05;
    }
    for (const item of this.items?.values() || []) {
      if (!reducedMotion.matches) item.rotation.y += 0.01;
    }
    this.renderer.render(this.scene, this.camera);
    this.positionOverlay();
    requestAnimationFrame(this.loop);
  }

  tween(duration, step) {
    const time = reducedMotion.matches ? Math.min(duration, 60) : duration;
    return new Promise((done) => this.tweens.add({ start: performance.now(), duration: time, step, done }));
  }

  positionOverlay() {
    if (!this.monkey) return;
    const point = this.monkey.position.clone();
    point.y += 1.05;
    point.project(this.camera);
    const x = ((point.x + 1) / 2) * this.container.clientWidth;
    const y = ((1 - point.y) / 2) * this.container.clientHeight;
    for (const node of [this.bubble, this.mood]) {
      node.style.left = `${x}px`;
      node.style.top = `${y}px`;
    }
  }

  say(text) {
    this.bubble.textContent = text;
    this.bubble.hidden = false;
  }

  hideBubble() {
    this.bubble.hidden = true;
  }

  showFeeling(feeling) {
    if (!feeling || !this.monkey) return;
    this.mood.textContent = feeling.face;
    this.mood.hidden = false;
    const jumps = feeling.mood === "proud" ? 3 : feeling.mood === "happy" ? 1 : 0;
    const monkey = this.monkey;
    if (jumps) {
      this.tween(500 * jumps, (_, p) => {
        monkey.position.y = Math.abs(Math.sin(p * Math.PI * jumps)) * 0.35;
        monkey.rotation.y = ANGLE[this.facing] + (feeling.mood === "proud" ? p * Math.PI * 2 : 0);
      });
    } else if (feeling.mood === "puzzled" || feeling.mood === "confused") {
      const head = monkey.userData.head;
      this.tween(900, (_, p) => (head.rotation.z = Math.sin(p * Math.PI) * 0.35));
    }
  }

  async play(event) {
    const d = this.duration;
    const monkey = this.monkey;
    this.mood.hidden = true;
    switch (event.type) {
      case "move": {
        const [fx, fz] = this.position;
        const [tx, tz] = event.to;
        this.position = event.to;
        const left = this.nudged; // the item the monkey stood by goes back to its square
        this.nudged = null;
        if (left && this.items.get(left.key) === left.item) {
          const { item, x, z } = left;
          const sx = item.position.x;
          const sz = item.position.z;
          this.tween(d, (e) => {
            item.position.x = sx + (x - sx) * e;
            item.position.z = sz + (z - sz) * e;
          });
        }
        await this.tween(d, (e, p) => {
          monkey.position.x = fx + (tx - fx) * e;
          monkey.position.z = fz + (tz - fz) * e;
          monkey.position.y = Math.sin(p * Math.PI) * 0.18;
        });
        // an item under the monkey would be hidden inside it: slide it out in front of its feet
        const here = this.items.get(`${tx},${tz}`);
        if (here) {
          this.nudged = { key: `${tx},${tz}`, item: here, x: tx, z: tz };
          const [dx, dz] = STEP[this.facing];
          const sx = here.position.x;
          const sz = here.position.z;
          await this.tween(Math.max(d * 0.5, 120), (e) => {
            here.position.x = sx + (tx + dx * 0.42 - sx) * e;
            here.position.z = sz + (tz + dz * 0.42 - sz) * e;
          });
        }
        break;
      }
      case "turn": {
        const from = monkey.rotation.y;
        let delta = (ANGLE[event.facing] - from) % (Math.PI * 2);
        if (delta > Math.PI) delta -= Math.PI * 2;
        if (delta < -Math.PI) delta += Math.PI * 2;
        this.facing = event.facing;
        await this.tween(d * 0.8, (e) => (monkey.rotation.y = from + delta * e));
        break;
      }
      case "grab": {
        const key = event.at.join(",");
        const item = this.items.get(key);
        if (event.item && item) {
          // bend down, lift the item high above the head, show "+1", then tuck it away;
          // slow enough to see even at the fastest speed
          const slow = Math.max(d, 260);
          const start = item.position.clone();
          await this.tween(slow * 0.5, (e) => (monkey.rotation.x = e * 0.45));
          await this.tween(slow, (e) => {
            monkey.rotation.x = 0.45 * (1 - e);
            item.position.x = start.x + (monkey.position.x - start.x) * e;
            item.position.z = start.z + (monkey.position.z - start.z) * e;
            item.position.y = e * 1.25;
            item.scale.setScalar(1 + e * 0.4);
          });
          this.say(`+1 ${ITEM_EMOJI[this.level.pack.items[event.item]] || "⭐"}`);
          await wait(slow * 1.2);
          this.hideBubble();
          await this.tween(slow * 0.5, (e) => {
            item.position.y = 1.25 - e * 0.7;
            item.scale.setScalar(1.4 * (1 - e));
          });
          item.parent?.remove(item);
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
      case "bump": {
        const x = monkey.position.x;
        const z = monkey.position.z;
        const [dx, dz] = { north: [0, -1], east: [1, 0], south: [0, 1], west: [-1, 0] }[this.facing];
        await this.tween(650, (_, p) => {
          const push = Math.sin(p * Math.PI) * 0.25 * (1 - p);
          monkey.position.x = x + dx * push;
          monkey.position.z = z + dz * push;
          monkey.rotation.z = Math.sin(p * Math.PI * 6) * 0.15 * (1 - p);
        });
        break;
      }
      case "sense": {
        const head = monkey.userData.head;
        await this.tween(d * 0.8, (_, p) => (head.rotation.x = Math.sin(p * Math.PI) * 0.35));
        break;
      }
      default:
        await wait(d / 2);
    }
  }
}
