"""Solver module for applying high-level world rules.

The Solver applies implication rules that derive state from other state.
Unlike constraints (which fix violations), solver rules define causal relationships.
"""

from simulator.core.solver.rule import SolverCase, SolverRule
from simulator.core.solver.solver_branching import SolverBranchInfo, apply_solver_rules
from simulator.core.solver.solver_engine import SolverEngine
from simulator.core.solver.specs import (
    SolverCaseSpec,
    SolverRuleSpec,
    parse_solver_rule_spec,
)

__all__ = [
    "SolverRule",
    "SolverCase",
    "SolverEngine",
    "SolverBranchInfo",
    "apply_solver_rules",
    "SolverRuleSpec",
    "SolverCaseSpec",
    "parse_solver_rule_spec",
]
