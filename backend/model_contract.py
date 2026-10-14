"""Stable identifiers for experimental model targets shown by the application."""

SYNTHETIC_DEMO_TARGET_COLUMN = "no_recorded_progress_30d"
SYNTHETIC_DEMO_TARGET_DEFINITION = (
    "1 when neither a Heard/Adjourned hearing-log event nor a judgment delivery is "
    "simulated within 30 days after snapshot_at; 0 when one is simulated in that "
    "window. QR scans and internal/admin changes are not progress. This is a "
    "fictional software-demo outcome, not a legal deadline or a court-derived label."
)
