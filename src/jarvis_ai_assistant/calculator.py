"""Safe arithmetic parsing and evaluation for Jarvis."""

from __future__ import annotations

import ast
import math
import operator
import re


class CalculationError(ValueError):
    """Raised when a math expression cannot be parsed or evaluated safely."""


class Calculator:
    """Parses natural-language arithmetic and evaluates it safely."""

    _BINARY_OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.Mod: operator.mod,
    }
    _UNARY_OPERATORS = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }
    _FUNCTIONS = {
        "sqrt": math.sqrt,
        "abs": abs,
        "round": round,
    }

    def can_handle(self, text: str) -> bool:
        """Return True when the utterance looks like a math request."""
        normalized = text.strip().lower()
        if not normalized:
            return False

        direct_expression = re.fullmatch(r"[\d\s\.\+\-\*\/\^\(\)%]+", normalized)
        if direct_expression and any(char.isdigit() for char in normalized):
            return True

        keyword_patterns = [
            r"\b(calculate|compute|solve|evaluate)\b",
            r"\b(square root|sqrt|percent of|percentage of|plus|minus|times|multiplied by|divided by|mod|modulo)\b",
        ]
        if any(re.search(pattern, normalized) for pattern in keyword_patterns):
            return bool(re.search(r"\d", normalized))

        if normalized.startswith("what is ") and re.search(r"\d", normalized) and re.search(
            r"[\+\-\*/\^()]|\b(plus|minus|times|divided by|multiplied by|percent of)\b",
            normalized,
        ):
            return True

        return False

    def evaluate(self, text: str) -> tuple[str, float]:
        """Evaluate a math query and return the normalized expression and result."""
        expression = self._normalize_expression(text)
        try:
            parsed = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise CalculationError("I could not parse that calculation.") from exc

        result = float(self._eval_node(parsed.body))
        return expression, result

    def _normalize_expression(self, text: str) -> str:
        normalized = text.strip().lower()
        normalized = normalized.replace(",", "")
        normalized = normalized.rstrip("?.!")
        normalized = re.sub(r"^(what is|calculate|compute|solve|evaluate)\s+", "", normalized)

        percent_match = re.fullmatch(
            r"(\d+(?:\.\d+)?)\s+(?:percent|percentage)\s+of\s+(\d+(?:\.\d+)?)",
            normalized,
        )
        if percent_match:
            return f"(({percent_match.group(1)})/100)*({percent_match.group(2)})"

        normalized = re.sub(r"square root of\s+([0-9\.\(\)\+\-\*/\s]+)", r"sqrt(\1)", normalized)
        normalized = re.sub(r"sqrt of\s+([0-9\.\(\)\+\-\*/\s]+)", r"sqrt(\1)", normalized)
        normalized = re.sub(r"sqrt\s+([0-9\.\(\)\+\-\*/\s]+)", r"sqrt(\1)", normalized)

        replacements = [
            ("multiplied by", "*"),
            ("times", "*"),
            ("x", "*"),
            ("divided by", "/"),
            ("over", "/"),
            ("plus", "+"),
            ("minus", "-"),
            ("modulo", "%"),
            ("mod", "%"),
            ("to the power of", "**"),
            ("power of", "**"),
            ("^", "**"),
        ]
        for source, target in replacements:
            normalized = normalized.replace(source, target)

        normalized = re.sub(r"\s+", " ", normalized).strip()
        normalized = normalized.replace(" ", "")
        if not normalized:
            raise CalculationError("I could not find a calculation in that command.")
        return normalized

    def _eval_node(self, node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)

        if isinstance(node, ast.BinOp) and type(node.op) in self._BINARY_OPERATORS:
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            return float(self._BINARY_OPERATORS[type(node.op)](left, right))

        if isinstance(node, ast.UnaryOp) and type(node.op) in self._UNARY_OPERATORS:
            return float(self._UNARY_OPERATORS[type(node.op)](self._eval_node(node.operand)))

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in self._FUNCTIONS:
            arguments = [self._eval_node(arg) for arg in node.args]
            return float(self._FUNCTIONS[node.func.id](*arguments))

        raise CalculationError("That calculation uses unsupported syntax.")
