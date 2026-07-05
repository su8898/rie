"""Vocabulary — enums, the reason-meta shape, scoring constants (domain-logic §10).

Pure stdlib. This module has no internal dependencies; everything else imports from here.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class LegalStatus(Enum):           # §3 — benchmark sources carry legal status
    ENFORCEABLE = auto()           # negotiated rates, SEP+fee, authorisations
    ACCEPTED = auto()              # RPL — provider-accepted market rate
    INTERDICTED = auto()           # RAF 2022 tariff — signal only
    ENDOGENOUS = auto()            # empirical medians — signal only


PAYMENT_RULE_STATUSES = {LegalStatus.ENFORCEABLE, LegalStatus.ACCEPTED}


class Maturity(Enum):              # §1 — defensibility layer
    GROUNDED = auto()              # statute / case law / regulation cited
    HEURISTIC = auto()             # reasonable rule, stated weakness
    UNVALIDATED = auto()           # not yet calibrated


class SignalMode(Enum):            # §11 — promotion lifecycle
    SHADOW = auto()                # computed, stored, zero points, invisible
    ADVISORY = auto()              # visible, zero points
    SCORED = auto()                # contributes to band


class Category(Enum):              # §9 — disposition, worst-first
    FRAUD = 1
    MERITS = 2
    COMPLIANCE = 3
    PREAUTH = 4
    SI_GATE = 5
    ADJUSTED = 6
    CLEAN = 7


class Band(Enum):
    GREEN = auto()
    AMBER = auto()
    RED = auto()


AMBER_AT, RED_AT = 25, 50
ENDOGENOUS_POINT_CAP = 45          # endogenous signals alone can never reach RED (§10)


@dataclass(frozen=True)
class ReasonMeta:
    category: Category
    hard: bool                     # hard gate vs soft feature
    points: int                    # soft-feature score contribution when SCORED
    maturity: Maturity
    endogenous: bool = False       # counts toward the endogenous cap
    basis: str = ""                # citation or stated weakness
