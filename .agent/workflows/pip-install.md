---
description: How to run pip install commands for ChibiBooru
---

# Important: Always Use the Virtual Environment

ChibiBooru uses a Python virtual environment at `./venv/`.

## Installing packages

// turbo-all

1. Always activate the venv first, then install:
```bash
source ./venv/bin/activate && pip install <package>
```

2. Or for requirements.txt:
```bash
source ./venv/bin/activate && pip install -r requirements.txt
```

## Running Python commands

Always prefix with venv activation:
```bash
source ./venv/bin/activate && python <script.py>
```

## NEVER do this:
- `pip install <package>` (without activating venv)
- Install packages globally
