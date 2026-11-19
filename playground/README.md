# Playground

Example programs for some of the bundled levels (`codezoo levels list` shows all 23). Each file is named after the level it solves; run the commands from the repository root.

```bash
uv run codezoo levels show m01-l03
```

```bash
uv run codezoo check m01-l03 playground/m01-l03.py
```

```bash
uv run codezoo run m01-l03 playground/m01-l03.py --trace
```

| File | Level | Stars |
| --- | --- | --- |
| `m01-l01.py` | One banana | 3/3 |
| `m01-l02.py` | Turn the corner | 3/3 |
| `m01-l03.py` | Around the rock | 3/3 |
| `m01-l04.py` | Two bananas | 3/3 |
| `m01-l05.py` | Leave a note | 3/3 |
| `m02-l01.py` | Banana row | 3/3 |
| `m02-l01-no-loop.py` | Banana row without a loop | 1/3: solved, but too long and no `for` |

`oops/` holds programs that go wrong on purpose, to show CodeZoo's messages. The first line of each file names the command to try.

| File | What happens |
| --- | --- |
| `oops/bump.py` | The monkey walks into the rock |
| `oops/typo.py` | `stpe` instead of `step`: "Did you mean `step`?" |
| `oops/syntax.py` | A missing bracket: Python can't read the line |
| `oops/too-short.py` | Stops one square early: 0 stars and a hint |
| `oops/while.py` | `while` isn't supported yet: kept as raw code, not run |

Copy any file, change it, and check it again. `tests/test_playground.py` makes sure these examples keep behaving as described.
