"""Confidence gate interface retained for Phase 4 integration."""


class ConfidenceGate:
    """Constructible dependency; no confidence-policy enforcement is claimed."""

    def __init__(self):
        self.available = False
