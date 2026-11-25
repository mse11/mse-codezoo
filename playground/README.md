# Playground

Example programs for some of the bundled levels (`codezoo levels list` shows all 109). Each file is named after the level it solves; run the commands from the repository root.

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
| `m03-l02.py` | Counting bananas (a variable) | 3/3 |
| `m04-l04.py` | f-strings | 3/3 |
| `m05-l03.py` | Row of surprises (`if` in three worlds) | 3/3 |
| `m07-l03.py` | Give it an input, using your own helper file `mytricks.py` | 2/3: the `def` is in `mytricks.py`, not in the program |
| `m07-l05.py` | Give back an answer (`return`) | 3/3 |
| `m08-l02.py` | Thin ice: the penguin catches `CrackError` | 3/3 |
| `m09-l06.py` | Exactly the plan: the beaver's dictionary | 3/3 |
| `m10-l06.py` | The first burrow: the fox explores by recursion | 3/3 |

`oops/` holds programs that go wrong on purpose, to show CodeZoo's messages. The first line of each file names the command to try.

| File | What happens |
| --- | --- |
| `oops/bump.py` | The monkey walks into the rock |
| `oops/typo.py` | `stpe` instead of `step`: "Did you mean `step`?" |
| `oops/syntax.py` | A missing bracket: Python can't read the line |
| `oops/too-short.py` | Stops one square early: 0 stars and a hint |
| `oops/for-else.py` | `for ... else` isn't part of CodeZoo: kept as raw code, not run |
| `oops/one-world.py` | Works in world 1 but grabs a rotten banana in world 2 |
| `oops/no-brackets.py` | `if is_blocked:` without brackets: "Add brackets to ask it" |
| `oops/no-base-case.py` | A function that calls itself forever: "Does it have a base case?" |
| `oops/thin-ice.py` | Nothing catches the penguin's `CrackError` |
| `oops/no-global.py` | Changing `score` inside a function without `global score` |

`mytricks.py` is not a level's program: it is a helper file, and any program in the same folder can `import` it, like your own `tricks.py`.

Copy any file, change it, and check it again. `tests/test_playground.py` makes sure these examples keep behaving as described.
