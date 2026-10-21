"""Small, intentionally restricted expression evaluator; Python eval is never used."""
from __future__ import annotations
import ast
import re
from typing import Any


class ExpressionError(ValueError):
    pass


def validate_expression(expression: str, allowed_names: set[str] | None = None) -> None:
    """Validate syntax and the evaluator's safe AST subset without evaluating it."""
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 4096:
        raise ExpressionError("Expression must contain 1–4,096 characters")
    text = expression.strip()
    if text.startswith("="):
        text = text[1:].strip()
    try:
        root = ast.parse(text, mode="eval").body
    except SyntaxError as exc:
        raise ExpressionError(f"Invalid expression: {exc.msg}") from exc

    functions = {"len", "str", "int", "float", "bool", "lower", "upper", "contains", "starts_with"}
    binary = {ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod}
    unary = {ast.Not, ast.USub, ast.UAdd}
    comparisons = {ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn}

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (str, int, float, bool, type(None))):
                raise ExpressionError("Expression constant type is not supported")
        elif isinstance(node, ast.Name):
            if allowed_names is not None and node.id not in allowed_names:
                raise ExpressionError(f"Variable '{node.id}' is not available in this expression")
        elif isinstance(node, (ast.List, ast.Tuple)):
            for item in node.elts:
                visit(item)
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if key is None:
                    raise ExpressionError("Dictionary unpacking is not supported")
                visit(key); visit(value)
        elif isinstance(node, ast.Subscript):
            visit(node.value); visit(node.slice)
        elif isinstance(node, ast.Slice):
            for item in (node.lower, node.upper, node.step):
                if item is not None: visit(item)
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                raise ExpressionError("Private properties are not supported")
            visit(node.value)
        elif isinstance(node, ast.UnaryOp) and type(node.op) in unary:
            visit(node.operand)
        elif isinstance(node, ast.BoolOp) and type(node.op) in {ast.And, ast.Or}:
            for item in node.values: visit(item)
        elif isinstance(node, ast.Compare):
            if any(type(op) not in comparisons for op in node.ops):
                raise ExpressionError("Comparison operator is not supported")
            visit(node.left)
            for item in node.comparators: visit(item)
        elif isinstance(node, ast.BinOp) and type(node.op) in binary:
            visit(node.left); visit(node.right)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in functions and not node.keywords:
            for item in node.args: visit(item)
        else:
            raise ExpressionError(f"Expression element is not allowed: {type(node).__name__}")

    visit(root)


def evaluate(expression: str, variables: dict[str, Any]) -> Any:
    text = expression.strip()
    if text.startswith("="):
        text = text[1:].strip()
    try:
        root = ast.parse(text, mode="eval").body
    except SyntaxError as exc:
        raise ExpressionError(f"Invalid expression: {exc.msg}") from exc

    def visit(node: ast.AST) -> Any:
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool, type(None))):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise ExpressionError(f"Unknown variable '{node.id}'")
            return variables[node.id]
        if isinstance(node, ast.List):
            return [visit(x) for x in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(visit(x) for x in node.elts)
        if isinstance(node, ast.Dict):
            return {visit(k): visit(v) for k, v in zip(node.keys, node.values)}
        if isinstance(node, ast.Subscript):
            return visit(node.value)[visit(node.slice)]
        if isinstance(node, ast.Slice):
            return slice(visit(node.lower) if node.lower else None, visit(node.upper) if node.upper else None, visit(node.step) if node.step else None)
        if isinstance(node, ast.Attribute) and not node.attr.startswith("_"):
            value = visit(node.value)
            if isinstance(value, dict) and node.attr in value:
                return value[node.attr]
            raise ExpressionError(f"Property '{node.attr}' is available only on objects represented as mappings")
        if isinstance(node, ast.UnaryOp) and type(node.op) in {ast.Not, ast.USub, ast.UAdd}:
            v = visit(node.operand)
            return {ast.Not: lambda: not v, ast.USub: lambda: -v, ast.UAdd: lambda: +v}[type(node.op)]()
        if isinstance(node, ast.BoolOp) and type(node.op) in {ast.And, ast.Or}:
            values = [visit(x) for x in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.Compare):
            left = visit(node.left)
            ops = {ast.Eq: lambda a,b: a == b, ast.NotEq: lambda a,b: a != b, ast.Lt: lambda a,b: a < b,
                   ast.LtE: lambda a,b: a <= b, ast.Gt: lambda a,b: a > b, ast.GtE: lambda a,b: a >= b,
                   ast.In: lambda a,b: a in b, ast.NotIn: lambda a,b: a not in b}
            for op, comp in zip(node.ops, node.comparators):
                if type(op) not in ops:
                    raise ExpressionError("Comparison operator is not supported")
                right = visit(comp)
                if not ops[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.BinOp) and type(node.op) in {ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod}:
            left, right = visit(node.left), visit(node.right)
            return {ast.Add: lambda: left + right, ast.Sub: lambda: left - right, ast.Mult: lambda: left * right,
                    ast.Div: lambda: left / right, ast.FloorDiv: lambda: left // right, ast.Mod: lambda: left % right}[type(node.op)]()
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"len", "str", "int", "float", "bool", "lower", "upper", "contains", "starts_with"} and not node.keywords:
            args = [visit(arg) for arg in node.args]
            funcs = {"len": len, "str": str, "int": int, "float": float, "bool": bool,
                     "lower": lambda v: str(v).lower(), "upper": lambda v: str(v).upper(),
                     "contains": lambda a,b: b in a, "starts_with": lambda a,b: str(a).startswith(str(b))}
            try:
                return funcs[node.func.id](*args)
            except (TypeError, ValueError) as exc:
                raise ExpressionError(f"Function {node.func.id} failed: {exc}") from exc
        raise ExpressionError(f"Expression element is not allowed: {type(node).__name__}")

    return visit(root)


_INTERPOLATION = re.compile(r"\{\{\s*(.*?)\s*\}\}")
def interpolate(value: Any, variables: dict[str, Any]) -> Any:
    if not isinstance(value, str):
        return value
    matches = list(_INTERPOLATION.finditer(value))
    if len(matches) == 1 and matches[0].span() == (0, len(value)):
        return evaluate(matches[0].group(1), variables)
    return _INTERPOLATION.sub(lambda m: str(evaluate(m.group(1), variables)), value)
