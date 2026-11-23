"""CourtLOG pilot role names, feature entitlements, and safe legacy-role migration helpers.

This module describes the currently approved pilot role/access vocabulary from the
CourtLOG workflow document. Deferred roles are deliberately not assignable.
"""

from __future__ import annotations

import os
from typing import Optional

CHIEF_JUDGE = "Chief Judge"
CHIEF_REGISTRAR = "Chief Registrar"
DEPUTY_CHIEF_REGISTRAR = "Deputy Chief Registrar"
REGISTRAR = "Registrar"
FILING_CLERK = "Filing Clerk"
REGISTRY_CLERK = "Registry Clerk"
COURT_CLERK = "Court Clerk"
BAILIFF = "Bailiff"
SHERIFF = "Sheriff"
PRESIDING_JUDGE = "Presiding Judge"
ROLE_ASSIGNMENT_REQUIRED = "Role Assignment Required"

# Active staff roles in the pilot scope. Court Clerk is assignable only when the
# deployment has the server-side court_clerk entitlement enabled.
PILOT_ROLES = (
    CHIEF_JUDGE,
    CHIEF_REGISTRAR,
    DEPUTY_CHIEF_REGISTRAR,
    REGISTRAR,
    FILING_CLERK,
    REGISTRY_CLERK,
    COURT_CLERK,
    BAILIFF,
    SHERIFF,
    PRESIDING_JUDGE,
)

DEFERRED_ROLES = (
    "Cashier / Fees Clerk",
    "Counsel",
    "Counsel's Clerk",
    "Appellate Justice",
    "Appellate Registry Clerk",
)

ROLE_REQUIRED_FEATURE = {COURT_CLERK: "court_clerk"}

# The old Clerk role combined several duties and cannot be safely inferred as one
# of the three new clerk roles. The account must be explicitly remapped by a Chief
# Registrar. DCR and Judge have clear one-to-one pilot successors.
LEGACY_ROLE_RENAMES = {
    "DCR": DEPUTY_CHIEF_REGISTRAR,
    "Judge": PRESIDING_JUDGE,
}
LEGACY_ROLE_REMAP = {"Clerk": ROLE_ASSIGNMENT_REQUIRED}


def enabled_paid_features() -> set[str]:
    """Return server-provisioned feature entitlements from COURTLOG_PAID_FEATURES."""
    raw = os.getenv("COURTLOG_PAID_FEATURES", "")
    allowed = set(ROLE_REQUIRED_FEATURE.values())
    return {
        item.strip().casefold()
        for item in raw.split(",")
        if item.strip().casefold() in allowed
    }


def required_feature_for_role(role: str) -> Optional[str]:
    return ROLE_REQUIRED_FEATURE.get(role)


def role_is_licensed(role: str) -> bool:
    feature = required_feature_for_role(role)
    return feature is None or feature.casefold() in enabled_paid_features()


def role_is_assignable(role: str) -> bool:
    return role in PILOT_ROLES and role_is_licensed(role)


def canonical_legacy_role(role: str) -> Optional[str]:
    """Return a safe canonical replacement, or None for roles needing manual review."""
    if role in LEGACY_ROLE_RENAMES:
        return LEGACY_ROLE_RENAMES[role]
    return LEGACY_ROLE_REMAP.get(role)
