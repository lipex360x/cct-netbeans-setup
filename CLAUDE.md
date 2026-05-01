# CLAUDE.md

## Required reading before any task

Read `.docs/project.yaml` before starting any work. It contains the project purpose, architecture, design decisions, and planned features — it is the source of truth for context.

## Overview

Zero-clone CLI to configure NetBeans Ant projects (JUnit 5, classpath, build overrides).
Executed directly via `uv run <url>` without cloning the repository.

Entry point: `setup.py` — single-file PEP 723 script containing all business logic.
Tests: `tests/test_setup.py` — pytest with `tmp_path` fixtures and HTTP mocks.

## `setup.py` architecture

| Layer | Functions |
|---|---|
| Validation | `validate_netbeans_project`, `is_junit5_configured` |
| File operations | `set_compile_on_save_false`, `add_file_references`, `modify_classpath`, `inject_build_xml`, `remove_*`, `revert_classpath` |
| Network | `fetch_jar_names`, `download_jars` |
| CLI | interactive menu with `rich` — **not yet implemented** |

## Key design decisions

- **Relative paths**: JARs are placed in `<project>/lib/junit5/` — portable across machines without reconfiguration.
- **String-based XML editing**: `build.xml` is edited with markers (`cct-netbeans-setup:begin/end`), not `ElementTree`, to preserve comments and formatting.
- **Idempotency**: all install/uninstall operations are safe to run multiple times.
- **Single-file delivery**: everything lives in `setup.py` to enable `uv run <url>`. Tests import it via `sys.path` injection (see `tests/conftest.py`).

## Quality

Pre-commit configured in `.pre-commit-config.yaml`. The pipeline validates:
- `check-abbrev`, `check-comments`, `ruff check`, `ruff format --line-length 100`, `mypy`, `vulture`, `bandit`, `pylint`, `pytest`

To validate manually:
```bash
uvx --from git+https://github.com/lipex360x/dev-quality check-all .
```
