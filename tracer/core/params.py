"""User Parameters — the grammar behind Fusion's parameter sheet.

A document carries NAMED numbers (``width = 20``) whose values may be
expressions over other parameters (``thickness = width / 2``).  Any
numeric lever a feature exposes can then be BOUND to an expression,
so one edit rebuilds the whole model.

Everything here is deliberately small and honest: values are unitless
scalars spoken in the document's current measures; the expression
language is + - * / ** , parentheses, min/max/sqrt/abs/round and the
parameter names — evaluated on a whitelisted AST, never ``exec``,
because these expressions come out of a JSON file written by a
stranger.
"""
from __future__ import annotations

import ast
import math
import re

__all__ = ["ParamError", "eval_expr", "resolve", "parse_sheet"]

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_FUNCS = {"min": min, "max": max, "sqrt": math.sqrt, "abs": abs,
          "round": round}

_BINOPS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
           ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b,
           ast.Pow: lambda a, b: a ** b}


class ParamError(ValueError):
    """A parameter name, formula or sheet we cannot accept."""


def eval_expr(expr: str, values: dict | None = None) -> float:
    """Evaluate one formula over ``values`` (name -> float).  Raises
    ParamError on anything unknown, unsafe or arithmetically absurd."""
    values = values or {}
    text = str(expr).strip()
    if text.startswith("="):              # Fusion's fx cells carry a "="
        text = text[1:]
    if not text:
        raise ParamError("empty formula")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as e:
        raise ParamError(f"can't read formula {expr!r}: {e.msg}") from e
    try:
        return float(_ev(tree.body, values, expr))
    except ParamError:
        raise
    except ZeroDivisionError as e:
        raise ParamError(f"formula {expr!r} divides by zero") from e
    except Exception as e:
        raise ParamError(f"formula {expr!r} failed: {e}") from e


def _ev(n, values: dict, src: str):
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) \
            and not isinstance(n.value, bool):
        return n.value
    if isinstance(n, ast.Name):
        if n.id in values:
            return values[n.id]
        raise ParamError(f"unknown parameter {n.id!r} in {src!r}")
    if isinstance(n, ast.BinOp) and type(n.op) in _BINOPS:
        return _BINOPS[type(n.op)](_ev(n.left, values, src),
                                   _ev(n.right, values, src))
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd,
                                                        ast.USub)):
        v = _ev(n.operand, values, src)
        return v if isinstance(n.op, ast.UAdd) else -v
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
            and n.func.id in _FUNCS and not n.keywords:
        return _FUNCS[n.func.id](*[_ev(a, values, src) for a in n.args])
    raise ParamError(f"formula {src!r} uses something I won't run")


def resolve(raw: dict) -> dict:
    """Resolve a name -> formula sheet into name -> float, following
    references in dependency order.  Cycles and strays name
    themselves in the error."""
    values: dict = {}
    state: dict = {}                      # name -> "walk" | "done"

    def walk(name: str, chain: tuple) -> float:
        if name in values:
            return values[name]
        if state.get(name) == "walk":
            loop = " -> ".join(chain + (name,))
            raise ParamError(f"parameters form a circle: {loop}")
        if name not in raw:
            raise ParamError(f"unknown parameter {name!r}")
        state[name] = "walk"
        if not _NAME.match(name):
            raise ParamError(f"{name!r} is not a legal parameter name")
        values[name] = eval_expr(raw[name],
                                 {k: walk(k, chain + (name,))
                                  for k in _names(raw[name])})
        state[name] = "done"
        return values[name]

    for k in raw:
        walk(k, ())
    return values


def _names(expr: str) -> list:
    """Identifier names a formula references (excluding the whitelisted
    function names)."""
    try:
        tree = ast.parse(expr.lstrip("=").strip(), mode="eval")
    except SyntaxError:
        return []
    return sorted({n.id for n in ast.walk(tree)
                   if isinstance(n, ast.Name) and n.id not in _FUNCS})


def parse_sheet(text: str) -> dict:
    """Fusion's sheet, as typed text: one ``name = formula`` per line,
    blank lines and ``#`` comments allowed."""
    raw: dict = {}
    for i, line in enumerate(str(text).splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if "=" not in line:
            raise ParamError(f"line {i}: expected 'name = formula'")
        name, expr = (s.strip() for s in line.split("=", 1))
        if not _NAME.match(name or ""):
            raise ParamError(f"line {i}: {name!r} is not a legal "
                             "parameter name")
        if not expr:
            raise ParamError(f"line {i}: {name} has no formula")
        if name in raw:
            raise ParamError(f"line {i}: {name} is defined twice")
        raw[name] = expr
    resolve(raw)                          # refuses strays and cycles
    return raw


def parse_configs(text: str) -> dict:
    """M91: named configuration rows for the sheet —

        Small: width = 20, height = 10
        Large: width = 50        # one per line, # comments ok

    -> {'Small': {'width': '20', 'height': '10'}, ...}.  Values stay
    raw strings: they are formulas resolved against the merged sheet,
    exactly like the sheet itself (validated there, not here)."""
    out: dict = {}
    for i, line in enumerate(str(text).splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, sep, body = line.partition(":")
        if not sep or not name.strip() or not body.strip():
            raise ParamError(f"line {i}: expected 'Name: param = value'")
        entries: dict = {}
        for item in body.split(","):
            key, eq, val = item.partition("=")
            if not eq or not key.strip():
                raise ParamError(f"line {i}: {item.strip()!r} is not "
                                 "'name = value'")
            entries[key.strip()] = val.strip()
        out[name.strip()] = entries
    return out
