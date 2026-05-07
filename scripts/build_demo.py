"""Build the static demo artifacts under ./public for Vercel.

Reuses kartavya.main._build_plan + _jinja_env so the static demo renders
exactly the same HTML and JSON the FastAPI dev server serves. Run after
any change to the pipeline, the template, or the demo case set.

Layout produced:
    public/
        index.html
        api/plan/<slug>.json   (one per CASES entry)
        pdf/<slug>.pdf         (copied from tests/fixtures)

Vercel rewrites in vercel.json map the JS-expected URLs
(/api/plan/<slug> and /pdf/<slug>) to these files, so no template or
JS changes are needed.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from kartavya.main import CASES, _PLAN_CACHE, _build_plan, _jinja_env  # noqa: E402

PUBLIC = REPO / "public"


def main() -> None:
    if PUBLIC.exists():
        shutil.rmtree(PUBLIC)
    (PUBLIC / "api" / "plan").mkdir(parents=True)
    (PUBLIC / "pdf").mkdir(parents=True)

    _PLAN_CACHE.clear()
    cases_view = []
    for slug, cfg in CASES.items():
        plan = _build_plan(slug)
        (PUBLIC / "api" / "plan" / f"{slug}.json").write_text(
            json.dumps(plan, default=str, indent=2)
        )
        shutil.copy(cfg["pdf"], PUBLIC / "pdf" / f"{slug}.pdf")
        cases_view.append({"slug": slug, "label": cfg["label"]})

    html = _jinja_env.get_template("review.html").render(cases=cases_view)
    (PUBLIC / "index.html").write_text(html)

    print(f"Built {PUBLIC.relative_to(REPO)} with {len(CASES)} case(s).")


if __name__ == "__main__":
    main()
