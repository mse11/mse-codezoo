"""The pond: Python's interactive prompt in the console pane (the 3.13 REPL's way of
working: ``>>>`` for a new line, ``...`` while a block goes on, the value of an expression
shown, ``_`` holding the last one).

A pond keeps its own variables between lines, like a Python session, and runs every line
with the zoo's interpreter: the same safe subset, step limit and kind messages as a program.
There is no world in the pond, so the animal's commands are not there; ``print``, maths,
text, lists, functions and classes are.
"""

from __future__ import annotations

import codeop
import secrets
import threading
import warnings
from collections import OrderedDict
from typing import Any

from mse_codezoo import ir
from mse_codezoo.i18n import t
from mse_codezoo.interpreter import Runner, safe_repr
from mse_codezoo.lang_python import parse

MAX_PONDS = 32  # newest kept, like running games
MAX_LINE = 400
POND_STEPS = 2_000  # per line typed


class Pond:
    def __init__(self, version: tuple[int, int] | None) -> None:
        self.version = version
        self.names: dict[str, Any] = {}
        self.buffer: list[str] = []

    def feed(self, line: str) -> dict[str, Any]:
        """One line typed at the prompt: ``more`` while a block isn't finished yet."""
        self.buffer.append(line)
        text = "\n".join(self.buffer)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                complete = codeop.compile_command(text, "<pond>", "single")
        except (SyntaxError, ValueError, OverflowError):
            complete = True  # let the zoo's own parser explain the mistake kindly
        if complete is None:
            return {"more": True, "output": [], "error": None}
        self.buffer = []
        return self.run(text)

    def run(self, text: str) -> dict[str, Any]:
        parsed = parse(text + "\n", self.version)
        if not parsed.ok or parsed.program is None:
            first = parsed.diagnostics[0] if parsed.diagnostics else None
            message = first.message if first else t("That line isn't Python the zoo can read.")
            return {"more": False, "output": [], "error": message}
        program = parsed.program
        # a lone expression shows its value, as the REPL does (and keeps it in `_`)
        shown = len(program.body) == 1 and isinstance(program.body[0], ir.ExprStmt)
        if shown:
            stmt = program.body[0]
            target = ir.Name(id=f"{stmt.id}._", name="_")
            program.body = [ir.Assign(id=stmt.id, target=target, value=stmt.value)]
        runner = Runner(program, max_steps=POND_STEPS, version=self.version)
        runner.env.update(self.names)
        runner.globals = runner.env
        runner.execute()
        output = list(runner.output)
        error = runner.error.message if runner.error else None
        if shown and error is None and runner.env.get("_") is not None:
            output.append(safe_repr(runner.env["_"]))
        self.names = {k: v for k, v in runner.env.items() if not (shown and k == "_" and v is None)}
        return {"more": False, "output": output, "error": error}


class Ponds:
    """The ponds of one server, by session id (newest kept)."""

    def __init__(self) -> None:
        self._ponds: OrderedDict[str, Pond] = OrderedDict()
        self._lock = threading.Lock()

    def feed(self, session: Any, line: Any, version: tuple[int, int] | None) -> dict[str, Any]:
        if not isinstance(line, str) or len(line) > MAX_LINE or "\n" in line:
            return {
                "session": session,
                "more": False,
                "output": [],
                "error": t("Type one line at a time."),
            }
        with self._lock:
            pond = self._ponds.get(session) if isinstance(session, str) else None
            if pond is None or pond.version != version:
                session = secrets.token_urlsafe(9)
                pond = Pond(version)
                self._ponds[session] = pond
                while len(self._ponds) > MAX_PONDS:
                    self._ponds.popitem(last=False)
            self._ponds.move_to_end(session)
        return {"session": session, **pond.feed(line)}

    def forget(self, session: Any) -> None:
        with self._lock:
            self._ponds.pop(session, None)


PONDS = Ponds()
