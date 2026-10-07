"""M118 — the Message Log's spine: a Qt-free event bus in core.

Fusion's Message Log has no way to click an entry and land on the
feature that caused it [ui_message_log Finding 6]. Tracer's log starts
one better: every entry can carry WHO broke, so the panel's rows
deep-link to the timeline. To stay headless-testable, the bus lives in
core and GUI code only subscribes to it — the document and its error
paths speak, the UI listens.

Entries dedupe at the tail: a dialog that recomputes five times over
the same broken fillet logs ONE line with a repeat count, which is
what makes a log worth reading after a session of pain.
"""
from __future__ import annotations

import weakref
from dataclasses import dataclass, field
from datetime import datetime

ERROR = "ERROR"
WARN = "WARN"
INFO = "INFO"

CAP = 2000                     # a rolling memory, like any good log


@dataclass
class Entry:
    severity: str
    text: str
    source: str = "app"
    feature: str | None = None
    feature_pos: int | None = None
    ts: str = field(default_factory=lambda: datetime.now().strftime(
        "%H:%M:%S"))
    count: int = 1

    def stamp(self) -> str:
        return self.ts


_entries: list[Entry] = []
_listeners: list = []


def _bump_time(e: Entry) -> None:
    e.ts = datetime.now().strftime("%H:%M:%S")


def _notify() -> None:
    dead = []
    for i, ref in enumerate(_listeners):
        if isinstance(ref, weakref.WeakMethod):
            cb = ref()                     # None once the listener dies
            if cb is None:
                dead.append(i)             # the listener died; reap it
                continue
        else:
            cb = ref
        try:
            cb()
        except Exception:                  # a deaf listener never deafens
            pass                           # the others
    for i in reversed(dead):
        del _listeners[i]


def log(severity: str, text: str, source: str = "app",
        feature: str | None = None, pos: int | None = None,
        dedupe: bool = True) -> Entry:
    """Append (or re-stamp, if the tail is the same complaint)."""
    text = str(text).strip()
    last = _entries[-1] if _entries else None
    if dedupe and last is not None and last.severity == severity \
            and last.text == text and last.feature == feature \
            and last.source == source:
        last.count += 1
        _bump_time(last)
        _notify()
        return last
    e = Entry(severity=severity, text=text, source=source,
              feature=feature, feature_pos=pos)
    _entries.append(e)
    if len(_entries) > CAP:
        del _entries[:len(_entries) - CAP]
    _notify()
    return e


def error(text, **kw) -> Entry:
    return log(ERROR, text, **kw)


def warn(text, **kw) -> Entry:
    return log(WARN, text, **kw)


def info(text, **kw) -> Entry:
    return log(INFO, text, **kw)


def entries() -> list[Entry]:
    return list(_entries)


def counts() -> tuple[int, int]:
    """(errors, warnings) — the two numbers a status bar shouts."""
    return (sum(e.count for e in _entries if e.severity == ERROR),
            sum(e.count for e in _entries if e.severity == WARN))


def clear() -> None:
    _entries.clear()
    _notify()


def subscribe(cb) -> None:
    """Bound methods are held WEAKLY: a panel that dies of old age must
    not be kept alive by the bus, and must stop being painted into.
    Plain functions and lambdas are held strongly (an inline lambda has
    no other owner, and a closure's reach is the caller's business)."""
    ref = (weakref.WeakMethod(cb) if hasattr(cb, "__self__") else cb)
    _listeners.append(ref)


def unsubscribe(cb) -> None:
    for i, ref in enumerate(_listeners):
        live = ref() if isinstance(ref, weakref.WeakMethod) else ref
        if live == cb:                     # bound methods: ==, not `is`
            del _listeners[i]
            return
    # dead refs are reaped by _notify(); an unsubscribe for a corpse is a no-op


def dump_text() -> str:
    lines = []
    for e in _entries:
        who = f" [{e.feature}]" if e.feature else ""
        rep = f"  \u00d7{e.count}" if e.count > 1 else ""
        lines.append(f"{e.ts}  {e.severity:<5} {e.source}{who}: "
                     f"{e.text}{rep}")
    return "\n".join(lines)
