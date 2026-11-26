// The 3D stage: a low-poly jungle grid drawn with three.js (vendored, no network).
// Same interface as the 2D stage in stage.js: load(level, world), reset(), play(event),
// setSpeed(n), showFeeling(feeling), plus a `duration` in milliseconds.
// Models are built from simple shapes in code, so there are no asset files to load.

import * as THREE from "./vendor/three/three.module.min.js";

const ANGLE = { north: Math.PI, east: Math.PI / 2, south: 0, west: -Math.PI / 2 };
const STEP = { north: [0, -1], east: [1, 0], south: [0, 1], west: [-1, 0] };
import { EMOJI as ITEM_EMOJI, missBubble } from "./stage.js";
import { graphics, lowerGraphics } from "./look.js";

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

// 3D detail from "Look and feel" (look.js): high, medium or low. Models read it when they
// are built (at each reset); the renderer's settings follow it at once (applyQuality).
const quality = () => document.documentElement.dataset.graphics || graphics();
// how finely round shapes are cut: fewer triangles on slower computers
const SEGMENTS = { high: 1, medium: 0.5, low: 0.34 };
const seg = (n, least = 3) => Math.max(least, Math.round(n * (SEGMENTS[quality()] ?? 1)));

function material(color, options = {}) {
  if (quality() === "low") return new THREE.MeshLambertMaterial({ color, flatShading: true, ...options });
  return new THREE.MeshStandardMaterial({ color, flatShading: true, roughness: 0.85, ...options });
}

function mesh(geometry, color, options) {
  const result = new THREE.Mesh(geometry, material(color, options));
  result.castShadow = true;
  result.receiveShadow = true;
  return result;
}

// --- models -----------------------------------------------------------------------

// --- cartoon style: smooth, soft shapes and big shiny eyes ---------------------------------

// fur-like: matte with a soft sheen at the edges; `gloss` for noses and shiny bits
// (high only: medium is plain smooth plastic, low the cheapest lighting there is)
function soft(color, { gloss = false, ...options } = {}) {
  const level = quality();
  if (level !== "high") {
    // options only the high detail's material has (sheen, clearcoat, a pearl's shimmer)
    const { sheen, sheenColor, sheenRoughness, clearcoat, iridescence, roughness, ...plain } = options;
    if (level === "low") return new THREE.MeshLambertMaterial({ color, ...plain });
    return new THREE.MeshStandardMaterial({ color, roughness: roughness ?? (gloss ? 0.3 : 0.75), ...plain });
  }
  return new THREE.MeshPhysicalMaterial({
    color,
    roughness: gloss ? 0.25 : 0.7,
    sheen: gloss ? 0 : 0.8,
    sheenRoughness: 0.5,
    sheenColor: new THREE.Color(color).lerp(new THREE.Color(0xffffff), 0.5),
    clearcoat: gloss ? 1 : 0,
    ...options,
  });
}

function blob(radius, color, options, [across, down] = [32, 24]) {
  const result = new THREE.Mesh(new THREE.SphereGeometry(radius, seg(across, 8), seg(down, 6)), soft(color, options));
  result.castShadow = quality() === "high" || radius >= 0.06; // tiny parts' shadows are hardly seen
  result.receiveShadow = true;
  return result;
}

// white eyeball, coloured iris, pupil and a white glint; scaled flat in y to blink
function cuteEye(radius, iris = 0x5d3a1a) {
  const eye = new THREE.Group();
  const ball = blob(radius, 0xffffff, { gloss: true });
  const ring = blob(radius * 0.68, iris, { gloss: true }, [24, 16]);
  ring.position.z = radius * 0.42;
  const pupil = blob(radius * 0.4, 0x111111, { gloss: true }, [16, 12]);
  pupil.position.z = radius * 0.72;
  const glint = new THREE.Mesh(new THREE.SphereGeometry(radius * 0.2, seg(12, 6), seg(8, 4)), new THREE.MeshBasicMaterial({ color: 0xffffff }));
  glint.position.set(radius * 0.3, radius * 0.32, radius * 0.92);
  const small = glint.clone();
  small.scale.setScalar(0.5);
  small.position.set(-radius * 0.28, -radius * 0.3, radius * 0.95);
  eye.add(ball, ring, pupil, glint, small);
  return eye;
}

function cheek(x, y, z) {
  const spot = new THREE.Mesh(
    new THREE.SphereGeometry(0.045, seg(16, 6), seg(12, 4)),
    new THREE.MeshBasicMaterial({ color: 0xff8a9a, transparent: true, opacity: 0.55, depthWrite: false }),
  );
  spot.scale.set(1.3, 0.8, 0.3);
  spot.position.set(x, y, z);
  spot.lookAt(x * 3, y, z * 3);
  return spot;
}

// a chubby cartoon monkey: big head, big eyes, short limbs, a curly tail
function makeMonkey() {
  const monkey = new THREE.Group();
  const fur = 0x9a6234;
  const face = 0xf2d3b0;

  const body = blob(0.19, fur);
  body.scale.set(1, 1.12, 0.92);
  body.position.y = 0.25;
  const belly = blob(0.14, face);
  belly.scale.set(1, 1.15, 0.6);
  belly.position.set(0, 0.23, 0.1);
  const arms = [-1, 1].map((side) => {
    const arm = new THREE.Mesh(new THREE.CapsuleGeometry(0.045, 0.14, seg(8, 2), seg(16, 6)), soft(fur));
    arm.castShadow = true;
    arm.position.set(side * 0.19, 0.24, 0.04);
    arm.rotation.z = side * 0.35;
    arm.rotation.x = -0.25;
    const hand = blob(0.05, face);
    hand.position.y = -0.11;
    arm.add(hand);
    return arm;
  });
  const feet = [-0.09, 0.09].map((x) => {
    const foot = blob(0.065, face);
    foot.scale.set(1, 0.6, 1.4);
    foot.position.set(x, 0.04, 0.07);
    return foot;
  });
  const curl = new THREE.CatmullRomCurve3([
    [0, 0.18, -0.15], [0, 0.2, -0.3], [0, 0.35, -0.4], [0, 0.5, -0.34], [0, 0.52, -0.24], [0, 0.44, -0.2], [0, 0.4, -0.27],
  ].map((point) => new THREE.Vector3(...point)));
  const tail = new THREE.Mesh(new THREE.TubeGeometry(curl, seg(40, 12), 0.028, seg(10, 5)), soft(fur));
  tail.castShadow = true;

  // the head is about as big as the body, which is what makes it read as "cute"
  const head = blob(0.24, fur);
  head.scale.set(1.05, 0.95, 0.95);
  const mask = blob(0.19, face); // heart-ish face: two cheeks around the eyes, plus the muzzle
  mask.scale.set(1.15, 0.8, 0.55);
  mask.position.set(0, 0.01, 0.13);
  const muzzle = blob(0.12, face);
  muzzle.scale.set(1.2, 0.8, 0.75);
  muzzle.position.set(0, -0.08, 0.17);
  const nose = blob(0.028, 0x4a2c17, { gloss: true }, [16, 12]);
  nose.scale.set(1.5, 0.8, 0.8);
  nose.position.set(0, -0.04, 0.26);
  const smile = new THREE.Mesh(new THREE.TorusGeometry(0.045, 0.009, seg(8, 3), seg(20, 6), Math.PI * 0.8), soft(0x4a2c17));
  smile.rotation.z = Math.PI + Math.PI * 0.1;
  smile.position.set(0, -0.08, 0.255);
  const eyes = [-0.09, 0.09].map((x) => {
    const eye = cuteEye(0.072);
    eye.position.set(x, 0.045, 0.185);
    eye.rotation.y = x * 1.6; // look slightly outward, following the curve of the face
    return eye;
  });
  const brows = [-1, 1].map((side) => {
    const brow = new THREE.Mesh(new THREE.CapsuleGeometry(0.01, 0.04, seg(4, 1), seg(8, 4)), soft(0x5d3a1a));
    brow.rotation.z = Math.PI / 2 + side * 0.25;
    brow.position.set(side * 0.085, 0.13, 0.205);
    return brow;
  });
  const ears = [-1, 1].map((side) => {
    const ear = blob(0.085, fur);
    ear.scale.set(0.5, 1, 1);
    ear.position.set(side * 0.25, 0.03, 0);
    const inner = blob(0.06, 0xf5b8a0);
    inner.scale.set(0.5, 1, 1);
    inner.position.x = side * 0.02;
    ear.add(inner);
    return ear;
  });
  const tuft = blob(0.05, fur);
  tuft.scale.set(0.6, 1.2, 0.6);
  tuft.position.set(0.02, 0.24, 0.02);
  tuft.rotation.z = -0.4;

  const headGroup = new THREE.Group(); // pivots at the neck, for nods and head tilts
  headGroup.position.y = 0.6;
  headGroup.add(head, mask, muzzle, nose, smile, ...eyes, ...brows, ...ears, tuft, cheek(-0.15, -0.06, 0.2), cheek(0.15, -0.06, 0.2));
  monkey.add(body, belly, ...arms, ...feet, tail, headGroup);
  monkey.userData.head = headGroup;
  monkey.userData.eyes = eyes;
  monkey.userData.body = body;
  monkey.rotation.order = "YXZ"; // turn first, so bending forward follows the facing
  return monkey;
}

// idle life for cartoon animals: blink every few seconds, breathe a little, and the
// animal's own touch (a bee's wings flap, an octopus's arms wiggle, a fox's tail sways)
function idleLife(animal, t) {
  const { eyes, body, wings, wiggle, tail, float } = animal.userData;
  if (eyes) {
    const phase = (t + (animal.id % 7) * 0.37) % 3.6;
    const shut = phase < 0.14 ? Math.sin((phase / 0.14) * Math.PI) : 0;
    for (const eye of eyes) eye.scale.y = 1 - shut * 0.9;
  }
  if (body) {
    const base = (body.userData.base ??= body.scale.clone());
    const breath = Math.sin(t * 2.2) * 0.02;
    body.scale.set(base.x * (1 - breath * 0.5), base.y * (1 + breath), base.z * (1 - breath * 0.5));
  }
  for (const wing of wings || []) wing.rotation.z = wing.userData.side * Math.sin(t * 28) * 0.45;
  (wiggle || []).forEach((arm, i) => (arm.rotation.z = Math.sin(t * 2.5 + i) * 0.08));
  if (tail) tail.rotation.y = Math.sin(t * 1.8) * 0.25;
  if (float) float.position.y = 0.08 + Math.sin(t * 2 + animal.id) * 0.04; // a ghost hovers
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

function finish(animal, parts, head) {
  animal.add(...parts, head);
  animal.userData.head = head;
  animal.rotation.order = "YXZ";
  return animal;
}

// --- the other zoo animals, in the monkey's cartoon style -------------------------------

// a smooth capsule (arms, legs, antennae)
function limb(radius, length, color) {
  const result = new THREE.Mesh(new THREE.CapsuleGeometry(radius, length, seg(6, 2), seg(14, 6)), soft(color));
  result.castShadow = quality() === "high" || radius >= 0.04;
  return result;
}

// big eyes, cheeks and a small smile on a head group; returns the eyes (for blinking)
function cuteFace(head, { r, y, z, spread, iris, turn = 1.4, smile = null, cheeks = true }) {
  const eyes = [-spread, spread].map((x) => {
    const eye = cuteEye(r, iris);
    eye.position.set(x, y, z);
    eye.rotation.y = x * turn;
    return eye;
  });
  head.add(...eyes);
  if (cheeks) head.add(cheek(-(spread + 0.06), y - 0.08, z - 0.01), cheek(spread + 0.06, y - 0.08, z - 0.01));
  if (smile) {
    const mouth = new THREE.Mesh(
      new THREE.TorusGeometry(smile.size ?? 0.04, 0.008, seg(8, 3), seg(20, 6), Math.PI * 0.8),
      soft(smile.color ?? 0x3a2418),
    );
    mouth.rotation.z = Math.PI * 1.1;
    mouth.position.set(0, smile.y, smile.z);
    head.add(mouth);
  }
  return eyes;
}

function cartoon(animal, parts, head, extra = {}) {
  finish(animal, parts, head);
  Object.assign(animal.userData, extra);
  return animal;
}

// a round penguin in a little red scarf
function makePenguin() {
  const penguin = new THREE.Group();
  const coat = 0x2f3e52;
  const orange = 0xff9f1c;
  const body = blob(0.22, coat);
  body.scale.set(1, 1.2, 0.95);
  body.position.y = 0.28;
  const belly = blob(0.17, 0xfdfdfd);
  belly.scale.set(0.95, 1.15, 0.6);
  belly.position.set(0, 0.25, 0.11);
  const wings = [-1, 1].map((side) => {
    const wing = blob(0.1, coat);
    wing.scale.set(0.35, 1.05, 0.7);
    wing.position.set(side * 0.21, 0.3, 0);
    wing.rotation.z = side * 0.35;
    return wing;
  });
  const feet = [-0.08, 0.08].map((x) => {
    const foot = blob(0.06, orange, { gloss: true });
    foot.scale.set(1, 0.4, 1.5);
    foot.position.set(x, 0.025, 0.09);
    return foot;
  });
  const scarf = new THREE.Mesh(new THREE.TorusGeometry(0.15, 0.04, seg(10, 4), seg(28, 8)), soft(0xe63946));
  scarf.rotation.x = Math.PI / 2;
  scarf.position.y = 0.49;
  scarf.castShadow = true;
  const scarfEnd = limb(0.035, 0.1, 0xe63946);
  scarfEnd.position.set(0.09, 0.4, 0.12);
  scarfEnd.rotation.z = 0.3;

  const head = new THREE.Group();
  head.position.y = 0.64;
  const skull = blob(0.21, coat);
  skull.scale.set(1.05, 0.95, 0.95);
  const mask = blob(0.16, 0xfdfdfd); // white face
  mask.scale.set(1.2, 0.85, 0.6);
  mask.position.set(0, -0.02, 0.1);
  const beak = blob(0.045, orange, { gloss: true });
  beak.scale.set(1.4, 0.7, 1.2);
  beak.position.set(0, -0.06, 0.2);
  head.add(skull, mask, beak);
  const eyes = cuteFace(head, { r: 0.062, y: 0.02, z: 0.155, spread: 0.08, iris: 0x2a6fb5 });
  return cartoon(penguin, [body, belly, ...wings, ...feet, scarf, scarfEnd], head, { eyes, body });
}

// a chubby beaver with two big front teeth and a flat paddle tail
function makeBeaver() {
  const beaver = new THREE.Group();
  const fur = 0x8d5a3b;
  const light = 0xe0bd96;
  const dark = 0x5a3a28;
  const body = blob(0.21, fur);
  body.scale.set(1.05, 1.05, 1);
  body.position.y = 0.25;
  const belly = blob(0.15, light);
  belly.scale.set(1, 1.1, 0.6);
  belly.position.set(0, 0.23, 0.11);
  const tail = blob(0.13, dark);
  tail.scale.set(0.85, 0.22, 1.5);
  tail.position.set(0, 0.06, -0.3);
  tail.rotation.x = 0.25;
  const arms = [-1, 1].map((side) => {
    const arm = limb(0.04, 0.09, fur);
    arm.position.set(side * 0.17, 0.27, 0.1);
    arm.rotation.set(-0.6, 0, side * 0.3);
    return arm;
  });
  const feet = [-0.09, 0.09].map((x) => {
    const foot = blob(0.065, dark);
    foot.scale.set(1, 0.5, 1.4);
    foot.position.set(x, 0.035, 0.08);
    return foot;
  });

  const head = new THREE.Group();
  head.position.y = 0.56;
  const skull = blob(0.21, fur);
  skull.scale.set(1.05, 0.95, 0.95);
  const muzzle = blob(0.1, light);
  muzzle.scale.set(1.35, 0.85, 0.85);
  muzzle.position.set(0, -0.07, 0.16);
  const nose = blob(0.035, 0x2b1a12, { gloss: true });
  nose.scale.set(1.4, 0.9, 1);
  nose.position.set(0, -0.025, 0.245);
  const teeth = [-0.017, 0.017].map((x) => {
    const tooth = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.05, 0.015), soft(0xfffaf0, { gloss: true }));
    tooth.position.set(x, -0.13, 0.225);
    return tooth;
  });
  const ears = [-1, 1].map((side) => {
    const ear = blob(0.05, fur);
    ear.scale.set(1, 1, 0.6);
    ear.position.set(side * 0.15, 0.15, -0.02);
    const inner = blob(0.03, 0xc99a7a);
    inner.position.z = 0.02;
    ear.add(inner);
    return ear;
  });
  head.add(skull, muzzle, nose, ...teeth, ...ears);
  const eyes = cuteFace(head, { r: 0.06, y: 0.05, z: 0.165, spread: 0.08, iris: 0x4a2c17 });
  return cartoon(beaver, [body, belly, tail, ...arms, ...feet], head, { eyes, body });
}

// an orange fox: pointy ears, white cheeks, a big fluffy tail with a white tip
function makeFox() {
  const fox = new THREE.Group();
  const fur = 0xf07a26;
  const white = 0xfff3e6;
  const dark = 0x3e2a20;
  const body = blob(0.19, fur);
  body.scale.set(0.95, 1.05, 1.1);
  body.position.y = 0.25;
  const chest = blob(0.13, white);
  chest.scale.set(1, 1.15, 0.6);
  chest.position.set(0, 0.26, 0.11);
  const legs = [-0.08, 0.08].map((x) => {
    const leg = limb(0.04, 0.08, dark);
    leg.position.set(x, 0.07, 0.07);
    return leg;
  });
  const tailBase = new THREE.Group(); // sways from where the tail meets the body
  tailBase.position.set(0, 0.2, -0.17);
  tailBase.rotation.x = 0.55; // up and back, like a happy fox's
  const tail = blob(0.11, fur);
  tail.scale.set(0.85, 0.85, 1.9);
  tail.position.z = -0.16;
  const tip = blob(0.08, white);
  tip.position.z = -0.34;
  tailBase.add(tail, tip);

  const head = new THREE.Group();
  head.position.y = 0.56;
  const skull = blob(0.21, fur);
  skull.scale.set(1.1, 0.95, 1);
  const cheeks = [-1, 1].map((side) => {
    const patch = blob(0.11, white);
    patch.scale.set(1, 0.75, 0.75);
    patch.position.set(side * 0.08, -0.07, 0.11);
    return patch;
  });
  const snout = blob(0.07, white);
  snout.scale.set(1, 0.8, 1.3);
  snout.position.set(0, -0.06, 0.2);
  const nose = blob(0.026, 0x1a1a1a, { gloss: true });
  nose.position.set(0, -0.035, 0.29);
  const ears = [-1, 1].map((side) => {
    const ear = new THREE.Mesh(new THREE.ConeGeometry(0.08, 0.17, seg(16, 4)), soft(fur));
    ear.castShadow = true;
    ear.position.set(side * 0.12, 0.2, -0.01);
    ear.rotation.z = -side * 0.3;
    const inner = new THREE.Mesh(new THREE.ConeGeometry(0.05, 0.11, seg(12, 4)), soft(dark));
    inner.position.set(0, -0.02, 0.03);
    ear.add(inner);
    return ear;
  });
  head.add(skull, ...cheeks, snout, nose, ...ears);
  const eyes = cuteFace(head, { r: 0.058, y: 0.035, z: 0.17, spread: 0.085, iris: 0x8a4b12, cheeks: false });
  return cartoon(fox, [body, chest, ...legs, tailBase], head, { eyes, body, tail: tailBase });
}

// a pink octopus: a round head-body and eight curly arms that wiggle
function makeOctopus() {
  const octopus = new THREE.Group();
  const skin = 0xff6f91;
  const arms = ARMS.map(([dx, dz]) => {
    const arm = new THREE.Group();
    arm.rotation.y = -Math.atan2(dz, dx);
    const path = new THREE.CatmullRomCurve3(
      [[0.05, 0.16, 0], [0.16, 0.06, 0], [0.28, 0.035, 0], [0.37, 0.08, 0], [0.35, 0.14, 0], [0.3, 0.12, 0]]
        .map((point) => new THREE.Vector3(...point)),
    );
    const tube = new THREE.Mesh(new THREE.TubeGeometry(path, seg(24, 8), 0.04, seg(10, 5)), soft(skin));
    tube.castShadow = true;
    arm.add(tube);
    return arm;
  });
  const head = new THREE.Group();
  head.position.y = 0.36;
  const dome = blob(0.26, skin);
  dome.scale.set(1, 1.1, 1);
  const spots = [[-0.12, 0.17, -0.12], [0.1, 0.21, -0.06], [0.16, 0.08, -0.17], [-0.05, 0.25, 0.05]].map(([x, y, z], i) => {
    const spot = blob(0.03 + (i % 2) * 0.012, 0xffa3b8);
    spot.scale.set(1, 1, 0.4);
    spot.position.set(x, y, z);
    spot.lookAt(x * 3, y * 3, z * 3);
    return spot;
  });
  head.add(dome, ...spots);
  const eyes = cuteFace(head, {
    r: 0.075, y: 0.01, z: 0.215, spread: 0.1, iris: 0x3b2a6e,
    smile: { y: -0.1, z: 0.25, size: 0.045, color: 0x7a1f3d },
  });
  return cartoon(octopus, arms, head, { eyes, body: dome, wiggle: arms });
}

// a fluffy striped bee with see-through wings that flap
function makeBee() {
  const bee = new THREE.Group();
  const yellow = 0xffc93c;
  const dark = 0x2b2b2b;
  const body = new THREE.Group();
  body.position.y = 0.4;
  const fuzz = blob(0.2, yellow);
  fuzz.scale.set(1, 0.95, 1.2);
  // stripes sized to the body's oval at their place along it
  const stripes = [0.0, -0.13].map((z) => {
    const across = 0.2 * Math.sqrt(1 - (z / 0.24) ** 2);
    const stripe = new THREE.Mesh(new THREE.TorusGeometry(across - 0.005, 0.045, seg(10, 4), seg(32, 8)), soft(dark));
    stripe.scale.y = 0.95;
    stripe.position.z = z;
    return stripe;
  });
  const sting = new THREE.Mesh(new THREE.ConeGeometry(0.035, 0.08, seg(12, 4)), soft(dark, { gloss: true }));
  sting.rotation.x = -Math.PI / 2;
  sting.position.z = -0.3;
  body.add(fuzz, ...stripes, sting);
  const wings = [-1, 1].map((side) => {
    const pivot = new THREE.Group(); // flaps around where the wing meets the body
    pivot.position.set(side * 0.06, 0.58, -0.04);
    const wing = blob(0.15, 0xe8f4ff, { transparent: true, opacity: 0.6, depthWrite: false });
    wing.castShadow = false;
    wing.scale.set(0.9, 0.12, 0.55);
    wing.position.x = side * 0.13;
    wing.rotation.z = side * 0.45;
    pivot.add(wing);
    pivot.userData.side = side;
    return pivot;
  });
  const feet = [-0.06, 0.06].map((x) => {
    const foot = limb(0.022, 0.06, dark);
    foot.position.set(x, 0.2, 0.03);
    return foot;
  });

  const head = new THREE.Group();
  head.position.set(0, 0.47, 0.29);
  const skull = blob(0.15, 0xffdb70);
  const antennae = [-1, 1].map((side) => {
    const stalk = limb(0.01, 0.1, dark);
    stalk.position.set(side * 0.06, 0.17, 0);
    stalk.rotation.z = -side * 0.35;
    const ball = blob(0.025, dark, { gloss: true }, [16, 12]);
    ball.position.y = 0.07;
    stalk.add(ball);
    return stalk;
  });
  head.add(skull, ...antennae);
  const eyes = cuteFace(head, {
    r: 0.055, y: 0.02, z: 0.115, spread: 0.065, iris: 0x4a2c17,
    smile: { y: -0.065, z: 0.14, size: 0.03 },
  });
  return cartoon(bee, [body, ...wings, ...feet], head, { eyes, body: fuzz, wings });
}

// --- things to collect, in the animals' cartoon style --------------------------------------
// Each is a group standing on the ground at its origin (the stage moves, spins and scales it).

function group(...parts) {
  const result = new THREE.Group();
  if (parts.length) result.add(...parts);
  return result;
}

function at(object, x, y, z) {
  object.position.set(x, y, z);
  return object;
}

// the top half of a ball: jellyfish, shells, mushroom caps
function dome(radius, color, options) {
  const result = new THREE.Mesh(
    new THREE.SphereGeometry(radius, seg(32, 8), seg(12, 4), 0, Math.PI * 2, 0, Math.PI / 2),
    soft(color, { side: THREE.DoubleSide, ...options }),
  );
  result.castShadow = true;
  return result;
}

function tube(points, radius, color, options) {
  const path = new THREE.CatmullRomCurve3(points.map((point) => new THREE.Vector3(...point)));
  const result = new THREE.Mesh(new THREE.TubeGeometry(path, seg(24, 6), radius, seg(10, 4)), soft(color, options));
  result.castShadow = quality() === "high" || radius >= 0.03;
  return result;
}

// two small eyes and a smile, for the creatures among the things (fish, crab, jellyfish)
function tinyFace(x, y, z, spread = 0.04) {
  const face = new THREE.Group();
  face.position.set(x, y, z);
  cuteFace(face, { r: 0.03, y: 0, z: 0, spread, iris: 0x222222, turn: 0, cheeks: false, smile: { y: -0.04, z: 0.01, size: 0.018 } });
  return face;
}

function makeBanana(color = 0xffd23f, spots = false) {
  const fruit = tube([[-0.17, 0.2, 0], [-0.1, 0.1, 0], [0, 0.07, 0], [0.1, 0.1, 0], [0.17, 0.2, 0]], 0.052, color, { gloss: true });
  const stem = at(limb(0.016, 0.04, 0x6b4a2a), 0.185, 0.24, 0);
  stem.rotation.z = -0.5;
  const tip = at(blob(0.022, 0x4a3420, {}, [12, 8]), -0.18, 0.215, 0);
  const banana = group(fruit, stem, tip);
  if (spots) {
    for (const [x, y] of [[-0.08, 0.1], [0.03, 0.08], [0.11, 0.12]]) {
      const spot = at(blob(0.018, 0x3b2c14, {}, [10, 8]), x, y, 0.045);
      spot.scale.z = 0.4;
      banana.add(spot);
    }
  }
  return banana;
}

function makeCoconut() {
  const nut = at(blob(0.16, 0x7a4b2a), 0, 0.15, 0);
  nut.scale.set(1, 0.95, 1);
  const coconut = group(nut);
  for (const [x, z] of [[-0.035, 0.03], [0.035, 0.03], [0, -0.03]]) {
    coconut.add(at(blob(0.018, 0x2b1a10, {}, [10, 8]), x, 0.3, z)); // the three "eyes" on top
  }
  return coconut;
}

function makeFish() {
  const body = at(blob(0.13, 0x4fc3f7, { gloss: true }), 0, 0.2, 0);
  body.scale.set(1.5, 0.9, 0.62);
  const belly = at(blob(0.1, 0xe1f5fe), 0.03, 0.16, 0);
  belly.scale.set(1.5, 0.6, 0.6);
  const tail = at(new THREE.Mesh(new THREE.ConeGeometry(0.1, 0.15, seg(16, 4)), soft(0x0288d1)), -0.25, 0.2, 0);
  tail.rotation.z = -Math.PI / 2; // the point joins the body
  tail.scale.z = 0.3;
  tail.castShadow = true;
  const fin = at(blob(0.06, 0x0288d1), -0.02, 0.31, 0);
  fin.scale.set(1.2, 0.8, 0.25);
  const fish = group(body, belly, tail, fin);
  for (const side of [-1, 1]) {
    const eye = at(cuteEye(0.042, 0x222222), 0.12, 0.23, side * 0.065); // one on each side
    eye.rotation.y = side > 0 ? 0.6 : Math.PI - 0.6; // looking out and a little forward
    fish.add(eye);
  }
  return fish;
}

function makePebble() {
  const big = at(blob(0.13, 0x9e9e9e, { roughness: 0.9 }), 0, 0.075, 0);
  big.scale.set(1.25, 0.6, 1);
  const small = at(blob(0.07, 0xbdbdbd, { roughness: 0.9 }), 0.13, 0.04, 0.09);
  small.scale.set(1.2, 0.6, 1);
  return group(big, small);
}

// a scallop: ridged halves fanning out from the hinge, in two shades
function makeShell(color = 0xffb4a2) {
  const shell = group();
  for (let i = -3; i <= 3; i++) {
    const angle = i * 0.32;
    const ridge = blob(0.065, i % 2 ? 0xff9e8a : color, { gloss: true });
    ridge.scale.set(0.5, 0.45, 1.5);
    ridge.position.set(Math.sin(angle) * 0.08, 0.035 + (3 - Math.abs(i)) * 0.006, Math.cos(angle) * 0.08 - 0.08);
    ridge.rotation.y = angle;
    shell.add(ridge);
  }
  const hinge = at(blob(0.035, 0xff8a75), 0, 0.03, -0.1);
  hinge.scale.set(1.5, 0.7, 0.8);
  shell.add(hinge);
  return shell;
}

function makePearl() {
  const cup = at(dome(0.14, 0xb39ddb, { gloss: true }), 0, 0.075, 0);
  cup.rotation.x = Math.PI; // an open shell, as a little bowl
  cup.scale.set(1, 0.5, 1);
  const pearl = at(blob(0.075, 0xffffff, { gloss: true, clearcoat: 1, sheen: 0, iridescence: 1 }), 0, 0.12, 0);
  return group(cup, pearl);
}

function makeJellyfish() {
  const bell = at(dome(0.16, 0xce93d8, { transparent: true, opacity: 0.85, gloss: true }), 0, 0.3, 0);
  bell.scale.set(1, 0.85, 1);
  const jelly = group(bell, tinyFace(0, 0.36, 0.14, 0.045));
  for (let i = 0; i < 5; i++) {
    const angle = (i / 5) * Math.PI * 2;
    const [x, z] = [Math.cos(angle) * 0.08, Math.sin(angle) * 0.08];
    jelly.add(tube([[x, 0.3, z], [x * 1.2 + 0.02, 0.2, z * 1.2], [x * 0.9 - 0.02, 0.1, z * 0.9], [x * 1.1, 0.03, z * 1.1]], 0.014, 0xe1bee7));
  }
  return jelly;
}

function makeFlower() {
  const stem = tube([[0, 0, 0], [0.02, 0.12, 0], [0, 0.25, 0]], 0.016, 0x43a047);
  const leaf = at(blob(0.06, 0x66bb6a), 0.06, 0.09, 0);
  leaf.scale.set(1, 0.2, 0.5);
  leaf.rotation.z = 0.5;
  const head = at(new THREE.Group(), 0, 0.28, 0);
  head.rotation.x = -1.0; // the bloom looks up, a little forward
  head.add(blob(0.045, 0xffca28, { gloss: true }));
  for (let i = 0; i < 6; i++) {
    const angle = (i / 6) * Math.PI * 2;
    const petal = at(blob(0.05, 0xff8fb1), Math.cos(angle) * 0.07, Math.sin(angle) * 0.07, -0.01);
    petal.scale.set(1, 1, 0.35);
    head.add(petal);
  }
  return group(stem, leaf, head);
}

function makeClover() {
  const stem = tube([[0, 0, 0], [0.015, 0.1, 0], [0, 0.2, 0]], 0.014, 0x388e3c);
  const clover = group(stem);
  for (let i = 0; i < 3; i++) {
    const angle = (i / 3) * Math.PI * 2 + Math.PI / 2;
    // a heart: two small round halves side by side
    const leaf = at(new THREE.Group(), Math.cos(angle) * 0.065, 0.21, Math.sin(angle) * 0.065);
    leaf.rotation.y = -angle + Math.PI / 2;
    for (const side of [-1, 1]) {
      const half = at(blob(0.045, 0x43a047), side * 0.03, 0, 0);
      half.scale.set(1, 0.3, 1.1);
      leaf.add(half);
    }
    clover.add(leaf);
  }
  return clover;
}

function makeNettle() {
  const stalk = tube([[0, 0, 0], [0, 0.18, 0], [0.01, 0.36, 0]], 0.018, 0x2e7d32);
  const nettle = group(stalk);
  for (let i = 0; i < 4; i++) {
    const holder = at(new THREE.Group(), 0, 0.1 + i * 0.07, 0);
    holder.rotation.y = i * 1.9;
    const leaf = at(blob(0.07, i % 2 ? 0x2e7d32 : 0x388e3c), 0.07, 0, 0);
    leaf.scale.set(1, 0.15, 0.45);
    leaf.rotation.z = 0.4;
    holder.add(leaf);
    nettle.add(holder);
  }
  return nettle;
}

function makeCrab() {
  const red = 0xef5350;
  const body = at(blob(0.13, red, { gloss: true }), 0, 0.12, 0);
  body.scale.set(1.35, 0.6, 1);
  const crab = group(body);
  for (const side of [-1, 1]) {
    const stalk = at(limb(0.012, 0.06, red), side * 0.045, 0.21, 0.07);
    const eye = at(cuteEye(0.032, 0x222222), side * 0.045, 0.27, 0.075); // eyes on stalks
    crab.add(stalk, eye);
    const arm = at(limb(0.02, 0.08, red), side * 0.17, 0.13, 0.08);
    arm.rotation.set(-0.9, 0, side * 0.9);
    const claw = at(blob(0.05, red, { gloss: true }), side * 0.22, 0.17, 0.14);
    claw.scale.set(1, 0.8, 1.2);
    crab.add(arm, claw);
    for (let i = 0; i < 3; i++) {
      const leg = at(limb(0.012, 0.08, 0xc62828), side * 0.17, 0.06, -0.06 + i * 0.06);
      leg.rotation.z = side * 1.1;
      crab.add(leg);
    }
  }
  const smile = at(new THREE.Mesh(new THREE.TorusGeometry(0.025, 0.006, seg(6, 3), seg(12, 6), Math.PI * 0.8), soft(0x5d1a1a)), 0, 0.11, 0.13);
  smile.rotation.z = Math.PI * 1.1;
  crab.add(smile);
  return crab;
}

function makeEgg() {
  const nest = at(new THREE.Mesh(new THREE.TorusGeometry(0.13, 0.05, seg(10, 4), seg(28, 8)), soft(0xa1887f)), 0, 0.04, 0);
  nest.rotation.x = Math.PI / 2;
  nest.castShadow = true;
  const egg = at(blob(0.1, 0xfffbea, { gloss: true }), 0, 0.15, 0);
  egg.scale.set(0.85, 1.15, 0.85);
  const result = group(nest, egg);
  for (const [x, y, z] of [[0.05, 0.2, 0.06], [-0.06, 0.15, 0.06], [0.02, 0.1, -0.08], [-0.03, 0.23, -0.05]]) {
    const speck = at(blob(0.012, 0xc8a27a, {}, [8, 6]), x, y, z);
    result.add(speck);
  }
  return result;
}

function makeBerry() {
  const berries = group();
  for (const [x, y, z] of [[-0.05, 0.07, 0.02], [0.05, 0.07, 0.03], [0, 0.07, -0.06], [0, 0.15, 0]]) {
    berries.add(at(blob(0.065, 0x5e35b1, { gloss: true }), x, y, z));
  }
  const leaf = at(blob(0.05, 0x43a047), 0.02, 0.21, 0);
  leaf.scale.set(1, 0.2, 0.5);
  leaf.rotation.z = -0.4;
  berries.add(leaf);
  return berries;
}

// a snapping trap, drawn as a toy: a grey ring of rounded teeth around a red button
function makeTrap() {
  const base = at(blob(0.17, 0x757575, { gloss: true }), 0, 0.03, 0);
  base.scale.set(1, 0.2, 1);
  const trap = group(base, at(blob(0.05, 0xe53935, { gloss: true }), 0, 0.06, 0));
  for (let i = 0; i < 8; i++) {
    const angle = (i / 8) * Math.PI * 2;
    const tooth = at(new THREE.Mesh(new THREE.ConeGeometry(0.025, 0.07, seg(10, 4)), soft(0xbdbdbd, { gloss: true })), Math.cos(angle) * 0.13, 0.08, Math.sin(angle) * 0.13);
    tooth.castShadow = true;
    trap.add(tooth);
  }
  return trap;
}

// a cut log: bark, light wood at the ends with a growth ring
function makeLog(bark, { inside = 0xe8c592, stripes = false, length = 0.42, radius = 0.085 } = {}) {
  const log = at(new THREE.Group(), 0, radius + 0.005, 0);
  log.rotation.z = Math.PI / 2;
  const trunk = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, length, seg(24, 6), 1, true), soft(bark));
  trunk.castShadow = true;
  log.add(trunk);
  for (const end of [-1, 1]) {
    const cut = at(new THREE.Mesh(new THREE.CircleGeometry(radius, seg(24, 6)), soft(inside)), 0, (end * length) / 2, 0);
    cut.rotation.x = end * -Math.PI / 2;
    const ring = at(new THREE.Mesh(new THREE.RingGeometry(radius * 0.45, radius * 0.55, seg(24, 6)), soft(0xc49a64)), 0, end * (length / 2 + 0.001), 0);
    ring.rotation.x = end * -Math.PI / 2;
    log.add(cut, ring);
  }
  if (stripes) {
    const marks = [[-0.15, 0.3], [-0.1, 2.6], [-0.03, 1.4], [0.02, 4.4], [0.08, 0.9], [0.12, 3.3], [0.16, 5.4], [-0.06, 5.2]];
    for (const [y, angle] of marks) {
      const mark = at(blob(0.03, 0x37332f, {}, [10, 6]), Math.cos(angle) * radius, y, Math.sin(angle) * radius);
      mark.scale.set(1.6, 0.45, 0.3); // a short dark dash across the bark
      mark.lookAt(Math.cos(angle) * 2, y, Math.sin(angle) * 2);
      log.add(mark);
    }
  }
  const sprout = at(blob(0.035, 0x66bb6a), 0.08, radius * 2 + 0.01, 0); // a little leaf growing from it
  sprout.scale.set(1, 0.3, 0.55);
  return group(log, sprout);
}

function makeStick() {
  const stick = group(tube([[-0.2, 0.03, 0], [-0.05, 0.04, 0.02], [0.08, 0.035, -0.01], [0.2, 0.05, 0]], 0.02, 0x6d4c41));
  stick.add(tube([[0.02, 0.04, 0], [0.08, 0.08, 0.04], [0.12, 0.12, 0.05]], 0.012, 0x6d4c41));
  const leaf = at(blob(0.04, 0x66bb6a), 0.14, 0.13, 0.05);
  leaf.scale.set(1, 0.25, 0.5);
  stick.add(leaf);
  return stick;
}

function makeLeaf() {
  const blade = at(blob(0.15, 0x66bb6a), 0, 0.05, 0);
  blade.scale.set(1, 0.12, 0.55);
  const vein = at(limb(0.008, 0.26, 0x388e3c), 0, 0.07, 0);
  vein.rotation.z = Math.PI / 2;
  const stalk = at(limb(0.01, 0.06, 0x388e3c), -0.18, 0.05, 0);
  stalk.rotation.z = Math.PI / 2;
  const leaf = group(blade, vein, stalk);
  leaf.rotation.z = 0.15;
  return leaf;
}

function makeThorn() {
  const stalk = tube([[0, 0, 0], [0.03, 0.15, 0], [-0.02, 0.3, 0]], 0.025, 0x558b2f);
  const thorn = group(stalk);
  for (let i = 0; i < 6; i++) {
    const spike = new THREE.Mesh(new THREE.ConeGeometry(0.018, 0.07, seg(8, 4)), soft(0x9ccc65, { gloss: true }));
    const angle = i * 2.2;
    spike.position.set(Math.cos(angle) * 0.03, 0.06 + i * 0.04, Math.sin(angle) * 0.03);
    spike.rotation.set(Math.sin(angle) * 1.3, 0, -Math.cos(angle) * 1.3);
    thorn.add(spike);
  }
  return thorn;
}

function makeMushroom() {
  const stem = at(limb(0.045, 0.08, 0xfff8e1), 0, 0.085, 0);
  const cap = at(dome(0.15, 0xe53935, { gloss: true }), 0, 0.15, 0);
  cap.scale.set(1, 0.75, 1);
  const mushroom = group(stem, cap);
  for (const [x, z, size] of [[0, 0, 0.03], [0.08, 0.04, 0.022], [-0.07, 0.05, 0.02], [0.02, -0.09, 0.024], [-0.06, -0.05, 0.018]]) {
    const y = 0.15 + 0.11 * Math.sqrt(Math.max(0, 1 - (x * x + z * z) / 0.0225));
    const dot = at(blob(size, 0xffffff, {}, [10, 8]), x, y, z);
    dot.scale.y = 0.4;
    mushroom.add(dot);
  }
  return mushroom;
}

function makeGem() {
  const gem = at(new THREE.Mesh(new THREE.OctahedronGeometry(0.14, 0), soft(0x4fc3f7, { gloss: true, flatShading: true })), 0, 0.2, 0);
  gem.scale.y = 1.3;
  gem.castShadow = true;
  return group(gem);
}

const ITEM_MODELS = {
  banana: () => makeBanana(),
  rotten: () => makeBanana(0x8d7a3a, true),
  coconut: makeCoconut,
  fish: makeFish,
  pebble: makePebble,
  shell: () => makeShell(),
  pearl: makePearl,
  jellyfish: makeJellyfish,
  flower: makeFlower,
  clover: makeClover,
  nettle: makeNettle,
  crab: makeCrab,
  egg: makeEgg,
  berry: makeBerry,
  trap: makeTrap,
  oak: () => makeLog(0x6d4c41),
  pine: () => makeLog(0xa1887f, { inside: 0xf3d9a4 }),
  birch: () => makeLog(0xf5f5f5, { stripes: true }),
  stick: makeStick,
  leaf: makeLeaf,
  thorn: makeThorn,
  mushroom: makeMushroom,
};

function makeItem(noun) {
  return (ITEM_MODELS[noun] || makeGem)();
}

// --- scenery: ground, tiles, trees, rocks, plants, the goal flag -----------------------------

// a box with soft, rounded edges (tiles, the ground, planks). Shapes are shared between
// boxes of the same size; each box keeps its own material, so one tile can flash alone.
const roundedShapes = new Map();
function roundedGeometry(width, height, depth, bevel) {
  const key = [width, height, depth, bevel, quality()].join();
  if (roundedShapes.has(key)) return roundedShapes.get(key);
  const [w, d] = [width / 2 - bevel, depth / 2 - bevel];
  const corner = Math.min(bevel * 1.5, w, d);
  const shape = new THREE.Shape();
  shape.moveTo(-w + corner, -d);
  shape.lineTo(w - corner, -d);
  shape.quadraticCurveTo(w, -d, w, -d + corner);
  shape.lineTo(w, d - corner);
  shape.quadraticCurveTo(w, d, w - corner, d);
  shape.lineTo(-w + corner, d);
  shape.quadraticCurveTo(-w, d, -w, d - corner);
  shape.lineTo(-w, -d + corner);
  shape.quadraticCurveTo(-w, -d, -w + corner, -d);
  const geometry = new THREE.ExtrudeGeometry(shape, {
    depth: Math.max(0.001, height - bevel * 2),
    bevelEnabled: true,
    bevelThickness: bevel,
    bevelSize: bevel,
    bevelSegments: seg(4, 1),
    curveSegments: seg(6, 1),
  });
  geometry.rotateX(-Math.PI / 2); // extruded upwards
  geometry.center();
  roundedShapes.set(key, geometry);
  return geometry;
}

// ground and tiles: plain and matte (they cover most of the picture, so no sheen)
function groundMaterial(color, options = {}) {
  if (quality() === "low") return new THREE.MeshLambertMaterial({ color, ...options });
  return new THREE.MeshStandardMaterial({ color, roughness: 0.9, ...options });
}

function roundedBox(width, height, depth, bevel, color, options) {
  const result = new THREE.Mesh(roundedGeometry(width, height, depth, bevel), groundMaterial(color, options));
  result.castShadow = true;
  result.receiveShadow = true;
  return result;
}

// a lumpy ball: a sphere pushed in and out a little, the same way for the same seed
function lumpy(radius, color, seed = 1, options) {
  const geometry = new THREE.SphereGeometry(radius, seg(28, 8), seg(20, 6));
  const point = new THREE.Vector3();
  const position = geometry.attributes.position;
  for (let i = 0; i < position.count; i++) {
    point.fromBufferAttribute(position, i);
    const bump = 1 + 0.07 * Math.sin(point.x * 17 + seed) * Math.cos(point.z * 13 - seed) + 0.05 * Math.sin(point.y * 21 + seed * 2);
    point.multiplyScalar(bump);
    position.setXYZ(i, point.x, point.y, point.z);
  }
  geometry.computeVertexNormals();
  const result = new THREE.Mesh(geometry, soft(color, { roughness: 0.85, sheen: 0, ...options }));
  result.castShadow = true;
  result.receiveShadow = true;
  return result;
}

// a round cartoon tree: a gently bent trunk and a crown of three or four soft balls. The
// crown's top is at about 1.3, where fruit on a tree square sits.
function makeTree(seed = 0) {
  const trunk = tube([[0, 0, 0], [0.03, 0.35, 0], [-0.02, 0.7, 0], [0, 0.9, 0]], 0.08, 0x8d5a3b);
  const root = at(blob(0.12, 0x7a4b2e), 0, 0.03, 0);
  root.scale.set(1.2, 0.35, 1.2);
  const tree = group(trunk, root);
  const greens = [0x4caf50, 0x43a047, 0x66bb6a];
  const crown = [[0, 1.0, 0, 0.33], [-0.22, 0.88, 0.08, 0.24], [0.22, 0.9, -0.05, 0.25], [0.05, 0.85, 0.22, 0.22]];
  crown.forEach(([x, y, z, r], i) => tree.add(at(lumpy(r, greens[(i + seed) % 3], seed + i, { roughness: 0.75 }), x, y, z)));
  return tree;
}

// a wall: a big smooth boulder and a small one leaning on it, with a cap that suits the
// world: moss on land, snow on the ice, nothing on the reef
const ROCK_CAPS = { penguin: 0xfafdff, octopus: null };
function makeRock(seed = 0, world = "monkey") {
  const big = at(lumpy(0.36, 0x9e9a93, seed), 0, 0.27, 0);
  big.scale.set(1, 0.8, 0.95);
  const small = at(lumpy(0.16, 0x8a867f, seed + 3), 0.27, 0.1, 0.2);
  const rock = group(big, small);
  const cap = world in ROCK_CAPS ? ROCK_CAPS[world] : 0x7cb342;
  if (cap !== null) {
    const top = at(lumpy(0.2, cap, seed + 5, { roughness: 0.95 }), -0.05, 0.49, -0.04);
    top.scale.set(1.2, 0.3, 1.1);
    rock.add(top);
  }
  return rock;
}

// edge decoration: a bush, a tuft of grass or a few flowers (coral and seaweed on the reef)
function makePlant(seed, world) {
  if (world === "octopus") return seed % 2 ? makeCoral(seed) : makeSeaweed(seed);
  const kind = seed % 3;
  if (kind === 0) {
    const bush = group();
    [[0, 0.14, 0, 0.17], [-0.15, 0.1, 0.05, 0.12], [0.14, 0.1, -0.03, 0.13]].forEach(([x, y, z, r], i) => {
      bush.add(at(lumpy(r, i % 2 ? 0x388e3c : 0x43a047, seed + i), x, y, z));
    });
    if (seed % 2) bush.add(at(blob(0.03, 0xff8fb1, {}, [12, 8]), 0.05, 0.3, 0.06)); // a little flower
    return bush;
  }
  if (kind === 1) {
    const grass = group();
    for (let i = 0; i < 6; i++) {
      const angle = (i / 6) * Math.PI * 2 + seed;
      const [dx, dz] = [Math.cos(angle) * 0.06, Math.sin(angle) * 0.06];
      grass.add(tube([[dx * 0.3, 0, dz * 0.3], [dx, 0.12, dz], [dx * 2.2, 0.24 + (i % 3) * 0.04, dz * 2.2]], 0.012, i % 2 ? 0x558b2f : 0x7cb342));
    }
    return grass;
  }
  const flowers = group();
  for (let i = 0; i < 3; i++) {
    const [x, z] = [Math.cos(i * 2.1 + seed) * 0.1, Math.sin(i * 2.1 + seed) * 0.1];
    const height = 0.14 + i * 0.04;
    flowers.add(tube([[x, 0, z], [x, height, z]], 0.01, 0x43a047));
    flowers.add(at(blob(0.035, [0xffeb3b, 0xff8fb1, 0xffffff][(i + seed) % 3], {}, [12, 8]), x, height + 0.02, z));
  }
  return flowers;
}

function makeCoral(seed) {
  const colour = [0xff7a8a, 0xffa94d, 0xb388ff][seed % 3];
  const coral = group();
  for (let i = 0; i < 4; i++) {
    const angle = i * 1.7 + seed;
    const [x, z] = [Math.cos(angle) * 0.08, Math.sin(angle) * 0.08];
    const top = 0.2 + (i % 2) * 0.08;
    coral.add(tube([[0, 0, 0], [x * 0.6, top * 0.5, z * 0.6], [x * 1.4, top, z * 1.4]], 0.025, colour));
    coral.add(at(blob(0.032, colour, {}, [12, 8]), x * 1.4, top, z * 1.4));
  }
  return coral;
}

function makeSeaweed(seed) {
  const weed = group();
  for (let i = 0; i < 3; i++) {
    const x = (i - 1) * 0.07;
    const sway = (i % 2 ? 1 : -1) * 0.05;
    weed.add(tube([[x, 0, 0], [x + sway, 0.12, 0], [x - sway, 0.24, 0.02], [x + sway, 0.34 + (seed % 2) * 0.06, 0]], 0.018, i % 2 ? 0x2e7d32 : 0x26a69a));
  }
  return weed;
}

// the goal: a glowing ring on the square and a little flag that waves
function makeFlag() {
  const ring = at(new THREE.Mesh(
    new THREE.TorusGeometry(0.36, 0.035, seg(12, 4), seg(48, 12)),
    soft(0xffd54f, { gloss: true, emissive: 0xffb300, emissiveIntensity: 0.35 }),
  ), 0, 0.02, 0);
  ring.rotation.x = Math.PI / 2;
  const pole = at(limb(0.022, 0.72, 0xfafafa), 0.3, 0.4, -0.3);
  const knob = at(blob(0.04, 0xffd54f, { gloss: true }, [16, 12]), 0.3, 0.8, -0.3);
  const clothShape = new THREE.PlaneGeometry(0.3, 0.2, seg(10, 3), 1);
  const position = clothShape.attributes.position;
  for (let i = 0; i < position.count; i++) {
    const x = position.getX(i);
    position.setZ(i, Math.sin((x + 0.15) * 14) * 0.025 * (x + 0.15) * 4); // ripples, more at the free end
  }
  clothShape.computeVertexNormals();
  const cloth = at(new THREE.Mesh(clothShape, soft(0xe53935, { side: THREE.DoubleSide, sheen: 0 })), 0.45, 0.67, -0.3);
  cloth.castShadow = true;
  return group(ring, pole, knob, cloth);
}

// a lamp post on its pink square (terrain "o")
function makeLamp() {
  const post = at(limb(0.04, 0.42, 0xc62828), 0, 0.25, 0);
  const lamp = at(blob(0.09, 0xfff176, { gloss: true, emissive: 0xffc107, emissiveIntensity: 0.7 }), 0, 0.55, 0);
  const cap = at(dome(0.08, 0xc62828), 0, 0.6, 0);
  cap.scale.y = 0.6;
  return group(post, lamp, cap);
}

// --- game mode objects: doors, switches, power-ups, and the rings of playing together ---

// a wooden gate between two posts; the plank sinks into the ground when it opens
function makeDoor() {
  const door = new THREE.Group();
  for (const side of [-0.4, 0.4]) {
    door.add(at(roundedBox(0.13, 0.9, 0.13, 0.03, 0x6d4c41), side, 0.45, 0));
    door.add(at(blob(0.07, 0x8d6e63, { gloss: true }), side, 0.92, 0));
  }
  const plank = at(roundedBox(0.68, 0.7, 0.1, 0.03, 0xbc8f6a), 0, 0.4, 0);
  const band = at(roundedBox(0.7, 0.08, 0.12, 0.02, 0x5d4037), 0, 0.55, 0);
  const low = at(roundedBox(0.7, 0.08, 0.12, 0.02, 0x5d4037), 0, 0.2, 0);
  const gate = new THREE.Group();
  gate.add(plank, band, low);
  door.add(gate);
  door.userData.gate = gate;
  return door;
}

// a round plate on the ground with a lever that flips over
function makeSwitch() {
  const result = new THREE.Group();
  const plate = at(new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.34, 0.06, seg(32, 10)), soft(0x90a4ae, { gloss: true })), 0, 0.03, 0);
  plate.castShadow = plate.receiveShadow = true;
  const lever = new THREE.Group();
  const stick = at(limb(0.035, 0.32, 0x546e7a), 0, 0.19, 0);
  const knob = at(blob(0.08, 0xe53935, { gloss: true }), 0, 0.4, 0);
  lever.add(stick, knob);
  lever.position.y = 0.05;
  lever.rotation.z = -0.5;
  result.add(plate, lever);
  result.userData.lever = lever;
  result.userData.knob = knob;
  return result;
}

// a glowing five-pointed star that spins above its square
function makePower() {
  const shape = new THREE.Shape();
  for (let i = 0; i < 10; i++) {
    const radius = i % 2 ? 0.09 : 0.2;
    const angle = (i / 10) * Math.PI * 2 + Math.PI / 2;
    const [x, y] = [Math.cos(angle) * radius, Math.sin(angle) * radius];
    if (i === 0) shape.moveTo(x, y);
    else shape.lineTo(x, y);
  }
  const geometry = new THREE.ExtrudeGeometry(shape, {
    depth: 0.04, bevelEnabled: true, bevelThickness: 0.03, bevelSize: 0.025, bevelSegments: seg(3, 1),
  });
  geometry.center();
  const star = at(new THREE.Mesh(geometry, soft(0xffd600, { gloss: true, emissive: 0xffab00, emissiveIntensity: 0.6 })), 0, 0.4, 0);
  star.castShadow = true;
  return group(star);
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

// a friendly little crocodile: long round body, bumps along the back, a wide smile with
// small teeth, eyes up on top of the head, a tail that sways
function makeGuard() {
  const guard = new THREE.Group();
  const skin = 0x4caf50;
  const dark = 0x2e7d32;
  const belly = 0xc5e1a5;
  const body = at(blob(0.2, skin), 0, 0.17, -0.02);
  body.scale.set(0.95, 0.62, 1.45);
  const under = at(blob(0.16, belly), 0, 0.12, 0);
  under.scale.set(0.95, 0.5, 1.5);
  const bumps = [-0.18, -0.06, 0.06, 0.18].map((z, i) => {
    const bump = at(blob(0.045 - i * 0.003, dark), 0, 0.28, z);
    bump.scale.set(1, 0.7, 1.2);
    return bump;
  });
  const feet = [[-0.17, 0.16], [0.17, 0.16], [-0.17, -0.18], [0.17, -0.18]].map(([x, z]) => {
    const foot = at(blob(0.06, dark), x, 0.04, z);
    foot.scale.set(1.1, 0.6, 1.3);
    return foot;
  });
  const tail = new THREE.Group(); // sways from where it meets the body
  tail.position.set(0, 0.15, -0.3);
  tail.add(tube([[0, 0, 0], [0, -0.03, -0.15], [0.04, -0.08, -0.3], [0.1, -0.1, -0.4]], 0.06, skin));
  tail.add(at(blob(0.035, skin), 0.1, -0.1, -0.41));

  const head = new THREE.Group();
  head.position.set(0, 0.2, 0.27);
  const skull = at(blob(0.15, skin), 0, 0.02, 0.02);
  skull.scale.set(1.05, 0.8, 1);
  const snout = at(blob(0.12, skin), 0, -0.02, 0.17);
  snout.scale.set(1, 0.55, 1.4);
  const jaw = at(blob(0.11, belly), 0, -0.06, 0.15);
  jaw.scale.set(1, 0.35, 1.4);
  const nostrils = [-0.03, 0.03].map((x) => at(blob(0.014, 0x1b3a1b, {}, [8, 6]), x, 0.03, 0.33));
  const teeth = [-0.07, -0.025, 0.025, 0.07].map((x) => {
    const tooth = at(new THREE.Mesh(new THREE.ConeGeometry(0.014, 0.035, seg(8, 3)), soft(0xffffff, { gloss: true })), x, -0.055, 0.27 - Math.abs(x) * 0.6);
    tooth.rotation.x = Math.PI; // pointing down
    return tooth;
  });
  const lids = [-0.07, 0.07].map((x) => at(blob(0.06, skin), x, 0.12, 0.02)); // eye bumps
  head.add(skull, snout, jaw, ...nostrils, ...teeth, ...lids);
  const eyes = cuteFace(head, {
    r: 0.05, y: 0.14, z: 0.05, spread: 0.07, iris: 0xc8a000, turn: 1, // the pale jaw is its smile
  });
  return cartoon(guard, [body, under, ...bumps, ...feet, tail], head, { eyes, tail });
}

// a round little ghost that floats up and down: a dome, a wavy hem, small arms
function makeGhost() {
  const ghost = new THREE.Group();
  const white = 0xf3f0ff;
  const look = { transparent: true, opacity: 0.9, emissive: 0xb8b0ff, emissiveIntensity: 0.25 };
  const float = new THREE.Group(); // bobs up and down (idleLife)
  float.position.y = 0.08;
  const skirt = at(new THREE.Mesh(new THREE.CylinderGeometry(0.21, 0.24, 0.24, seg(32, 8), 1, true), soft(white, look)), 0, 0.26, 0);
  skirt.castShadow = true;
  const hem = Array.from({ length: 7 }, (_, i) => {
    const angle = (i / 7) * Math.PI * 2;
    return at(blob(0.06, white, look), Math.sin(angle) * 0.2, 0.14, Math.cos(angle) * 0.2);
  });
  const arms = [-1, 1].map((side) => {
    const arm = at(blob(0.055, white, look), side * 0.23, 0.32, 0.03);
    arm.scale.set(0.7, 1.2, 0.7);
    arm.rotation.z = side * 0.6;
    return arm;
  });
  const head = new THREE.Group();
  head.position.y = 0.38;
  head.add(dome(0.21, white, look));
  const eyes = cuteFace(head, {
    r: 0.055, y: 0.08, z: 0.16, spread: 0.07, iris: 0x2a2440, turn: 1.2,
    smile: { y: 0.0, z: 0.2, size: 0.035, color: 0x2a2440 },
  });
  float.add(skirt, ...hem, ...arms, head);
  ghost.add(float);
  ghost.userData.head = head;
  ghost.userData.eyes = eyes;
  ghost.userData.float = float;
  ghost.rotation.order = "YXZ";
  return ghost;
}

// a round beetle in the program's colour: two shiny wing cases with spots, a dark head
// with big eyes and two antennae, six little legs
function makeBeetle(colour) {
  const beetle = new THREE.Group();
  const dark = 0x222222;
  const shell = new THREE.Group();
  for (const side of [-1, 1]) {
    // one wing case: this side's quarter of a ball (a dark line runs between the two)
    const half = at(new THREE.Mesh(
      new THREE.SphereGeometry(0.2, seg(20, 6), seg(12, 4), side > 0 ? 0 : Math.PI, Math.PI, 0, Math.PI / 2),
      soft(colour, { gloss: true, side: THREE.DoubleSide }),
    ), side * 0.002, 0.08, -0.02);
    half.scale.set(1, 0.85, 1.2);
    half.castShadow = true;
    shell.add(half);
    for (const [x, z] of [[0.09, 0.06], [0.08, -0.12], [0.14, -0.03]]) {
      const spot = at(blob(0.035, dark, {}, [12, 8]), side * x, 0.08 + 0.17 * Math.sqrt(Math.max(0, 1 - (x * x) / 0.04 - (z * z) / 0.0576)) - 0.01, z);
      spot.scale.y = 0.35;
      shell.add(spot);
    }
  }
  const seam = at(limb(0.008, 0.36, dark), 0, 0.245, -0.03);
  seam.rotation.x = Math.PI / 2;
  seam.scale.z = 0.6;
  const base = at(blob(0.19, dark), 0, 0.09, -0.02);
  base.scale.set(1, 0.3, 1.2);
  const legs = [-0.1, 0, 0.1].flatMap((z) =>
    [-1, 1].map((side) => {
      const leg = at(limb(0.014, 0.08, dark), side * 0.2, 0.05, z);
      leg.rotation.z = side * 1.1;
      return leg;
    }),
  );
  const head = new THREE.Group();
  head.position.set(0, 0.14, 0.24);
  head.add(blob(0.1, dark, { gloss: true }));
  const antennae = [-1, 1].map((side) => {
    const stalk = at(limb(0.008, 0.08, dark), side * 0.045, 0.11, 0.02);
    stalk.rotation.set(0.4, 0, -side * 0.4);
    const ball = at(blob(0.018, dark, { gloss: true }, [10, 8]), 0, 0.055, 0);
    stalk.add(ball);
    return stalk;
  });
  head.add(...antennae);
  const eyes = cuteFace(head, { r: 0.045, y: 0.02, z: 0.075, spread: 0.045, iris: colour, turn: 1.3, cheeks: false });
  return cartoon(beetle, [shell, seam, base, ...legs], head, { eyes, body: shell });
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
    // smoothing the edges is chosen once, when the drawing surface is made
    this.renderer = new THREE.WebGLRenderer({ antialias: quality() !== "low", alpha: true });
    // gentle filmic colour handling: bright parts roll off softly instead of clipping
    this.renderer.toneMapping = THREE.NeutralToneMapping;
    this.renderer.toneMappingExposure = 1.05;
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
    sun.shadow.radius = 4;
    this.sun = sun;
    // a cool light from behind outlines the characters against the ground (rim light)
    const rim = new THREE.DirectionalLight(0xb3d9ff, 1.4);
    rim.position.set(3, 4, -8);
    this.rim = rim;
    this.scene.add(sun, sun.target, rim);
    this.applyQuality();
    window.addEventListener("codezoo-look", () => {
      if (quality() !== this.quality) this.applyQuality();
    });

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
    const ground = roundedBox(width + 0.6, 0.3, height + 0.6, 0.08, edge);
    ground.position.set((width - 1) / 2, -0.2, (height - 1) / 2);
    // a layer of earth under the grass, like a slice of cake: the board reads as a little world
    const earth = roundedBox(width + 0.5, 0.3, height + 0.5, 0.1, new THREE.Color(edge).multiplyScalar(0.62).getHex());
    earth.position.set((width - 1) / 2, -0.45, (height - 1) / 2);
    board.add(ground, earth);
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
          const tree = makeTree(x * 3 + y);
          tree.position.set(x, 0, y);
          board.add(tree);
        }
        if (kind === "o") {
          board.add(at(makeLamp(), x + 0.35, 0, y - 0.35));
        }
      }
    }
    // a few plants around the edge, placed the same way every time
    for (let i = 0; pack.id !== "penguin" && i < width + height; i++) {
      const plant = makePlant(i, pack.id);
      const side = i % 4;
      const along = (i * 7) % Math.max(width, height);
      const x = side === 0 ? -0.75 : side === 1 ? width - 0.25 : Math.min(along, width - 1);
      const z = side === 2 ? -0.75 : side === 3 ? height - 0.25 : Math.min(along, height - 1);
      plant.position.set(x, 0, z);
      plant.scale.setScalar(0.8 + ((i * 13) % 5) / 10);
      board.add(plant);
    }
    for (const [x, y] of world.walls) {
      const rock = makeRock(x * 5 + y * 3, pack.id);
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
        return roundedBox(0.98, 0.06, 0.98, 0.02, 0x4fa3e0, { transparent: true, opacity: 0.85, roughness: 0.15 });
      case "-":
        return roundedBox(0.96, 0.1, 0.96, 0.03, 0x81d4fa, { transparent: true, opacity: 0.7, roughness: 0.1 });
      case "o":
        return roundedBox(0.96, 0.1, 0.96, 0.03, 0xf8bbd0);
      case "=":
        return roundedBox(0.96, 0.12, 0.96, 0.03, 0xa1887f);
      default:
        return roundedBox(0.94, 0.1, 0.94, 0.03, color);
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

  // what "3D detail" changes at once: pixels drawn, shadows and the rim light. The animals'
  // own detail follows on the next reset (Reset, the next level), when they are built again.
  applyQuality() {
    const level = quality();
    this.quality = level;
    const ratio = window.devicePixelRatio || 1;
    this.renderer.setPixelRatio(level === "high" ? Math.min(ratio, 2) : level === "medium" ? Math.min(ratio, 1.25) : 1);
    this.renderer.shadowMap.enabled = level !== "low";
    this.renderer.shadowMap.type = level === "high" ? THREE.PCFSoftShadowMap : THREE.PCFShadowMap;
    this.sun.castShadow = level !== "low";
    this.sun.shadow.mapSize.setScalar(level === "high" ? 1024 : 512);
    this.sun.shadow.map?.dispose();
    this.sun.shadow.map = null;
    this.rim.visible = level !== "low";
    this.scene.traverse((object) => {
      for (const material of [object.material].flat()) if (material) material.needsUpdate = true;
    });
    this.frameTimes = [];
    this.slowWindows = 0;
    if (this.running) this.resize();
  }

  // "3D detail: automatic": when frames keep coming slowly, go down a step (look.js decides
  // whether it may). Only ordinary frame gaps count: a hidden tab pauses drawing altogether.
  watchSpeed(now) {
    const gap = now - (this.lastFrame ?? now);
    this.lastFrame = now;
    if (gap <= 0 || gap > 250) return;
    this.frameTimes.push(gap);
    if (this.frameTimes.reduce((sum, time) => sum + time, 0) < 3000) return;
    const average = this.frameTimes.reduce((sum, time) => sum + time, 0) / this.frameTimes.length;
    this.frameTimes = [];
    this.slowWindows = average > 45 ? this.slowWindows + 1 : 0; // under about 22 pictures a second
    if (this.slowWindows >= 2) {
      this.slowWindows = 0;
      lowerGraphics(); // look.js announces it, and the listener above applies it
    }
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
    this.watchSpeed(now);
    for (const tween of [...this.tweens]) {
      const progress = Math.min(1, (now - tween.start) / tween.duration);
      tween.step(ease(progress), progress);
      if (progress >= 1) {
        this.tweens.delete(tween);
        tween.done();
      }
    }
    if (this.monkey && !reducedMotion.matches) {
      const t = this.clock.getElapsedTime();
      if (this.tweens.size === 0) this.monkey.userData.head.rotation.z = Math.sin(t * 1.6) * 0.05;
      idleLife(this.monkey, t);
      for (const model of this.others?.values() || []) idleLife(model, t); // friends playing along
      for (const model of this.critters?.values() || []) idleLife(model, t);
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
