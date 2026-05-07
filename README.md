# Kartavya

Compliance-operations layer over the Karnataka High Court CCMS. Converts disposed-judgment PDFs into deadline-bound, role-targeted action plans for government officers.

**Live demo:**  [here](https://ai-for-bharat-theme-11.vercel.app/)

---

## Prerequisites

- **Python 3.11 or newer**
- **git** and **make** _(make is needed on macOS/Linux/WSL; Windows-native users can skip it — see the [Windows (no WSL)](#windows-no-wsl) section below)_

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

## Windows (no WSL)

If you're on Windows and don't want WSL, you can run everything natively. You just skip `make` and call Python directly.

**1. Install** (one-time):
- Python 3.11 from <https://www.python.org/downloads/> — check **"Add Python to PATH"** during install.
- Git from <https://git-scm.com/download/win>.

**2. Open Command Prompt (CMD)** — the simplest shell. Then:

```cmd
git clone https://github.com/Kennnnnnyyyyyyyyy/AI-FOR-BHARAT-THEME11.git
cd AI-FOR-BHARAT-THEME11
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
```

**3. Replace each `make ...` command with the Python equivalent:**

| Instead of      | Run                                                                                                                                                |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `make demo-venkateshulu` | `python -m kartavya.cli.run tests/fixtures/venkateshulu_real_pdf_wp13296_2022/original.pdf --dry-run --today 2026-05-07`                    |
| `make demo-positive`     | `python -m kartavya.cli.run tests/fixtures/synthetic_disposed_with_directions/judgment.pdf --dry-run --demo-positive --today 2026-03-15` |
| `make dev`               | `uvicorn kartavya.main:app --reload --host 0.0.0.0 --port 8000`                                                                          |
| `make test`              | `pytest`                                                                                                                                  |

**Tips:**
- Using **PowerShell**? Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then activate with `.\.venv\Scripts\Activate.ps1`.
- Using **Git Bash** (installed with Git for Windows)? It supports the macOS/Linux commands directly — `source .venv/Scripts/activate` and so on.
- Want `make` to actually work on Windows? `winget install GnuWin32.Make` (or use Chocolatey / Scoop). Then everything in the main section above works as-is.

---

That's it. You don't need Docker, Postgres, Redis, or Ollama for the demo — the demo CLI uses stubbed LLM clients so everything runs offline.
