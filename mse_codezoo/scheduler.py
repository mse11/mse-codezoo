"""Running things at the same time on a simulated clock, so a race happens the same way
every run.

``asyncio``: an event loop like Python's own. Tasks take turns at every ``await``, in the
order they became ready, and ``asyncio.sleep(2)`` moves the clock instead of waiting; so a
program behaves exactly as it would in CPython, only instantly.

``threading``: each thread runs one statement at a time. With the GIL (the default) one
thread runs per tick and a seeded random choice decides when another thread gets a turn;
without it (Python 3.13's free-threaded build) every thread runs a statement in the same
tick. Either way the same seed gives the same interleaving, so a race shows up every time.

Every step is tagged with its lane (task or thread) and the clock, for the lanes under the
stage. Standard library only.
"""

from __future__ import annotations

import heapq
import itertools
import random
from collections import deque
from collections.abc import Callable, Generator
from typing import Any

from mse_codezoo import ir
from mse_codezoo.i18n import t
from mse_codezoo.interpreter import (
    Awaitable,
    LearnerError,
    Runner,
    ZooObject,
    coroutine,
    describe,
    function,
)

Body = Generator[Any, Any, Any]

SWITCH = 0.4  # with the GIL: chance that another thread gets the next statement


class CancelledError(BaseException):
    """A task was cancelled."""


CancelledError.__module__ = "asyncio"


class QueueEmpty(Exception):
    """``get_nowait()`` on an empty queue."""


QueueEmpty.__module__ = "asyncio"


def _cancelled() -> LearnerError:
    return LearnerError(t("The task was cancelled."), kind="raised", exception=CancelledError())


def _again(error: LearnerError) -> LearnerError:
    """The same error, raised again where someone waited for it."""
    return LearnerError(error.message, kind=error.kind, exception=error.exception)


def _need_loop(runner: Runner, what: str) -> Loop:
    if runner.loop is None:
        raise LearnerError(
            t(
                "`{what}` only works while `asyncio.run(...)` runs, inside an `async def`.",
                what=what,
            ),
            kind="type",
            exception=RuntimeError("no running event loop"),
        )
    return runner.loop


# --- asyncio -------------------------------------------------------------------------------


class Future(Awaitable):
    """A result that isn't there yet."""

    ZOO_ATTRS = ("done", "result", "cancelled")
    KIND = "a future"

    def __init__(self, loop: Loop) -> None:
        self.loop = loop
        self._done = False
        self._result: Any = None
        self._error: LearnerError | None = None
        self._cancelled = False
        self.waiters: list[Task] = []
        self.callbacks: list[Callable[[Future], None]] = []

    def done(self) -> bool:
        return self._done

    def cancelled(self) -> bool:
        return self._cancelled

    def result(self) -> Any:
        if not self._done:
            message = t("The result isn't ready yet; `await` it first.")
            raise LearnerError(message, kind="raised", exception=RuntimeError(message))
        if self._error is not None:
            raise _again(self._error)
        return self._result

    def set_result(self, value: Any) -> None:
        if not self._done:
            self._done, self._result = True, value
            self._wake()

    def set_error(self, error: LearnerError) -> None:
        if not self._done:
            self._done, self._error = True, error
            self._wake()

    def _wake(self) -> None:
        waiters, self.waiters = self.waiters, []
        for task in waiters:
            task.waiting_on = None
            self.loop.schedule(task)
        for callback in list(self.callbacks):
            callback(self)

    def wait(self, runner: Runner) -> Body:
        if not self._done:
            yield ("wait", self)
        return self.result()


class Task(Future):
    """A coroutine running on its own lane."""

    ZOO_ATTRS = ("done", "result", "cancel", "cancelled", "get_name")
    KIND = "a task"

    def __init__(self, loop: Loop, coro: coroutine, name: str) -> None:
        super().__init__(loop)
        self.name = name
        coro.started = True
        self.body = coro._body
        self.waiting_on: Future | None = None
        self.sleeping = False
        self.token = 0  # invalidates a timer when the task is woken early
        self.cancel_asked = False

    def get_name(self) -> str:
        return self.name

    def cancel(self) -> bool:
        if self._done:
            return False
        self.cancel_asked = True
        if self.waiting_on is not None:
            if self in self.waiting_on.waiters:
                self.waiting_on.waiters.remove(self)
            self.waiting_on = None
            self.loop.schedule(self)
        elif self.sleeping:
            self.token += 1
            self.sleeping = False
            self.loop.schedule(self)
        return True

    def step(self, value: Any) -> None:
        runner = self.loop.runner
        error = None
        if self.cancel_asked:
            self.cancel_asked = False
            error = _cancelled()
        outer = runner.lane
        runner.lane, self.loop.current = self.name, self
        try:
            request = self.body.send(value) if error is None else self.body.throw(error)
        except StopIteration as stop:
            self.set_result(stop.value)
            return
        except LearnerError as exc:
            self._cancelled = isinstance(exc.exception, CancelledError)
            self.set_error(exc)
            return
        finally:
            runner.lane, self.loop.current = outer, None
        self.loop.handle(self, request)

    def __repr__(self) -> str:
        return f"<Task {self.name}>"


class Loop:
    """The event loop behind ``asyncio.run()``."""

    def __init__(self, runner: Runner) -> None:
        self.runner = runner
        self.ready: deque[tuple[Task, Any]] = deque()
        self.timers: list[tuple[float, int, Task, int]] = []
        self.order = itertools.count()
        self.current: Task | None = None
        self.tasks: list[Task] = []

    def create_task(self, coro: Any, name: Any = None) -> Task:
        if isinstance(coro, Awaitable) and not isinstance(coro, coroutine | Future):
            # a trick that takes time, like reach(3), can be a task of its own
            label = getattr(coro, "label", None) or type(coro).__name__
            where = self.runner._current_statement()
            coro = coroutine(label, label, self._trick_body(coro, where), where)
        if not isinstance(coro, coroutine):
            message = t(
                "A task needs a coroutine, like `arm(3)` from an `async def`, not {what}.",
                what=describe(coro),
            )
            raise LearnerError(message, kind="type", exception=TypeError(message))
        if coro.started:
            message = t("This coroutine already ran. Call `{name}()` again for a new one.")
            raise LearnerError(
                message.replace("{name}", coro.name),
                kind="type",
                exception=RuntimeError("cannot reuse already awaited coroutine"),
            )
        lane = self.runner.add_lane(str(name) if name else coro.label)
        task = Task(self, coro, lane)
        self.tasks.append(task)
        self.schedule(task)
        self.runner.events.append({"type": "task", "lane": lane})
        return task

    def _trick_body(self, trick: Awaitable, where: str) -> Body:
        """A trick running as a task: steps on its own lane when it starts and ends."""
        runner = self.runner
        node = ir.Pass(id=where)
        body = trick.wait(runner)
        value: Any = None
        first = True
        while True:
            try:
                request = body.send(value)
            except StopIteration as stop:
                runner._step(node, note=f"-> {stop.value!r}")
                return stop.value
            if first:  # the trick has started: show it on its lane now
                runner._step(node, note=t("waiting"))
                first = False
            value = yield request

    def schedule(self, task: Task, value: Any = None) -> None:
        self.ready.append((task, value))

    def handle(self, task: Task, request: Any) -> None:
        kind, arg = request if isinstance(request, tuple) else (None, None)
        if kind == "sleep":
            if arg <= 0:
                self.schedule(task)
            else:
                task.sleeping = True
                task.token += 1
                wake = self.runner.clock + arg
                heapq.heappush(self.timers, (wake, next(self.order), task, task.token))
        elif kind == "wait":
            if arg.done():
                self.schedule(task)
            else:
                arg.waiters.append(task)
                task.waiting_on = arg
        else:
            task.set_error(
                LearnerError(
                    t("An `async def` can't `yield` in CodeZoo; use `await`."), kind="type"
                )
            )

    def run_until_done(self, main: Task) -> None:
        while not main.done():
            if self.ready:
                task, value = self.ready.popleft()
                if not task.done():
                    task.step(value)
                continue
            if not self.timers:
                raise LearnerError(
                    t("Every task is waiting for another one, so none can go on (a deadlock)."),
                    kind="raised",
                    exception=RuntimeError("deadlock"),
                )
            wake, _, task, token = heapq.heappop(self.timers)
            if token != task.token or task.done():
                continue
            self.runner.clock = max(self.runner.clock, wake)
            task.sleeping = False
            self.schedule(task)


class Sleep(Awaitable):
    KIND = "a wait"

    def __init__(self, seconds: float, result: Any) -> None:
        self.seconds = seconds
        self.result = result

    def wait(self, runner: Runner) -> Body:
        yield ("sleep", self.seconds)
        return self.result


class AsyncLock(ZooObject):
    """``asyncio.Lock()``: one task at a time inside ``async with lock:``."""

    ZOO_ATTRS = ("acquire", "release", "locked")
    KIND = "a lock"
    ASYNC = True

    def __init__(self, runner: Runner) -> None:
        self.runner = runner
        self._locked = False
        self.waiters: deque[Future] = deque()

    def locked(self) -> bool:
        return self._locked

    def acquire(self) -> Awaitable:
        return _Acquire(self)

    def release(self) -> None:
        if not self._locked:
            message = t("The lock isn't taken, so it can't be let go.")
            raise LearnerError(message, kind="raised", exception=RuntimeError(message))
        self.runner.events.append({"type": "lock", "action": "free"})
        if self.waiters:
            self.waiters.popleft().set_result(True)  # handed straight to the next in line
        else:
            self._locked = False

    def zoo_enter(self, runner: Runner) -> Body:
        yield from _Acquire(self).wait(runner)
        return None

    def zoo_exit(self, runner: Runner, error: Any) -> Body:
        self.release()
        return False
        yield  # pragma: no cover


class _Acquire(Awaitable):
    KIND = "a wait for a lock"

    def __init__(self, lock: AsyncLock) -> None:
        self.lock = lock

    def wait(self, runner: Runner) -> Body:
        lock = self.lock
        if not lock._locked:
            lock._locked = True
            runner.events.append({"type": "lock", "action": "take"})
            return True
        runner.events.append({"type": "lock", "action": "wait"})
        future = Future(_need_loop(runner, "lock"))
        lock.waiters.append(future)
        yield ("wait", future)
        runner.events.append({"type": "lock", "action": "take"})
        return True


class AsyncQueue(ZooObject):
    """``asyncio.Queue()``: tasks hand each other things in order."""

    ZOO_ATTRS = ("put", "get", "put_nowait", "get_nowait", "qsize", "empty")
    KIND = "a queue"

    def __init__(self, runner: Runner) -> None:
        self.runner = runner
        self.items: deque[Any] = deque()
        self.getters: deque[Future] = deque()

    def qsize(self) -> int:
        return len(self.items)

    def empty(self) -> bool:
        return not self.items

    def put_nowait(self, item: Any) -> None:
        while self.getters:
            getter = self.getters.popleft()
            if not getter.done():
                getter.set_result(item)
                return
        self.items.append(item)

    def put(self, item: Any) -> Awaitable:
        self.put_nowait(item)
        return Sleep(0, None)

    def get_nowait(self) -> Any:
        if not self.items:
            raise LearnerError(t("The queue is empty."), kind="raised", exception=QueueEmpty())
        return self.items.popleft()

    def get(self) -> Awaitable:
        return _Get(self)


class _Get(Awaitable):
    KIND = "a wait for the queue"

    def __init__(self, queue: AsyncQueue) -> None:
        self.queue = queue

    def wait(self, runner: Runner) -> Body:
        if self.queue.items:
            return self.queue.items.popleft()
        future = Future(_need_loop(runner, "queue.get()"))
        self.queue.getters.append(future)
        yield ("wait", future)
        return future.result()


class TaskGroup(ZooObject):
    """``async with asyncio.TaskGroup() as group:``: every task started in it has finished
    when the block ends; if one fails, the others are cancelled."""

    ZOO_ATTRS = ("create_task",)
    KIND = "a task group"
    ASYNC = True

    def __init__(self, runner: Runner) -> None:
        self.runner = runner
        self.tasks: list[Task] = []
        self.errors: list[LearnerError] = []
        self.entered = False

    def create_task(self, coro: Any, name: Any = None) -> Task:
        loop = _need_loop(self.runner, "create_task")
        if not self.entered:
            message = t("Start tasks inside `async with asyncio.TaskGroup() as group:`.")
            raise LearnerError(message, kind="raised", exception=RuntimeError(message))
        task = loop.create_task(coro, name)
        self.tasks.append(task)
        task.callbacks.append(self._finished)
        return task

    def _finished(self, task: Future) -> None:
        if task._error is not None and not task.cancelled():
            self.errors.append(task._error)
            for other in self.tasks:
                other.cancel()

    def zoo_enter(self, runner: Runner) -> Body:
        self.entered = True
        return self
        yield  # pragma: no cover

    def zoo_exit(self, runner: Runner, error: Any) -> Body:
        loop = _need_loop(runner, "TaskGroup")
        if error is not None:
            for task in self.tasks:
                task.cancel()
        while not all(task.done() for task in self.tasks):
            everyone = Future(loop)

            def check(_: Future, everyone: Future = everyone) -> None:
                if all(task.done() for task in self.tasks):
                    everyone.set_result(None)

            for task in self.tasks:
                if not task.done():
                    task.callbacks.append(check)
            yield ("wait", everyone)
        if self.errors:
            group = ExceptionGroup(
                "unhandled errors in a TaskGroup",
                [e.exception for e in self.errors if isinstance(e.exception, Exception)]
                or [RuntimeError(self.errors[0].message)],
            )
            raise LearnerError(
                t("A task in the group failed: {why}", why=self.errors[0].message),
                kind="raised",
                exception=group,
            )
        return False


def asyncio_names(runner: Runner) -> dict[str, Any]:
    def run(main: Any) -> Any:
        if runner.loop is not None:
            message = t("`asyncio.run()` can't start inside another `asyncio.run()`.")
            raise LearnerError(message, kind="raised", exception=RuntimeError(message))
        if runner.threads is not None and runner.threads.running:
            message = t("In CodeZoo, `asyncio.run()` works only in the main program.")
            raise LearnerError(message, kind="type", exception=RuntimeError(message))
        loop = Loop(runner)
        runner.loop = loop
        try:
            task = loop.create_task(main)
            loop.run_until_done(task)
        finally:
            runner.loop = None
        return task.result()

    def sleep(seconds: Any, result: Any = None) -> Sleep:
        if isinstance(seconds, bool) or not isinstance(seconds, int | float):
            message = t("`asyncio.sleep` needs a number of seconds, like `asyncio.sleep(1)`.")
            raise LearnerError(message, kind="type", exception=TypeError(message))
        return Sleep(max(seconds, 0), result)

    def create_task(coro: Any, name: Any = None) -> Task:
        return _need_loop(runner, "asyncio.create_task").create_task(coro, name)

    def gather(*parts: Any, return_exceptions: bool = False) -> Future:
        loop = _need_loop(runner, "asyncio.gather")
        children: list[Future] = []
        for part in parts:
            if isinstance(part, Awaitable) and not isinstance(part, Future):
                children.append(loop.create_task(part))
            elif isinstance(part, Future):
                children.append(part)
            else:
                message = t("`gather` needs coroutines or tasks, not {what}.", what=describe(part))
                raise LearnerError(message, kind="type", exception=TypeError(message))
        together = Future(loop)

        def check(_: Future | None) -> None:
            if together.done():
                return
            for child in children:
                if child.done() and child._error is not None and not return_exceptions:
                    together.set_error(child._error)
                    return
            if all(child.done() for child in children):
                together.set_result(
                    [
                        child._error.exception if child._error is not None else child._result
                        for child in children
                    ]
                )

        for child in children:
            child.callbacks.append(check)
        check(None)
        return together

    def current_task() -> Task | None:
        return _need_loop(runner, "asyncio.current_task").current

    return {
        "run": run,
        "sleep": sleep,
        "create_task": create_task,
        "gather": gather,
        "current_task": current_task,
        "Lock": lambda: AsyncLock(runner),
        "Queue": lambda: AsyncQueue(runner),
        "TaskGroup": lambda: TaskGroup(runner),
        "CancelledError": CancelledError,
        "QueueEmpty": QueueEmpty,
    }


# --- threading ---------------------------------------------------------------------------


class Thread(ZooObject):
    """``threading.Thread(target=gather, args=(3,))``"""

    ZOO_ATTRS = ("start", "join", "is_alive", "name")
    KIND = "a thread"

    def __init__(
        self,
        runner: Runner,
        target: Any = None,
        args: Any = (),
        kwargs: Any = None,
        name: Any = None,
    ) -> None:
        self.runner = runner
        self.target = target
        self.args = tuple(args)
        self.kwargs = dict(kwargs or {})
        label = getattr(target, "__name__", "thread")
        shown = ", ".join(repr(a) for a in self.args)
        self.name = str(name) if name else f"{label}({shown})"
        self.lane = ""
        self.started = False
        self.done = False
        self.body: Body | None = None
        self.blocked_on: ThreadLock | None = None
        self.sleep_until: float | None = None

    def start(self) -> None:
        if self.started:
            message = t("A thread can only be started once.")
            raise LearnerError(message, kind="raised", exception=RuntimeError(message))
        runner = self.runner
        if runner.threads is None:
            runner.threads = Threads(runner)
        self.started = True
        self.lane = runner.add_lane(self.name)
        self.body = runner.threads.body_for(self)
        runner.threads.threads.append(self)
        runner.events.append({"type": "thread", "lane": self.lane})

    def join(self) -> None:
        if not self.started:
            message = t("A thread has to `start()` before you can `join()` it.")
            raise LearnerError(message, kind="raised", exception=RuntimeError(message))
        assert self.runner.threads is not None
        self.runner.threads.run_until(lambda: self.done)

    def is_alive(self) -> bool:
        return self.started and not self.done

    def __repr__(self) -> str:
        return f"<Thread {self.name}>"


class ThreadLock(ZooObject):
    """``threading.Lock()``: one thread at a time inside ``with lock:``."""

    ZOO_ATTRS = ("acquire", "release", "locked")
    KIND = "a lock"

    def __init__(self, runner: Runner) -> None:
        self.runner = runner
        self._locked = False

    def locked(self) -> bool:
        return self._locked

    def _take(self) -> None:
        self._locked = True
        self.runner.events.append({"type": "lock", "action": "take"})

    def acquire(self, blocking: bool = True) -> bool:
        if not self._locked:
            self._take()
            return True
        if not blocking:
            return False
        threads = self.runner.threads
        if threads is not None and threads.running:
            self.runner.pending = ("acquire", self)  # the thread waits after this line
            return True
        self._wait_in_main()
        return True

    def _wait_in_main(self) -> None:
        threads = self.runner.threads
        if threads is None:
            message = t("The lock is taken and nobody will let it go (a deadlock).")
            raise LearnerError(message, kind="raised", exception=RuntimeError(message))
        threads.run_until(lambda: not self._locked)
        if self._locked:
            message = t("The lock is taken and nobody will let it go (a deadlock).")
            raise LearnerError(message, kind="raised", exception=RuntimeError(message))
        self._take()

    def release(self) -> None:
        if not self._locked:
            message = t("The lock isn't taken, so it can't be let go.")
            raise LearnerError(message, kind="raised", exception=RuntimeError(message))
        self._locked = False
        self.runner.events.append({"type": "lock", "action": "free"})

    def zoo_enter(self, runner: Runner) -> Body:
        if not self._locked:
            self._take()
            return None
        threads = runner.threads
        if threads is not None and threads.running:
            runner.events.append({"type": "lock", "action": "wait"})
            yield ("acquire", self)  # the scheduler hands over the lock when it is free
            return None
        self._wait_in_main()
        return None

    def zoo_exit(self, runner: Runner, error: Any) -> Body:
        self.release()
        return False
        yield  # pragma: no cover


class Threads:
    """Takes turns between threads, one statement at a time."""

    def __init__(self, runner: Runner) -> None:
        self.runner = runner
        self.threads: list[Thread] = []
        self.rng = random.Random(runner.seed)
        self.running = False
        self.current: Thread | None = None

    def body_for(self, thread: Thread) -> Body:
        runner = self.runner
        target = thread.target
        args, kwargs = list(thread.args), thread.kwargs
        if isinstance(target, Callable) and hasattr(target, "__func__"):  # a bound method
            if isinstance(target.__func__, function):
                args = [target.__self__, *args]
                target = target.__func__
        if isinstance(target, function) and runner._kind(target.node) == "function":
            frame = runner._bind(target, args, kwargs)
            return runner._framed(frame, runner._function_body(target, frame, True))

        def once() -> Body:
            if target is not None:
                runner._call_value(target, args, kwargs, getattr(target, "__name__", "target"))
            return None
            yield  # pragma: no cover

        return once()

    def run_until(self, finished: Callable[[], bool]) -> None:
        runner = self.runner
        if self.running:
            message = t("In CodeZoo, only the main program can wait for threads with `join()`.")
            raise LearnerError(message, kind="type", exception=RuntimeError(message))
        self.running = True
        outer = runner.lane
        try:
            while not finished():
                alive = [th for th in self.threads if th.started and not th.done]
                if not alive:
                    break
                runnable = [th for th in alive if self._can_run(th)]
                if not runnable:
                    sleepers = [th.sleep_until for th in alive if th.sleep_until is not None]
                    if not sleepers:
                        raise LearnerError(
                            t(
                                "Every thread is waiting for a lock, so none can go on (a deadlock)."  # noqa: E501
                            ),
                            kind="raised",
                            exception=RuntimeError("deadlock"),
                        )
                    runner.clock = max(runner.clock, min(sleepers))
                    continue
                if runner.gil:
                    self._resume(self._pick(runnable))
                else:  # free-threaded: every thread gets a statement in this tick
                    for thread in sorted(runnable, key=lambda _: self.rng.random()):
                        if not thread.done and self._can_run(thread):
                            self._resume(thread)
                runner.clock += 1
        finally:
            self.running = False
            runner.lane = outer

    def finish(self) -> None:
        if any(th.started and not th.done for th in self.threads):
            self.run_until(lambda: False)

    def _can_run(self, thread: Thread) -> bool:
        if thread.sleep_until is not None:
            if thread.sleep_until > self.runner.clock:
                return False
            thread.sleep_until = None
        lock = thread.blocked_on
        if lock is not None:
            if lock._locked:
                return False
            thread.blocked_on = None
            lock._take()
        return True

    def _pick(self, runnable: list[Thread]) -> Thread:
        if self.current in runnable and self.rng.random() > SWITCH:
            return self.current  # type: ignore[return-value]
        self.current = self.rng.choice(runnable)
        return self.current

    def _resume(self, thread: Thread) -> None:
        runner = self.runner
        runner.lane = thread.lane
        assert thread.body is not None
        try:
            request = thread.body.send(None)
        except StopIteration:
            thread.done = True
            return
        except LearnerError as exc:
            thread.done = True
            exc.message = t("In the thread {name}: {why}", name=thread.name, why=exc.message)
            raise
        kind, arg = request if isinstance(request, tuple) else ("preempt", None)
        if kind == "sleep":
            thread.sleep_until = runner.clock + arg
        elif kind == "acquire":
            thread.blocked_on = arg


def threading_names(runner: Runner) -> dict[str, Any]:
    def make_thread(
        group: Any = None, target: Any = None, name: Any = None, args: Any = (), kwargs: Any = None
    ) -> Thread:
        return Thread(runner, target, args, kwargs, name)

    def current_thread() -> Any:
        return types_namespace(name=runner.lane or "MainThread")

    return {
        "Thread": make_thread,
        "Lock": lambda: ThreadLock(runner),
        "current_thread": current_thread,
    }


class types_namespace(ZooObject):  # noqa: N801
    ZOO_ATTRS = ("name",)
    KIND = "a thread"

    def __init__(self, name: str) -> None:
        self.name = name
