"""calculator araci — guvenli aritmetik (eval YOK, AST beyaz listesi)."""
import ast
import math
import operator

from . import ToolSpec, register_tool

_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {k: getattr(math, k) for k in (
    "sqrt", "sin", "cos", "tan", "log", "log2", "log10", "exp",
    "floor", "ceil", "fabs", "atan", "asin", "acos", "degrees", "radians",
)}
_FUNCS.update({"abs": abs, "round": round, "min": min, "max": max})
_CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


def _ev(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ValueError("izinsiz sabit")
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_ev(node.left), _ev(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_ev(node.operand))
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in _FUNCS and not node.keywords):
        return _FUNCS[node.func.id](*[_ev(a) for a in node.args])
    raise ValueError("izinsiz ifade")


async def _run(args: dict):
    expr = (args or {}).get("expression", "")
    expr = expr.strip() if isinstance(expr, str) else ""
    if not expr:
        return "Bos ifade."
    try:
        tree = ast.parse(expr, mode="eval")
        return f"{expr} = {_ev(tree.body)}"
    except Exception as e:
        return f"Hesaplanamadi: {e}"


register_tool(ToolSpec(
    name="calculator",
    description=(
        "Aritmetik/matematik ifadelerini kesin hesaplar (+ - * / ** % // ve "
        "sqrt, sin, cos, log, exp, pi gibi). Sayisal kesinlik gereken her yerde kullan; "
        "kafadan hesaplama."
    ),
    parameters={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Hesaplanacak matematik ifadesi, orn '2*(3+4)**2' veya 'sqrt(144)'.",
            }
        },
        "required": ["expression"],
    },
    run=_run,
))
