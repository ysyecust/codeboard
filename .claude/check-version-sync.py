#!/usr/bin/env python3
"""Pre-commit hook: ensure pyproject.toml and codeboard.py versions match."""
import tomllib, re, sys

with open("pyproject.toml", "rb") as f:
    toml_ver = tomllib.load(f)["project"]["version"]
with open("codeboard.py") as f:
    m = re.search(r'__version__\s*=\s*"([^"]+)"', f.read())

py_ver = m.group(1) if m else "NOT FOUND"
if toml_ver != py_ver:
    print(f"VERSION MISMATCH: pyproject.toml={toml_ver} codeboard.py={py_ver}")
    sys.exit(1)
