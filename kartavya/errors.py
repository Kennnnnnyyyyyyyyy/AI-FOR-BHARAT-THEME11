"""Domain errors for Kartavya. API translates these to HTTP in `api/error_handlers.py` (§9)."""


class KartavyaError(Exception):
    """Root domain error."""


class ExtractionFailed(KartavyaError):
    """Raised when an LLM call cannot be parsed into the target schema after one retry (§3.6)."""


class AuditInvariantError(KartavyaError):
    """Raised by `audit.record(...)` when a recorded event violates a Tier-1 invariant (§10.3)."""


class AnchorMismatch(KartavyaError):
    """Raised when the LLM echoes an anchor token that is not in the chunk's anchor map (§3.4)."""


class SpanMismatch(KartavyaError):
    """Raised when a returned `source_span` is not a substring of its claimed paragraph (§3.4)."""
