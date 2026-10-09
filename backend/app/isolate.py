"""Run heavy CAD work (big STEP files) in a separate process with a memory cap and a time limit.

A very large or broken model can need more memory than the server has. Run in-process, that would take
the whole site down; run here, only the helper process dies and the caller gets an IsolatedError it can
turn into "an engineer will price this by hand".

The function runs in a fresh Python process (spawn, not fork: the web server has threads), so it must be
a top-level function given as "module:function", with plain arguments, and it must save its own results
(the CAD code already caches to disk).
"""
from __future__ import annotations

import importlib
import multiprocessing as mp
import os

BIG_FILE = int(os.getenv("CAD_ISOLATE_BYTES", str(15 * 1024 * 1024)))  # files above this are handled in a helper process
MEMORY_MB = int(os.getenv("CAD_MEMORY_MB", "1500"))  # cap for the helper (the Render instance has 2 GB in all)
TIME_S = int(os.getenv("CAD_TIME_S", "1200"))


class IsolatedError(Exception):
    pass


def _child(target: str, args: tuple, mem_mb: int, q) -> None:
    try:
        import resource

        lim = mem_mb * 1024 * 1024
        try:  # heap and private memory (not address space: OpenCascade's threads reserve large stacks)
            resource.setrlimit(resource.RLIMIT_DATA, (lim, resource.RLIM_INFINITY))
        except (ValueError, OSError):
            pass
        mod, fn = target.split(":")
        out = getattr(importlib.import_module(mod), fn)(*args)
        q.put(("ok", out))
    except MemoryError:
        q.put(("err", "The model needs more memory than this server has."))
    except Exception as exc:  # noqa: BLE001
        q.put(("err", f"{type(exc).__name__}: {exc}"[:500]))


def run(target: str, *args, mem_mb: int | None = None, timeout: int | None = None):
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=_child, args=(target, args, mem_mb or MEMORY_MB, q), daemon=True)
    p.start()
    p.join(timeout or TIME_S)
    if p.is_alive():
        p.kill()
        p.join(5)
        raise IsolatedError("The model took too long to read.")
    try:
        status, out = q.get(timeout=2)
    except Exception:  # noqa: BLE001  (died before it could answer: killed for memory, or crashed)
        code = p.exitcode
        raise IsolatedError("The model needs more memory than this server has." if code in (-9, 137) or code is None
                            else f"The model could not be read (helper exit {code}).") from None
    if status != "ok":
        raise IsolatedError(out)
    return out
