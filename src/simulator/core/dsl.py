"""
Domain-Specific Language (DSL) for Safe Expression Evaluation

This module provides a safe, restricted expression evaluator for preconditions
and effects in the simulator. It uses AST whitelisting to prevent dangerous
operations while supporting qualitative reasoning patterns.

Key features:
- AST-based evaluation (no Python eval())
- Whitelist of allowed operations
- Support for implication syntax (A -> B)
- Qualitative reasoning operations (comparisons, boolean logic)

Supported syntax:
- Literals: "string", True, False, [list], (tuple)
- Variables: attribute_name, parameter_name
- Comparisons: ==, !=, in, not in
- Boolean logic: and, or, not
- Conditionals: value if condition else other_value  
- Implications: A -> B (converted to (not A) or B)
"""

from __future__ import annotations
import ast
from typing import Any, Dict, Set

# Whitelist of allowed AST node types for security
ALLOWED_NODES: Set[type] = {
    ast.Expression,    # Top-level expression wrapper
    ast.BoolOp,       # Boolean operations (and, or)
    ast.And, ast.Or, ast.Not,  # Boolean operators
    ast.UnaryOp,      # Unary operations (not)
    ast.Compare,      # Comparison operations
    ast.Name,         # Variable names
    ast.Load,         # Variable loading context
    ast.Constant,     # Literal constants
    ast.List,         # List literals
    ast.Tuple,        # Tuple literals
    ast.In, ast.NotIn,    # Membership operators
    ast.Eq, ast.NotEq,    # Equality operators
    ast.IfExp         # Conditional expressions (ternary)
}


def _rewrite_implication(expr: str) -> str:
    """
    Rewrite implication syntax (A -> B) to equivalent boolean logic.
    
    Converts "A -> B" to "(not A) or B", which is logically equivalent.
    Supports chained implications like "A -> B -> C".
    
    Args:
        expr: Expression string potentially containing implications
        
    Returns:
        Expression with implications converted to boolean logic
        
    Examples:
        >>> _rewrite_implication('battery != "empty" -> switch == "on"')
        '(not (battery != "empty")) or (switch == "on")'
        >>> _rewrite_implication('A -> B -> C')
        '(not ((not (A)) or (B))) or (C)'
    """
    if '->' not in expr:
        return expr
        
    parts = expr.split('->')
    if len(parts) == 2:
        # Simple case: A -> B becomes (not A) or B
        left, right = parts[0].strip(), parts[1].strip()
        return f"(not ({left})) or ({right})"
    
    # Recursive case for chained implications: A -> B -> C
    # Process as A -> (B -> C)
    left = '->'.join(parts[:-1])
    right = parts[-1].strip()
    return f"(not ({_rewrite_implication(left)})) or ({_rewrite_implication(right)})"


def _validate_ast(node: ast.AST) -> None:
    """
    Recursively validate that an AST only contains whitelisted node types.
    
    This is our primary security mechanism - by only allowing specific
    AST node types, we prevent dangerous operations like function calls,
    imports, attribute access, etc.
    
    Args:
        node: AST node to validate
        
    Raises:
        ValueError: If any node type is not in the whitelist
    """
    if type(node) not in ALLOWED_NODES:
        raise ValueError(f"Disallowed syntax: {type(node).__name__}")
    
    # Recursively validate all child nodes
    for child in ast.iter_child_nodes(node):
        _validate_ast(child)


def eval_expr(expr: str, ctx: Dict[str, Any]) -> Any:
    """
    Safely evaluate a DSL expression in the given context.
    
    This is the main entry point for expression evaluation. It handles
    implication rewriting, AST validation, and safe evaluation.
    
    Args:
        expr: Expression string to evaluate
        ctx: Context dictionary mapping variable names to values
        
    Returns:
        Result of evaluating the expression
        
    Raises:
        ValueError: If the expression contains disallowed syntax
        KeyError: If the expression references unknown variables
        
    Examples:
        >>> ctx = {"switch": "on", "battery": "high"}
        >>> eval_expr('switch == "on"', ctx)
        True
        >>> eval_expr('battery != "empty" -> switch == "on"', ctx)
        True
        >>> eval_expr('"high" if battery == "high" else "low"', ctx)
        'high'
    """
    # Step 1: Rewrite implications to boolean logic
    code = _rewrite_implication(expr)
    
    # Step 2: Parse into AST
    try:
        tree = ast.parse(code, mode='eval')
    except SyntaxError as e:
        raise ValueError(f"Invalid expression syntax: {expr}") from e
    
    # Step 3: Validate AST contains only whitelisted operations
    _validate_ast(tree)
    
    # Step 4: Safely evaluate the AST
    return _eval_node(tree.body, ctx)


def _eval_node(node: ast.AST, ctx: Dict[str, Any]) -> Any:
    """
    Recursively evaluate an AST node in the given context.
    
    This function handles each type of allowed AST node and evaluates
    it appropriately. It's the core of our safe evaluation engine.
    
    Args:
        node: AST node to evaluate
        ctx: Context dictionary for variable resolution
        
    Returns:
        Result of evaluating the node
        
    Raises:
        ValueError: If node type is unsupported or operation is invalid
        KeyError: If variable name is not found in context
    """
    # Literal constants (strings, booleans)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (str, bool)):
            return node.value
        raise ValueError("Only string and bool constants are allowed")
    
    # Variable names (attributes, parameters)
    if isinstance(node, ast.Name):
        if node.id not in ctx:
            available_vars = ", ".join(sorted(ctx.keys()))
            raise KeyError(f"Unknown identifier: {node.id}. Available: {available_vars}")
        return ctx[node.id]
    
    # List literals
    if isinstance(node, ast.List):
        return [_eval_node(elt, ctx) for elt in node.elts]
    
    # Tuple literals
    if isinstance(node, ast.Tuple):
        return tuple(_eval_node(elt, ctx) for elt in node.elts)
    
    # Unary operations (currently just 'not')
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not bool(_eval_node(node.operand, ctx))
    
    # Boolean operations (and, or)
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            # Short-circuit evaluation for 'and'
            for value_node in node.values:
                result = bool(_eval_node(value_node, ctx))
                if not result:
                    return False
            return True
        
        if isinstance(node.op, ast.Or):
            # Short-circuit evaluation for 'or'
            for value_node in node.values:
                result = bool(_eval_node(value_node, ctx))
                if result:
                    return True
            return False
    
    # Comparison operations
    if isinstance(node, ast.Compare):
        # We only support single comparisons (no chaining like a < b < c)
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise ValueError("Chained comparisons are not supported")
        
        left = _eval_node(node.left, ctx)
        right = _eval_node(node.comparators[0], ctx)
        op = node.ops[0]
        
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
        if isinstance(op, ast.In):
            return left in right
        if isinstance(op, ast.NotIn):
            return left not in right
        
        raise ValueError("Only ==, !=, in, not in comparison operators are supported")
    
    # Conditional expressions (ternary operator)
    if isinstance(node, ast.IfExp):
        condition = bool(_eval_node(node.test, ctx))
        if condition:
            return _eval_node(node.body, ctx)
        else:
            return _eval_node(node.orelse, ctx)
    
    # If we reach here, we encountered an unsupported node type
    raise ValueError(f"Unsupported expression node: {type(node).__name__}")


def validate_expression_syntax(expr: str) -> None:
    """
    Validate that an expression has valid syntax without evaluating it.
    
    Useful for validating action definitions during loading without
    needing a specific context.
    
    Args:
        expr: Expression string to validate
        
    Raises:
        ValueError: If the expression has invalid syntax or disallowed operations
    """
    try:
        code = _rewrite_implication(expr)
        tree = ast.parse(code, mode='eval')
        _validate_ast(tree)
    except SyntaxError as e:
        raise ValueError(f"Invalid expression syntax: {expr}") from e