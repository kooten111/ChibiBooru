---
description: How to run package install commands for ChibiBooru (uv or pip)
---

# Important: Always Use the Virtual Environment

ChibiBooru uses a Python virtual environment at `./venv/`.

## Installing packages

// turbo-all

1. Always activate the venv first, then install. Prefer **uv** (faster):
```bash
source ./venv/bin/activate && uv pip install <package>
```

2. Or with pip:
```bash
source ./venv/bin/activate && pip install <package>
```

3. For requirements.txt:
```bash
source ./venv/bin/activate && uv pip install -r requirements.txt
```

## Running Python commands

Always prefix with venv activation:
```bash
source ./venv/bin/activate && python <script.py>
```

## NEVER do this:
- `pip install <package>` or `uv pip install <package>` (without activating venv)
- Install packages globally
