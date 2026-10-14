"""A tiny arithmetic tool Wale can *use* instead of trying to recall sums.

Given a message, ``solve`` digs out an arithmetic expression (digits, operators,
brackets), evaluates it safely with a restricted AST walk — no ``eval`` of raw
text — and returns the answer. Messages with no real sum come back as None.

    >>> solve("what is 4 + 4?")
    {'expr': '4 + 4', 'value': '8'}
"""

import ast
import re

_ALLOWED = set("0123456789+-*/()%.^ ")
_OPERATORS = set("+-*/%^")
_UNICODE = {
    "×": "*", "✕": "*", "·": "*",
    "÷": "/", "∕": "/",
    "−": "-", "–": "-", "—": "-",
    "＋": "+", "＝": "=",
}
_MAX_POW = 1000


def _runs(text):
    """Maximal stretches made only of arithmetic characters (words break them)."""
    runs, cur = [], ""
    for ch in text:
        if ch in _ALLOWED:
            cur += ch
        else:
            if cur.strip():
                runs.append(cur.strip())
            cur = ""
    if cur.strip():
        runs.append(cur.strip())
    return runs


def _candidate(run):
    """A run is worth evaluating only if it has a digit *and* an operator, and
    isn't a bare '4' or a dangling '4 +'."""
    has_digit = any(c.isdigit() for c in run)
    has_op = any(c in _OPERATORS for c in run)
    if not has_digit or not has_op:
        return None
    if not re.fullmatch(r"[0-9+\-*/()%.^ ]+", run):
        return None
    if run[-1] in _OPERATORS or run[0] in "*/%^.":
        return None
    return run


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError("bad constant")
        return node.value
    if isinstance(node, ast.UnaryOp):
        val = _eval(node.operand)
        if isinstance(node.op, ast.USub):
            return -val
        if isinstance(node.op, ast.UAdd):
            return val
        raise ValueError("bad unary op")
    if isinstance(node, ast.BinOp):
        left, right = _eval(node.left), _eval(node.right)
        op = node.op
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, ast.Div):
            if right == 0:
                raise ZeroDivisionError
            return left / right
        if isinstance(op, ast.Mod):
            if right == 0:
                raise ZeroDivisionError
            return left % right
        if isinstance(op, ast.Pow):
            if abs(right) > _MAX_POW:
                raise ValueError("exponent too big")
            return left ** right
        raise ValueError("bad binary op")
    raise ValueError("bad node")


def _format(value):
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.10g}"
    return str(value)


def solve(message):
    """Return ``{"expr", "value"}`` for the best arithmetic run, or None."""
    if not message:
        return None
    text = (message or "").lower()
    for src, dst in _UNICODE.items():
        text = text.replace(src, dst)
    best = None
    for run in _runs(text):
        expr = _candidate(run)
        if not expr:
            continue
        try:
            tree = ast.parse(expr.replace("^", "**"), mode="eval")
            value = _eval(tree)
        except (SyntaxError, ValueError, ZeroDivisionError, OverflowError):
            continue
        if best is None or len(expr) > len(best[0]):
            best = (expr, value)
    if best is None:
        return None
    return {"expr": re.sub(r"\s+", " ", best[0]).strip(), "value": _format(best[1])}
