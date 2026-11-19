// Import the CodeZoo engine inside Pyodide (CPython compiled to WebAssembly) and solve
// every bundled level there. Proves the engine stays standard-library only, so the
// phase 4 offline browser build is packaging, not porting.
//
//   uv build --wheel
//   npm install --no-save pyodide@0.29.5
//   node scripts/pyodide_smoke.mjs dist/
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { loadPyodide } from "pyodide";

const folder = process.argv[2] || "dist";
const wheel = readdirSync(folder).find((name) => name.endsWith(".whl"));
if (!wheel) {
  console.error(`no wheel in ${folder}/; run \`uv build --wheel\` first`);
  process.exit(2);
}

const pyodide = await loadPyodide();
pyodide.unpackArchive(new Uint8Array(readFileSync(join(folder, wheel))), "wheel");
const report = pyodide.runPython(`
import importlib, pkgutil, sys
import mse_codezoo
from mse_codezoo.game import solution_errors
from mse_codezoo.levels import level_files, load_level

engine = [m.name for m in pkgutil.iter_modules(mse_codezoo.__path__) if m.name not in ("cli", "__main__")]
for name in engine:
    importlib.import_module("mse_codezoo." + name)
assert "click" not in sys.modules, "the engine imported click"

failed = []
levels = level_files()
for path in levels:
    errors = solution_errors(load_level(path))
    if errors:
        failed.append("FAIL " + path.name + ": " + "; ".join(errors))
lines = [
    "Python " + sys.version.split()[0] + ": imported " + str(len(engine)) + " engine modules, "
    + str(len(levels) - len(failed)) + "/" + str(len(levels)) + " levels solved"
] + failed
chr(10).join(lines)
`);
console.log(report);
if (!report.includes("levels solved") || report.includes("FAIL ")) process.exit(1);
