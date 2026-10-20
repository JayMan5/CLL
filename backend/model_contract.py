"""Stable identifiers and definitions for synthetic model targets."""

SYNTHETIC_DEMO_TARGET_COLUMN = "no_recorded_progress_30d"
SYNTHETIC_DEMO_TARGET_DEFINITION = (
    "1 when neither a Heard/Adjourned hearing-log event nor a judgment delivery is "
    "simulated within 30 days after snapshot_at; 0 when one is simulated in that "
    "window. QR scans and internal/admin changes are not progress. This is a "
    "fictional software-demo outcome, not a legal deadline or a court-derived label."
)

SYNTHETIC_DURATION_TARGET_COLUMN = "synthetic_days_to_next_progress"
SYNTHETIC_DURATION_CASE_TYPES = (
    "Fictional Civil Claim",
    "Fictional Land Matter",
    "Fictional Criminal Appeal",
    "Fictional Commercial Appeal",
)
SYNTHETIC_DURATION_COURTS = (
    "Synthetic Court A",
    "Synthetic Court B",
    "Synthetic Court C",
    "Synthetic Court D",
)
SYNTHETIC_DURATION_TARGET_DEFINITION = (
    "Fictional elapsed days from snapshot_at until the next simulated qualifying "
    "Heard/Adjourned hearing-log event or judgment delivery. This is a synthetic "
    "software-demo duration, not an observed court outcome, case-resolution time, "
    "legal deadline, or calibrated real-world forecast."
)
