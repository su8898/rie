"""Generic state-machine primitive (domain-logic §8).

Machines are declarative transition tables. `fire()` enforces them in the service layer:
illegal transition -> IllegalTransition (HTTP 409), wrong actor -> WrongActor (403), unmet gate
-> GateNotMet (409). Every successful transition writes an actor-stamped TransitionLog row.
ADMIN is a superuser (satisfies any role requirement).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from . import models


class IllegalTransition(Exception):
    """No such transition from the current state (409)."""


class WrongActor(Exception):
    """The actor's role may not perform this transition (403)."""


class GateNotMet(Exception):
    """A precondition (gate) for the transition is not satisfied (409)."""


@dataclass(frozen=True)
class T:
    src: str
    action: str
    dst: str
    roles: tuple[str, ...] = ()          # empty = any authenticated user


@dataclass(frozen=True)
class Machine:
    name: str
    state_attr: str
    transitions: tuple[T, ...]
    initial: str = ""
    terminal: frozenset[str] = field(default_factory=frozenset)

    def find(self, state: str, action: str) -> Optional[T]:
        for t in self.transitions:
            if t.src == state and t.action == action:
                return t
        return None

    def actions_from(self, state: str) -> list[str]:
        return [t.action for t in self.transitions if t.src == state]

    def states(self) -> set[str]:
        s = {self.initial} if self.initial else set()
        for t in self.transitions:
            s.add(t.src)
            s.add(t.dst)
        return s


def fire(db: Session, machine: Machine, entity, entity_id, action: str, user: dict,
         gate: Optional[Callable[[], None]] = None, detail: Optional[dict] = None) -> str:
    cur = getattr(entity, machine.state_attr)
    t = machine.find(cur, action)
    if t is None:
        raise IllegalTransition(f"{machine.name}: '{action}' not allowed from '{cur}'")
    role = user.get("role")
    if t.roles and role != "ADMIN" and role not in t.roles:
        raise WrongActor(f"{machine.name}.{action} requires one of {t.roles}, not {role}")
    if gate is not None:
        gate()                            # raises GateNotMet on failure
    setattr(entity, machine.state_attr, t.dst)
    db.add(models.TransitionLog(
        entity_type=machine.name, entity_id=str(entity_id), from_state=cur, to_state=t.dst,
        action=action, actor=user.get("username", "?"), role=role or "?", detail=detail or {}))
    return t.dst
