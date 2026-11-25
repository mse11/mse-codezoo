// The 3D stage: a low-poly jungle grid drawn with three.js (vendored, no network).
// Same interface as the 2D stage in stage.js: load(level, world), reset(), play(event),
// setSpeed(n), showFeeling(feeling), plus a `duration` in milliseconds.
// Models are built from simple shapes in code, so there are no asset files to load.

import * as THREE from "./vendor/three/three.module.min.js";

const ANGLE = { north: Math.PI, east: Math.PI / 2, south: 0, west: -Math.PI / 2 };
const STEP = { north: [0, -1], east: [1, 0], south: [0, 1], west: [-1, 0] };
import { EMOJI as ITEM_EMOJI, missBubble } from "./stage.js";

// ground colours per world: [tile, other tile, edge]
const GROUND = {
  monkey: [0x7cb342, 0x8bc34a, 0x3e6b2f],
  penguin: [0xe3f2fd, 0xf5fbff, 0x90a4ae],
  beaver: [0x9ccc65, 0xaed581, 0x5d4037],
  fox: [0x558b2f, 0x689f38, 0x33691e],
  octopus: [0xffe0b2, 0xffecb3, 0x0277bd],
  bee: [0xaed581, 0xc5e1a5, 0x689f38],
};
const ARMS = [[0, -1], [1, -1], [1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0], [-1, -1]];
const QUIET = new Set(["task", "thread", "lock", "file", "input", "import", "call", "return", "print"]);
// less motion: the system setting or "Look and feel" (look.js sets data-motion on <html>)
const reducedMotion = { get matches() { return document.documentElement.dataset.motion === "reduce"; } };

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

// The other animals share the monkey's shape idea: a body, a head group that can nod, feet.
function makeAnimal(kind) {
  if (kind === "penguin") return makePenguin();
  if (kind === "beaver") return makeBeaver();
  if (kind === "fox") return makeFox();
  if (kind === "octopus") return makeOctopus();
  if (kind === "bee") return makeBee();
  return makeMonkey();
}

function makeOctopus() {
  const octopus = new THREE.Group();
  const skin = 0xd81b60;
  const legs = ARMS.map(([dx, dz]) => {
    const leg = mesh(new THREE.CylinderGeometry(0.035, 0.06, 0.32, 6), skin);
    leg.rotation.z = Math.PI / 2;
    leg.rotation.y = -Math.atan2(dz, dx);
    leg.position.set(dx * 0.17, 0.06, dz * 0.17);
    return leg;
  });
  const head = new THREE.Group();
  head.position.y = 0.32;
  const dome = mesh(new THREE.IcosahedronGeometry(0.25, 1), skin);
  dome.scale.set(1, 1.15, 1);
  head.add(dome, ...eyesAt(0.02, 0.22, 0.09));
  return finish(octopus, legs, head);
}

function makeBee() {
  const bee = new THREE.Group();
  const body = new THREE.Group();
  body.position.y = 0.45;
  [0, 1, 2].forEach((i) => {
    const band = mesh(new THREE.CylinderGeometry(0.17 - i * 0.02, 0.17 - i * 0.02, 0.12, 8), i % 2 ? 0x212121 : 0xffca28);
    band.rotation.x = Math.PI / 2;
    band.position.z = -0.1 - i * 0.11;
    body.add(band);
  });
  const wings = [-0.16, 0.16].map((x) => {
    const wing = mesh(new THREE.SphereGeometry(0.14, 8, 6), 0xe3f2fd, { transparent: true, opacity: 0.7 });
    wing.scale.set(0.4, 0.15, 1);
    wing.position.set(x, 0.65, -0.12);
    return wing;
  });
  const head = new THREE.Group();
  head.position.set(0, 0.47, 0.1);
  const skull = mesh(new THREE.IcosahedronGeometry(0.13, 1), 0x212121);
  head.add(skull, ...eyesAt(0.03, 0.11, 0.06));
  return finish(bee, [body, ...wings], head);
}

function finish(animal, parts, head) {
  animal.add(...parts, head);
  animal.userData.head = head;
  animal.rotation.order = "YXZ";
  return animal;
}

function eyesAt(y, z, spread = 0.07) {
  return [-spread, spread].map((x) => {
    const eye = mesh(new THREE.SphereGeometry(0.028, 8, 6), 0x1a1a1a);
    eye.position.set(x, y, z);
    return eye;
  });
}

function makePenguin() {
  const penguin = new THREE.Group();
  const body = mesh(new THREE.IcosahedronGeometry(0.27, 1), 0x263238);
  body.scale.set(0.9, 1.3, 0.85);
  body.position.y = 0.36;
  const belly = mesh(new THREE.IcosahedronGeometry(0.2, 1), 0xfafafa);
  belly.scale.set(0.8, 1.2, 0.5);
  belly.position.set(0, 0.33, 0.13);
  const feet = [-0.09, 0.09].map((x) => {
    const foot = mesh(new THREE.BoxGeometry(0.1, 0.03, 0.14), 0xffa000);
    foot.position.set(x, 0.02, 0.08);
    return foot;
  });
  const wings = [-0.25, 0.25].map((x) => {
    const wing = mesh(new THREE.BoxGeometry(0.04, 0.3, 0.14), 0x263238);
    wing.position.set(x, 0.38, 0);
    wing.rotation.z = x > 0 ? -0.25 : 0.25;
    return wing;
  });
  const head = new THREE.Group();
  head.position.y = 0.72;
  const skull = mesh(new THREE.IcosahedronGeometry(0.16, 1), 0x263238);
  const beak = mesh(new THREE.ConeGeometry(0.05, 0.14, 5), 0xffa000);
  beak.rotation.x = Math.PI / 2;
  beak.position.set(0, -0.02, 0.17);
  head.add(skull, beak, ...eyesAt(0.04, 0.13, 0.06));
  return finish(penguin, [body, belly, ...feet, ...wings], head);
}

function makeBeaver() {
  const beaver = new THREE.Group();
  const fur = 0x795548;
  const body = mesh(new THREE.IcosahedronGeometry(0.28, 1), fur);
  body.scale.set(1, 0.95, 1.1);
  body.position.y = 0.3;
  const tail = mesh(new THREE.BoxGeometry(0.22, 0.05, 0.36), 0x4e342e);
  tail.position.set(0, 0.08, -0.38);
  const feet = [-0.13, 0.13].map((x) => {
    const foot = mesh(new THREE.IcosahedronGeometry(0.07, 0), 0x4e342e);
    foot.position.set(x, 0.05, 0.1);
    return foot;
  });
  const head = new THREE.Group();
  head.position.y = 0.58;
  const skull = mesh(new THREE.IcosahedronGeometry(0.17, 1), fur);
  const nose = mesh(new THREE.SphereGeometry(0.04, 8, 6), 0x212121);
  nose.position.set(0, 0, 0.17);
  const teeth = mesh(new THREE.BoxGeometry(0.07, 0.06, 0.02), 0xfff8e1);
  teeth.position.set(0, -0.08, 0.15);
  const ears = [-0.12, 0.12].map((x) => {
    const ear = mesh(new THREE.SphereGeometry(0.04, 6, 4), 0x5d4037);
    ear.position.set(x, 0.13, -0.02);
    return ear;
  });
  head.add(skull, nose, teeth, ...ears, ...eyesAt(0.06, 0.13));
  return finish(beaver, [body, tail, ...feet], head);
}

function makeFox() {
  const fox = new THREE.Group();
  const fur = 0xef6c00;
  const body = mesh(new THREE.IcosahedronGeometry(0.24, 1), fur);
  body.scale.set(0.9, 0.9, 1.3);
  body.position.y = 0.32;
  const tail = mesh(new THREE.ConeGeometry(0.1, 0.45, 6), fur);
  tail.rotation.x = -Math.PI / 2.6;
  tail.position.set(0, 0.36, -0.42);
  const tip = mesh(new THREE.ConeGeometry(0.06, 0.14, 6), 0xfafafa);
  tip.rotation.x = -Math.PI / 2.6;
  tip.position.set(0, 0.47, -0.6);
  const legs = [-0.1, 0.1].map((x) => {
    const leg = mesh(new THREE.CylinderGeometry(0.035, 0.035, 0.18, 5), 0x3e2723);
    leg.position.set(x, 0.09, 0.08);
    return leg;
  });
  const head = new THREE.Group();
  head.position.set(0, 0.56, 0.18);
  const skull = mesh(new THREE.IcosahedronGeometry(0.15, 1), fur);
  const snout = mesh(new THREE.ConeGeometry(0.07, 0.18, 5), 0xfafafa);
  snout.rotation.x = Math.PI / 2;
  snout.position.set(0, -0.03, 0.16);
  const ears = [-0.08, 0.08].map((x) => {
    const ear = mesh(new THREE.ConeGeometry(0.05, 0.13, 4), fur);
    ear.position.set(x, 0.16, 0);
    return ear;
  });
  head.add(skull, snout, ...ears, ...eyesAt(0.04, 0.12, 0.06));
  return finish(fox, [body, tail, tip, ...legs], head);
}

function makeTree() {
  const tree = new THREE.Group();
  const trunk = mesh(new THREE.CylinderGeometry(0.08, 0.12, 0.9, 6), 0x795548);
  trunk.position.y = 0.45;
  const crown = mesh(new THREE.IcosahedronGeometry(0.42, 0), 0x2e7d32);
  crown.position.y = 1.05;
  tree.add(trunk, crown);
  return tree;
}

function makeLog(color) {
  const log = mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.5, 8), color);
  log.rotation.z = Math.PI / 2;
  log.position.y = 0.1;
  const group = new THREE.Group();
  group.add(log);
  return group;
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

function makeBlob(color, scale = [1, 1, 1], size = 0.15) {
  const group = new THREE.Group();
  const blob = mesh(new THREE.IcosahedronGeometry(size, 1), color);
  blob.scale.set(...scale);
  blob.position.y = size * scale[1] + 0.02;
  group.add(blob);
  return group;
}

function makeItem(noun) {
  if (noun === "banana") return makeBanana();
  if (noun === "rotten") return makeBanana(0x6b5b2a);
  if (noun === "coconut") return makeCoconut();
  if (noun === "fish") {
    const fish = makeBlob(0x4fc3f7, [1.5, 0.7, 0.6]);
    const tail = mesh(new THREE.ConeGeometry(0.08, 0.14, 4), 0x0288d1);
    tail.rotation.z = Math.PI / 2;
    tail.position.set(-0.28, 0.12, 0);
    fish.add(tail);
    return fish;
  }
  if (noun === "pebble") return makeBlob(0x9e9e9e, [1.2, 0.6, 1]);
  if (noun === "shell") return makeBlob(0xffccbc, [1.2, 0.5, 1]);
  if (noun === "pearl") return makeBlob(0xfafafa, [1, 1, 1], 0.1);
  if (noun === "jellyfish") return makeBlob(0xce93d8, [1, 0.8, 1], 0.17);
  if (noun === "flower" || noun === "clover") {
    const group = new THREE.Group();
    const stem = mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.25, 5), 0x388e3c);
    stem.position.y = 0.12;
    const bloom = mesh(new THREE.IcosahedronGeometry(0.1, 0), noun === "flower" ? 0xffeb3b : 0x43a047);
    bloom.position.y = 0.28;
    group.add(stem, bloom);
    return group;
  }
  if (noun === "nettle") return makeBlob(0x2e7d32, [0.8, 1.4, 0.8]);
  if (noun === "crab") return makeBlob(0xe53935, [1.4, 0.6, 1]);
  if (noun === "egg") return makeBlob(0xfffde7, [0.8, 1.1, 0.8]);
  if (noun === "berry") return makeBlob(0x5e35b1, [1, 1, 1], 0.12);
  if (noun === "trap") return makeBlob(0x616161, [1.4, 0.3, 1.4]);
  if (noun === "oak") return makeLog(0x8d6e63);
  if (noun === "pine") return makeLog(0xbcaaa4);
  if (noun === "birch") return makeLog(0xeeeeee);
  if (noun === "stick") return makeLog(0x6d4c41);
  if (noun === "leaf") return makeBlob(0x66bb6a, [1.3, 0.2, 0.8]);
  if (noun === "thorn") {
    const thorn = mesh(new THREE.ConeGeometry(0.08, 0.3, 5), 0x558b2f);
    thorn.position.y = 0.15;
    return thorn;
  }
  if (noun === "mushroom") {
    const group = new THREE.Group();
    const stem = mesh(new THREE.CylinderGeometry(0.04, 0.05, 0.16, 6), 0xfff8e1);
    stem.position.y = 0.08;
    const cap = mesh(new THREE.ConeGeometry(0.16, 0.12, 8), 0xc62828);
    cap.position.y = 0.2;
    group.add(stem, cap);
    return group;
  }
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

// --- game mode objects: doors, switches, power-ups, and the rings of playing together ---

// a wooden gate between two posts; the plank sinks into the ground when it opens
function makeDoor() {
  const door = new THREE.Group();
  for (const side of [-0.4, 0.4]) {
    const post = mesh(new THREE.BoxGeometry(0.12, 0.9, 0.12), 0x6d4c41);
    post.position.set(side, 0.45, 0);
    door.add(post);
  }
  const plank = mesh(new THREE.BoxGeometry(0.68, 0.7, 0.1), 0xa1887f);
  plank.position.y = 0.4;
  const band = mesh(new THREE.BoxGeometry(0.7, 0.08, 0.12), 0x5d4037);
  band.position.y = 0.55;
  const gate = new THREE.Group();
  gate.add(plank, band);
  door.add(gate);
  door.userData.gate = gate;
  return door;
}

// a round plate on the ground with a lever that flips over
function makeSwitch() {
  const group = new THREE.Group();
  const plate = mesh(new THREE.CylinderGeometry(0.3, 0.34, 0.06, 16), 0x90a4ae);
  plate.position.y = 0.03;
  const lever = new THREE.Group();
  const stick = mesh(new THREE.CylinderGeometry(0.035, 0.035, 0.38, 6), 0x546e7a);
  stick.position.y = 0.19;
  const knob = mesh(new THREE.SphereGeometry(0.08, 10, 8), 0xe53935);
  knob.position.y = 0.4;
  lever.add(stick, knob);
  lever.position.y = 0.05;
  lever.rotation.z = -0.5;
  group.add(plate, lever);
  group.userData.lever = lever;
  group.userData.knob = knob;
  return group;
}

// a glowing star that spins above its square
function makePower() {
  const group = new THREE.Group();
  const star = mesh(new THREE.OctahedronGeometry(0.2, 0), 0xffd600, { emissive: 0xffab00, emissiveIntensity: 0.7 });
  star.position.y = 0.4;
  group.add(star);
  return group;
}

// the coloured ring under each animal when children play together (numbers 1-4)
const PLAYER_COLOURS = [0xff7043, 0x42a5f5, 0x66bb6a, 0xab47bc];
function makePlayerRing(number) {
  const ring = mesh(new THREE.TorusGeometry(0.38, 0.05, 6, 24), PLAYER_COLOURS[(number - 1) % PLAYER_COLOURS.length]);
  ring.rotation.x = Math.PI / 2;
  ring.position.y = 0.03;
  return ring;
}

// Squares the animal must reach, for a goal flag.
// Game mode critters (game.js): an animal of the zoo when the kind is one, else a little
// creature of simple shapes. Kinds are the program's own words (`Guard(..., kind="ghost")`).
const ANIMALS = new Set(["monkey", "penguin", "beaver", "fox", "octopus", "bee"]);
const CRITTER_COLOURS = [0xe53935, 0x8e24aa, 0x1e88e5, 0xfb8c00, 0x00897b, 0x6d4c41, 0xc0ca33];

function makeCritter(kind) {
  if (ANIMALS.has(kind)) {
    const animal = makeAnimal(kind);
    animal.scale.setScalar(0.85);
    return animal;
  }
  if (kind === "guard") return makeGuard();
  if (kind === "ghost") return makeGhost();
  let hash = 0;
  for (const char of kind || "") hash = (hash * 31 + char.charCodeAt(0)) % 1000;
  return makeBeetle(CRITTER_COLOURS[hash % CRITTER_COLOURS.length]);
}

// a small green crocodile: long body, snout, eyes on top, four feet
function makeGuard() {
  const guard = new THREE.Group();
  const skin = 0x2e7d32;
  const body = mesh(new THREE.BoxGeometry(0.34, 0.2, 0.62), skin);
  body.position.y = 0.16;
  const tail = mesh(new THREE.ConeGeometry(0.1, 0.4, 5), skin);
  tail.rotation.x = -Math.PI / 2;
  tail.position.set(0, 0.14, -0.48);
  const feet = [[-0.17, 0.2], [0.17, 0.2], [-0.17, -0.2], [0.17, -0.2]].map(([x, z]) => {
    const foot = mesh(new THREE.BoxGeometry(0.1, 0.08, 0.12), 0x1b5e20);
    foot.position.set(x, 0.04, z);
    return foot;
  });
  const head = new THREE.Group();
  head.position.set(0, 0.2, 0.3);
  const snout = mesh(new THREE.BoxGeometry(0.26, 0.12, 0.3), 0x388e3c);
  snout.position.set(0, -0.02, 0.14);
  const teeth = mesh(new THREE.BoxGeometry(0.22, 0.03, 0.24), 0xfafafa);
  teeth.position.set(0, -0.08, 0.15);
  head.add(snout, teeth, ...eyesAt(0.08, 0.02, 0.08));
  return finish(guard, [body, tail, ...feet], head);
}

function makeGhost() {
  const ghost = new THREE.Group();
  const body = mesh(new THREE.CylinderGeometry(0.18, 0.26, 0.5, 10), 0xf5f5f5, { transparent: true, opacity: 0.85 });
  body.position.y = 0.3;
  const head = new THREE.Group();
  head.position.y = 0.55;
  const top = mesh(new THREE.SphereGeometry(0.18, 10, 8), 0xf5f5f5, { transparent: true, opacity: 0.85 });
  head.add(top, ...eyesAt(0.04, 0.15, 0.06));
  return finish(ghost, [body], head);
}

function makeBeetle(colour) {
  const beetle = new THREE.Group();
  const shell = mesh(new THREE.IcosahedronGeometry(0.24, 1), colour);
  shell.scale.set(1, 0.6, 1.2);
  shell.position.y = 0.17;
  const spots = [[-0.09, 0.05], [0.09, -0.06]].map(([x, z]) => {
    const spot = mesh(new THREE.SphereGeometry(0.05, 8, 6), 0x212121);
    spot.position.set(x, 0.3, z);
    return spot;
  });
  const legs = [-0.12, 0, 0.12].flatMap((z) =>
    [-0.24, 0.24].map((x) => {
      const leg = mesh(new THREE.BoxGeometry(0.1, 0.03, 0.03), 0x212121);
      leg.position.set(x, 0.05, z);
      return leg;
    }),
  );
  const head = new THREE.Group();
  head.position.set(0, 0.16, 0.28);
  head.add(mesh(new THREE.IcosahedronGeometry(0.11, 0), 0x212121), ...eyesAt(0.04, 0.08, 0.05));
  return finish(beetle, [shell, ...spots, ...legs], head);
}

// the shortest way round from one angle to another
function nearestAngle(from, to) {
  const turn = ((((to - from + Math.PI) % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI)) - Math.PI;
  return from + turn;
}

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
    this.outfit = document.createElement("div");
    this.outfit.className = "outfit3d";
    this.outfit.hidden = true;
    this.overlay.append(this.bubble, this.mood, this.outfit);

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
    this.hidden = false;
    const board = new THREE.Group();
    const [width, height] = world.size;
    this.width = width;
    this.height = height;

    const [tileA, tileB, edge] = GROUND[pack.id] || GROUND.monkey;
    const ground = mesh(new THREE.BoxGeometry(width + 0.6, 0.3, height + 0.6), edge);
    ground.position.set((width - 1) / 2, -0.2, (height - 1) / 2);
    board.add(ground);
    const terrain = new Map((world.terrain || []).map(([x, y, kind]) => [`${x},${y}`, kind]));
    this.tiles = new Map();
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const kind = terrain.get(`${x},${y}`);
        const tile = this.makeTile(kind, (x + y) % 2 ? tileA : tileB);
        tile.position.set(x, kind === "~" ? -0.08 : -0.05, y); // water sits a little lower
        board.add(tile);
        this.tiles.set(`${x},${y}`, tile);
        if (kind === "t") {
          const tree = makeTree();
          tree.position.set(x, 0, y);
          board.add(tree);
        }
        if (kind === "o") {
          const post = mesh(new THREE.CylinderGeometry(0.05, 0.08, 0.5, 6), 0xb71c1c);
          post.position.set(x + 0.35, 0.25, y - 0.35);
          const lamp = mesh(new THREE.SphereGeometry(0.09, 8, 6), 0xffeb3b, { emissive: 0xffc107, emissiveIntensity: 0.6 });
          lamp.position.set(x + 0.35, 0.55, y - 0.35);
          board.add(post, lamp);
        }
      }
    }
    // a few plants around the edge, placed the same way every time
    for (let i = 0; pack.id !== "penguin" && i < width + height; i++) {
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
      const up = terrain.get(`${x},${y}`) === "t" ? 1.3 : 0; // fruit grows at the top of a tree
      item.position.set(x, up, y);
      item.userData.baseY = up;
      board.add(item);
      this.items.set(`${x},${y}`, item);
    }
    for (const [x, y] of this.targets) {
      const flag = makeFlag();
      flag.position.set(x, 0, y);
      board.add(flag);
    }
    this.monkey = makeAnimal(pack.id);
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

  makeTile(kind, color) {
    switch (kind) {
      case "~":
        return mesh(new THREE.BoxGeometry(0.98, 0.06, 0.98), 0x4fa3e0, { transparent: true, opacity: 0.85, roughness: 0.2 });
      case "-":
        return mesh(new THREE.BoxGeometry(0.96, 0.1, 0.96), 0x81d4fa, { transparent: true, opacity: 0.7, roughness: 0.1 });
      case "o":
        return mesh(new THREE.BoxGeometry(0.96, 0.1, 0.96), 0xf8bbd0);
      case "=":
        return mesh(new THREE.BoxGeometry(0.96, 0.12, 0.96), 0xa1887f);
      default:
        return mesh(new THREE.BoxGeometry(0.96, 0.1, 0.96), color);
    }
  }

  // What the animal wears (from the habitat): an emoji drawn above its head.
  setOutfit(emoji) {
    this.outfitText = emoji || "";
    this.outfit.textContent = this.outfitText;
    this.outfit.hidden = !this.outfitText;
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
    for (const power of this.powers?.values() || []) {
      if (!reducedMotion.matches) power.rotation.y += 0.03;
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
    // the words go above a face (🤔); with no room above it on a short stage, beside it
    const both = !this.bubble.hidden && !this.mood.hidden;
    this.bubble.classList.toggle("beside", both && y - this.mood.offsetHeight - this.bubble.offsetHeight < 4);
    const top = this.monkey.position.clone();
    top.y += 0.85;
    top.project(this.camera);
    this.outfit.style.left = `${((top.x + 1) / 2) * this.container.clientWidth}px`;
    this.outfit.style.top = `${((1 - top.y) / 2) * this.container.clientHeight}px`;
  }

  say(text) {
    this.bubble.textContent = text;
    this.bubble.hidden = false;
  }

  hideBubble() {
    this.bubble.hidden = true;
  }

  // where the animal is on the screen (for "+1" texts and confetti, fun.js)
  animalPoint() {
    if (!this.monkey) return null;
    const point = this.monkey.position.clone();
    point.y += 0.45;
    point.project(this.camera);
    const box = this.container.getBoundingClientRect();
    return { x: box.left + ((point.x + 1) / 2) * box.width, y: box.top + ((1 - point.y) / 2) * box.height };
  }

  // the world square under a tap or click ([x, y]), or null off the board: a ray from the
  // camera through the point, onto the ground (the world editor in 3D)
  squareAt(event) {
    if (!this.board || !this.width) return null;
    const box = this.renderer.domElement.getBoundingClientRect();
    const pointer = new THREE.Vector2(
      ((event.clientX - box.left) / box.width) * 2 - 1,
      -((event.clientY - box.top) / box.height) * 2 + 1,
    );
    const ray = new THREE.Raycaster();
    ray.setFromCamera(pointer, this.camera);
    const ground = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
    const hit = new THREE.Vector3();
    if (!ray.ray.intersectPlane(ground, hit)) return null;
    const local = this.board.worldToLocal(hit.clone());
    const x = Math.round(local.x);
    const y = Math.round(local.z);
    return x >= 0 && y >= 0 && x < this.width && y < this.height ? [x, y] : null;
  }

  hitAnimal(event) {
    const point = this.animalPoint();
    if (!point) return false;
    const reach = Math.max(36, this.container.clientWidth / Math.max(this.width || 6, 4) / 1.6);
    return Math.hypot(event.clientX - point.x, event.clientY - point.y) < reach;
  }

  // poked while nothing runs: a hop and a word; every tenth poke is a spinning dance
  poke(text, { dance = false } = {}) {
    if (!this.monkey) return;
    clearTimeout(this.pokeTimer);
    this.say(text);
    const monkey = this.monkey;
    const base = ANGLE[this.facing];
    const y = monkey.position.y;
    if (dance) {
      this.tween(2200, (_, p) => {
        monkey.position.y = y + Math.abs(Math.sin(p * Math.PI * 4)) * 0.4;
        monkey.rotation.y = base + p * Math.PI * 4;
        monkey.rotation.z = Math.sin(p * Math.PI * 8) * 0.25;
      }).then(() => {
        monkey.rotation.set(0, base, 0);
        monkey.position.y = y;
      });
    } else {
      this.tween(450, (_, p) => {
        monkey.position.y = y + Math.sin(p * Math.PI) * 0.35;
        monkey.scale.setScalar(1 + Math.sin(p * Math.PI) * 0.12);
      }).then(() => {
        monkey.position.y = y;
        monkey.scale.setScalar(1);
      });
    }
    this.pokeTimer = setTimeout(() => this.hideBubble(), dance ? 2600 : 1600);
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

  // grab() found nothing: stretch towards the item and pull back, turn to look at it,
  // look up into the tree, or shrug; a pulsing ring marks where the item really is
  async missed(event) {
    const animal = this.monkey;
    const d = Math.max(this.duration, 220);
    const near = event.near || "none";
    let ring = null;
    if (event.to) {
      ring = new THREE.Mesh(
        new THREE.RingGeometry(0.3, 0.42, 24),
        new THREE.MeshBasicMaterial({ color: 0xffeb3b, transparent: true, opacity: 0.8, side: THREE.DoubleSide }),
      );
      ring.rotation.x = -Math.PI / 2;
      ring.position.set(event.to[0], 0.03, event.to[1]);
      this.board.add(ring);
    }
    this.say(missBubble(near));
    const pulse = (p) => ring && (ring.material.opacity = 0.35 + 0.45 * Math.abs(Math.sin(p * Math.PI * 3)));
    const [x, z] = this.position;
    if (near === "ahead" && event.to) {
      // lean and stretch towards it... and it is out of reach
      const [tx, tz] = event.to;
      const far = Math.max(Math.hypot(tx - x, tz - z), 1);
      const dx = ((tx - x) / far) * 0.35;
      const dz = ((tz - z) / far) * 0.35;
      await this.tween(d * 1.2, (e, p) => {
        animal.rotation.x = e * 0.5;
        animal.position.x = x + dx * e;
        animal.position.z = z + dz * e;
        pulse(p);
      });
      await this.tween(d, (e, p) => {
        animal.rotation.x = 0.5 * (1 - e);
        animal.position.x = x + dx * (1 - e);
        animal.position.z = z + dz * (1 - e);
        pulse(p);
      });
    } else if (event.to && near !== "up") {
      // turn to look at it, then back
      const [tx, tz] = event.to;
      const from = animal.rotation.y;
      let delta = (Math.atan2(tx - x, tz - z) - from) % (Math.PI * 2);
      if (delta > Math.PI) delta -= Math.PI * 2;
      if (delta < -Math.PI) delta += Math.PI * 2;
      await this.tween(d * 1.2, (e, p) => {
        animal.rotation.y = from + delta * e;
        pulse(p);
      });
      await this.tween(d * 1.2, (_, p) => pulse(p));
      await this.tween(d, (e) => (animal.rotation.y = from + delta * (1 - e)));
    } else if (near === "up") {
      const head = animal.userData.head;
      await this.tween(d * 2.4, (_, p) => {
        head.rotation.x = -Math.sin(p * Math.PI) * 0.7;
        pulse(p);
      });
    } else {
      // a shrug: a little hop and a shake of the head
      const head = animal.userData.head;
      await this.tween(d * 2.4, (_, p) => {
        animal.position.y = Math.sin(p * Math.PI) * 0.12;
        head.rotation.z = Math.sin(p * Math.PI * 4) * 0.3 * (1 - p);
      });
    }
    this.hideBubble();
    if (ring) this.board.remove(ring);
  }

  // --- game mode (game.js) -----------------------------------------------------------
  // The page hands over the whole game after every tick; the animal and the critters
  // glide to their new squares in less than a tick, so nothing ever lags behind.

  loadGame(game) {
    this.load({ pack: game.pack, world: game.world, goal: null });
    this.critters = new Map();
    this.others = new Map(); // the other players' animals, by number
    this.rings = new Map();
    this.doors = new Map();
    this.switches = new Map();
    this.powers = new Map();
    // the world's doors, switches and power-ups as they are before the game starts
    for (const object of game.world.objects || []) {
      const key = object.at.join(",");
      if (object.type === "door") this.placeObject(this.doors, key, makeDoor(), object.at).userData.open = false;
      if (object.type === "switch") this.placeObject(this.switches, key, makeSwitch(), object.at);
      if (object.type === "power") this.placeObject(this.powers, key, makePower(), object.at);
      if (object.type === "door" && object.open) {
        const door = this.doors.get(key);
        door.userData.open = true;
        door.userData.gate.position.y = -0.75;
      }
    }
  }

  placeObject(map, key, model, [x, y]) {
    model.position.set(x, 0, y);
    this.board.add(model);
    map.set(key, model);
    return model;
  }

  setDoor(door, open, time) {
    if (!door || door.userData.open === open) return;
    door.userData.open = open;
    const gate = door.userData.gate;
    const from = gate.position.y;
    const to = open ? -0.75 : 0;
    this.retween(gate, time, (e) => (gate.position.y = from + (to - from) * e));
  }

  // doors, switches and power-ups after a tick
  showObjects(state, time) {
    for (const [x, y, open] of state.doors || []) this.setDoor(this.doors.get(`${x},${y}`), open, time);
    for (const [x, y, on] of state.switches || []) {
      const model = this.switches.get(`${x},${y}`);
      if (!model) continue;
      model.userData.lever.rotation.z = on ? 0.5 : -0.5;
      model.userData.knob.material.color.setHex(on ? 0x43a047 : 0xe53935);
    }
    const powers = new Set((state.powers || []).map(([x, y]) => `${x},${y}`));
    for (const [key, model] of this.powers) {
      if (powers.has(key)) continue;
      this.powers.delete(key);
      this.retween(model, time, (e) => model.scale.setScalar(Math.max(0.01, 1 + e)), () => model.parent?.remove(model));
    }
  }

  // playing together: player 1 is the stage's own animal, the others get their own models;
  // each stands on a ring in its player's colour
  showPlayers(players, time, me) {
    const seen = new Set();
    for (const player of players) {
      seen.add(player.number);
      let model = player.number === 1 ? this.monkey : this.others.get(player.number);
      if (!model) {
        model = makeAnimal(player.look || this.level.pack.id);
        model.position.set(player.at[0], 0, player.at[1]);
        model.rotation.y = ANGLE[player.facing];
        this.board.add(model);
        this.others.set(player.number, model);
      }
      if (player.number !== 1) this.glide(model, player.at, player.facing, time);
      let ring = this.rings.get(player.number);
      if (!ring) {
        ring = makePlayerRing(player.number);
        this.rings.set(player.number, ring);
      }
      if (ring.parent !== model) model.add(ring);
      ring.scale.setScalar(player.number === me ? 1.15 : 1);
    }
    for (const [number, model] of this.others) {
      if (seen.has(number)) continue;
      model.parent?.remove(model);
      this.others.delete(number);
    }
  }

  showGame(state, tickMs = 150, me = 0) {
    const time = Math.max(40, tickMs * 0.85);
    this.glide(this.monkey, state.animal.at, state.animal.facing, time);
    this.showObjects(state, time);
    if (state.players?.length) this.showPlayers(state.players, time, me);
    this.position = [...state.animal.at];
    this.facing = state.animal.facing;
    const present = new Set(state.items.map(([x, y]) => `${x},${y}`));
    for (const [key, item] of this.items) {
      if (!present.has(key)) {
        item.parent?.remove(item);
        this.items.delete(key);
      }
    }
    for (const [x, y, tile] of state.items) {
      if (this.items.has(`${x},${y}`)) continue;
      const item = makeItem(this.level.pack.items[tile]);
      item.position.set(x, 0, y);
      item.userData.baseY = 0;
      this.board.add(item);
      this.items.set(`${x},${y}`, item);
    }
    const seen = new Set();
    for (const critter of state.critters) {
      seen.add(critter.id);
      let model = this.critters.get(critter.id);
      if (!model) {
        model = makeCritter(critter.kind);
        model.position.set(critter.at[0], 0, critter.at[1]);
        model.rotation.y = ANGLE[critter.facing];
        this.board.add(model);
        this.critters.set(critter.id, model);
      }
      this.glide(model, critter.at, critter.facing, time);
    }
    for (const [id, model] of this.critters) {
      if (seen.has(id)) continue;
      this.critters.delete(id);
      this.retween(model, time, (e) => model.scale.setScalar(Math.max(0.01, 1 - e)), () => model.parent?.remove(model));
    }
    if (state.said) this.say(state.said);
    else this.hideBubble();
  }

  // a bump in a game: a quick squash, no move (target: "animal" or a critter's id)
  bumpGame(target) {
    const model = target === "animal" ? this.monkey : this.critters?.get(target);
    // (in a shared world the page doesn't know whose bump it was, so it sends none)
    if (!model || reducedMotion.matches || model.userData.squash) return;
    const base = model.scale.x;
    model.userData.squash = true;
    this.tweens.add({
      start: performance.now(),
      duration: 160,
      step: (e, p) => model.scale.set(base * (1 + Math.sin(p * Math.PI) * 0.15), base * (1 - Math.sin(p * Math.PI) * 0.2), base),
      done: () => {
        model.scale.setScalar(base);
        model.userData.squash = false;
      },
    });
  }

  glide(model, [tx, tz], facing, time) {
    const [fx, fz] = [model.position.x, model.position.z];
    const from = model.rotation.y;
    const to = nearestAngle(from, ANGLE[facing]);
    if (fx === tx && fz === tz && Math.abs(to - from) < 1e-3) return;
    const moving = fx !== tx || fz !== tz;
    this.retween(model, time, (e, p) => {
      model.position.x = fx + (tx - fx) * e;
      model.position.z = fz + (tz - fz) * e;
      model.position.y = moving && !reducedMotion.matches ? Math.sin(p * Math.PI) * 0.12 : 0;
      model.rotation.y = from + (to - from) * Math.min(1, e * 1.6);
    });
  }

  // one movement per model at a time: a new tick takes over from where the last one is
  retween(model, duration, step, done = () => {}) {
    const old = model.userData.tween;
    if (old && this.tweens.delete(old)) old.done();
    const time = reducedMotion.matches ? Math.min(duration, 40) : duration;
    const tween = {
      start: performance.now(),
      duration: time,
      step,
      done: () => {
        if (model.userData.tween === tween) model.userData.tween = null;
        done();
      },
    };
    model.userData.tween = tween;
    this.tweens.add(tween);
  }

  async play(event) {
    const d = this.duration;
    const monkey = this.monkey;
    this.mood.hidden = true;
    if (QUIET.has(event.type)) return;
    this.arms ??= new Map();
    switch (event.type) {
      case "reach": {
        // a long arm grows towards its tip and stays out until its grab comes back
        const [fx, fz] = this.position;
        const [tx, tz] = event.to;
        const length = Math.hypot(tx - fx, tz - fz) || 0.3;
        const arm = mesh(new THREE.CylinderGeometry(0.05, 0.07, 1, 6), 0xd81b60);
        arm.rotation.z = Math.PI / 2;
        arm.rotation.y = -Math.atan2(tz - fz, tx - fx);
        arm.rotation.order = "YXZ";
        this.board.add(arm);
        this.arms.get(event.arm)?.parent?.remove(this.arms.get(event.arm));
        this.arms.set(event.arm, arm);
        await this.tween(d, (e) => {
          const reach = Math.max(length * e, 0.01);
          arm.scale.set(1, reach, 1);
          arm.position.set(fx + ((tx - fx) * e) / 2, 0.12, fz + ((tz - fz) * e) / 2);
        });
        break;
      }
      case "fly": {
        const [fx, fz] = this.position;
        const [tx, tz] = event.to;
        this.position = event.to;
        await this.tween(d * 1.6, (e, p) => {
          monkey.position.x = fx + (tx - fx) * e;
          monkey.position.z = fz + (tz - fz) * e;
          monkey.position.y = Math.sin(p * Math.PI) * 1.2;
        });
        break;
      }
      case "block":
        this.say("⏳");
        await wait(d * 2);
        this.hideBubble();
        break;
      case "move": {
        if (this.hidden) {
          monkey.scale.set(1, 1, 1);
          this.hidden = false;
        }
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
        const hop = event.slide ? 0 : 0.18; // a penguin slides on its belly, no hops
        if (event.slide) monkey.rotation.x = 0.9;
        await this.tween(event.slide ? d * 0.6 : d, (e, p) => {
          monkey.position.x = fx + (tx - fx) * e;
          monkey.position.z = fz + (tz - fz) * e;
          monkey.position.y = Math.sin(p * Math.PI) * hop;
        });
        if (!event.slide) monkey.rotation.x = 0;
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
      case "swing": {
        const [fx, fz] = this.position;
        const [tx, tz] = event.to;
        this.position = event.to;
        await this.tween(d * 2, (e, p) => {
          monkey.position.x = fx + (tx - fx) * e;
          monkey.position.z = fz + (tz - fz) * e;
          monkey.position.y = Math.sin(p * Math.PI) * 0.9;
        });
        break;
      }
      case "climb": {
        const key = event.at.join(",");
        const item = this.items.get(key);
        const [x, z] = event.at;
        const [fx, fz] = this.position;
        const climb = (e) => {
          monkey.position.x = fx + (x - fx) * 0.45 * e;
          monkey.position.z = fz + (z - fz) * 0.45 * e;
          monkey.position.y = e * 0.9;
        };
        await this.tween(d * 1.2, climb);
        if (item) {
          this.say(`+1 ${ITEM_EMOJI[this.level.pack.items[event.item]] || "⭐"}`);
          const start = item.position.clone();
          await this.tween(Math.max(d, 260), (e) => {
            item.position.y = start.y + e * 0.4;
            item.scale.setScalar(1 - e);
          });
          item.parent?.remove(item);
          this.items.delete(key);
          this.hideBubble();
        }
        await this.tween(d * 1.2, (e) => climb(1 - e));
        break;
      }
      case "build": {
        const key = event.at.join(",");
        const old = this.tiles.get(key);
        const bridge = this.makeTile("=");
        bridge.position.set(event.at[0], 0.4, event.at[1]);
        this.board.add(bridge);
        await this.tween(d * 1.5, (e) => (bridge.position.y = 0.4 - e * 0.45));
        if (old) this.board.remove(old);
        this.tiles.set(key, bridge);
        break;
      }
      case "crack": {
        const tile = this.tiles.get(event.at.join(","));
        const color = tile?.material.color.clone();
        await this.tween(700, (_, p) => {
          if (tile) tile.material.color.setRGB(1, 0.6 + 0.4 * (1 - Math.sin(p * Math.PI)), 0.6);
          monkey.rotation.z = Math.sin(p * Math.PI * 6) * 0.12 * (1 - p);
        });
        if (tile && color) tile.material.color.copy(color);
        break;
      }
      case "hide":
        await this.tween(d, (e) => monkey.scale.set(1, 1 - e * 0.4, 1));
        this.hidden = true;
        break;
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
        if (event.arm !== undefined) {
          const arm = this.arms.get(event.arm);
          const [fx, fz] = this.position;
          const [tx, tz] = event.at;
          const length = Math.hypot(tx - fx, tz - fz) || 0.3;
          const start = item?.position.clone();
          await this.tween(d, (e) => {
            const left = 1 - e;
            if (arm) {
              arm.scale.set(1, Math.max(length * left, 0.01), 1);
              arm.position.set(fx + ((tx - fx) * left) / 2, 0.12, fz + ((tz - fz) * left) / 2);
            }
            if (item && event.item && start) {
              item.position.x = start.x + (fx - start.x) * e;
              item.position.z = start.z + (fz - start.z) * e;
            }
          });
          arm?.parent?.remove(arm);
          this.arms.delete(event.arm);
          if (item && event.item) {
            item.parent?.remove(item);
            this.items.delete(key);
          }
          break;
        }
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
          await this.missed(event);
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
