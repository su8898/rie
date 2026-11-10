"""Vocabulary — enums, the reason-meta shape, scoring constants (domain-logic §10).

Pure stdlib. This module has no internal dependencies; everything else imports from here.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
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
    REVIEW = 6                     # no benchmark for a billed code — R&N review before payment (§3)
    ADJUSTED = 7
    CLEAN = 8


class Band(Enum):
    GREEN = auto()
    AMBER = auto()
    RED = auto()


AMBER_AT, RED_AT = 25, 50
ENDOGENOUS_POINT_CAP = 45          # endogenous signals alone can never reach RED (§10)

# Money is exact. Every rand figure is computed in Decimal and rounded half-up to the cent at
# the engine boundary; the record carries floats only as a JSON representation of those cents.
CENT = Decimal("0.01")


def D(x) -> Decimal:
    """Exact decimal of a rand/quantity input (floats via their shortest repr: 100.05 -> 100.05)."""
    return x if isinstance(x, Decimal) else Decimal(repr(x)) if isinstance(x, float) else Decimal(x)


def money(x) -> float:
    """Round to the cent, half-up (R70.035 -> R70.04), as a float for the JSON record."""
    return float(D(x).quantize(CENT, rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class ReasonMeta:
    category: Category
    hard: bool                     # hard gate vs soft feature
    points: int                    # soft-feature score contribution when SCORED
    maturity: Maturity
    endogenous: bool = False       # counts toward the endogenous cap
    basis: str = ""                # citation or stated weakness
