from __future__ import annotations
from typing import Dict, List
import copy
import re
from .actions import ActionType, TransitionResult, DiffEntry
from .dsl import eval_expr
from .state import ObjectState
from .object_types import ObjectType


_ASSIGN_RE = re.compile(r"^(.+?)\s*=\s*(.+)$")
_INCDEC_RE = re.compile(r"^(?P<attr>\w+)\s+(?P<op>inc|dec)$")
_TREND_TARGET_RE = re.compile(r"^(?P<attr>\w+)\s+trend$", re.IGNORECASE)


class ActionEngine:
    def __init__(self, obj_type: ObjectType):
        self.obj_type = obj_type

    def apply(self, state: ObjectState, action: ActionType, params: Dict[str, str]) -> TransitionResult:
        if action.object_type != self.obj_type.name:
            return TransitionResult(before=state, after=None, status="rejected",
                                    reason=f"Action {action.name} not valid for {self.obj_type.name}")

        for pname, spec in action.parameters.items():
            if pname not in params:
                return TransitionResult(before=state, after=None, status="rejected",
                                        reason=f"Missing parameter: {pname}")
            if spec.space is not None and params[pname] not in spec.space:
                return TransitionResult(before=state, after=None, status="rejected",
                                        reason=f"Parameter {pname} must be in {spec.space}")

        ctx = {**state.values, **params}

        for cond in action.preconditions:
            try:
                ok = bool(eval_expr(cond, ctx))
            except Exception as e:
                return TransitionResult(before=state, after=None, status="rejected",
                                        reason=f"Precondition error: {cond!r}: {e}")
            if not ok:
                return TransitionResult(before=state, after=None, status="rejected",
                                        reason=f"Precondition failed: {cond}")

        new_state = copy.deepcopy(state)
        diffs: List[DiffEntry] = []

        for eff in action.effects:
            eff = eff.strip()
            if not eff:
                continue

            m = _INCDEC_RE.match(eff)
            if m:
                attr = m.group("attr")
                op = m.group("op")
                if attr not in self.obj_type.attributes:
                    return TransitionResult(before=state, after=None, status="rejected",
                                            reason=f"Unknown attribute in effect: {attr}")
                attr_type = self.obj_type.attributes[attr]
                old = new_state.values[attr]
                direction = "up" if op == "inc" else "down"
                new = attr_type.space.step(old, direction)
                if new != old:
                    diffs.append(DiffEntry(attribute=attr, before=old, after=new, kind="value"))
                    new_state.values[attr] = new
                continue

            m = _ASSIGN_RE.match(eff)
            if not m:
                return TransitionResult(before=state, after=None, status="rejected",
                                        reason=f"Malformed effect (expected assignment or inc/dec): {eff}")
            lhs, rhs = m.group(1).strip(), m.group(2).strip()

            tm = _TREND_TARGET_RE.match(lhs)
            if tm:
                attr = tm.group("attr")
                if attr not in self.obj_type.attributes:
                    return TransitionResult(before=state, after=None, status="rejected",
                                            reason=f"Unknown attribute in trend target: {attr}")
                try:
                    val = eval_expr(rhs, ctx)
                except Exception as e:
                    return TransitionResult(before=state, after=None, status="rejected",
                                            reason=f"Effect eval error: {eff!r}: {e}")
                if val not in ("up","down","none"):
                    return TransitionResult(before=state, after=None, status="rejected",
                                            reason=f"Invalid trend value: {val!r}")
                old = new_state.trends.get(attr, "none")
                if old != val:
                    diffs.append(DiffEntry(attribute=f"{attr}.trend", before=old, after=val, kind="trend"))
                    new_state.trends[attr] = val
                continue

            attr = lhs
            if attr not in self.obj_type.attributes:
                return TransitionResult(before=state, after=None, status="rejected",
                                        reason=f"Unknown attribute in effect: {attr}")
            try:
                val = eval_expr(rhs, ctx)
            except Exception as e:
                return TransitionResult(before=state, after=None, status="rejected",
                                        reason=f"Effect eval error: {eff!r}: {e}")
            if not isinstance(val, str):
                return TransitionResult(before=state, after=None, status="rejected",
                                        reason=f"Effect must assign string to attribute {attr}, got {val!r}")
            space = self.obj_type.attributes[attr].space
            if not space.has(val):
                return TransitionResult(before=state, after=None, status="rejected",
                                        reason=f"Assigned value {val!r} not in space {space.levels!r}")
            old = new_state.values[attr]
            if old != val:
                diffs.append(DiffEntry(attribute=attr, before=old, after=val, kind="value"))
                new_state.values[attr] = val

            ctx[attr] = val

        return TransitionResult(before=state, after=new_state, status="ok", diff=diffs)