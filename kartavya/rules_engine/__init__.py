"""Rules engine — pure Python, YAML-driven, deterministic deadline calculation (§3.1, §3.5, §10.2).

The `RULE_ENGINE_VERSION` constant is stamped into every emitted `ActionPlan`
(see `ActionPlan.rule_engine_version`). Bump this on any change to engine
code or to YAML rule tables under `tables/` (§3.5 — every action plan must
trace back to an exact rule version).

Versioning convention: SemVer, but the prototype starts at 0.1.0 and bumps
the minor digit on rule additions / changes; the patch digit on engine
code changes that don't change rule semantics.
"""

RULE_ENGINE_VERSION = "0.2.0"

from kartavya.rules_engine.engine import (  # noqa: E402
    generate_action_plan,
    generate_actions,
)

__all__ = [
    "RULE_ENGINE_VERSION",
    "generate_action_plan",
    "generate_actions",
]
