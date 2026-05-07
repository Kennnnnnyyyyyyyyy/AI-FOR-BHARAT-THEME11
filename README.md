# Kartavya

Compliance-operations layer over the Karnataka High Court CCMS. Converts disposed-judgment PDFs into deadline-bound, role-targeted action plans for government officers.

**Live demo:** _\<paste your Vercel URL here once deployed\>_

---

## Prerequisites

- **Python 3.11 or newer**
- **git** and **make**
- _(Windows users: run everything inside WSL2.)_

```bash
# macOS:    brew install python@3.11 git make
# Ubuntu:   sudo apt install python3.11 python3.11-venv git make
```

## Setup (once)

```bash
git clone git@github.com:Kennnnnnyyyyyyyyy/AI-FOR-BHARAT-THEME11.git
cd AI-FOR-BHARAT-THEME11
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

## Try the demo (CLI)

```bash
make demo-venkateshulu   # dismissed case  → 1 SLP-monitor card
make demo-positive       # 3 directives    → 3 obligation cards
```

You should see a formatted action plan printed to the terminal, with deadlines, target officer designations, and statute citations.

## See the UI

```bash
make dev
# then open http://localhost:8000
```

Split-screen: judgment PDF on the left, action plan on the right. Switch between the two demo cases with the dropdown in the header.

## Run the tests

```bash
pytest
```

Expect **144 passed, 1 skipped**.

---

That's it. You don't need Docker, Postgres, Redis, or Ollama for the demo — the demo CLI uses stubbed LLM clients so everything runs offline.
