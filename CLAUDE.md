# CLAUDE.md

## Overview

Zero-clone CLI to configure NetBeans Ant projects (JUnit 5, classpath, build overrides).
Executed directly via `uv run <url>` without cloning the repository.

Entry point: `setup.py` — single-file PEP 723 script containing all business logic.
Tests: `tests/test_setup.py` — pytest with `tmp_path` fixtures and HTTP mocks.

## `setup.py` architecture

| Layer | Functions |
|---|---|
| Validation | `validate_netbeans_project`, `is_<feature>_configured` |
| File operations | `set_compile_on_save_false`, `add_file_references`, `modify_classpath`, `inject_build_xml`, `remove_*`, `revert_classpath` |
| Network | `fetch_jar_names`, `download_jars` |
| CLI | `main()` → `_<feature>_flow()` via `questionary` |

## CLI architecture

Navigation uses `questionary` for interactive menus. Every feature follows the same pattern — do not deviate from it when adding new options.

**Flow contract:** each `_<feature>_flow(console: Console) -> str` must:
1. Ask for the project path via `_ask_project_path()`
2. Call `is_<feature>_configured(project)` to show current status in a `Panel`
3. Offer contextual choices (install vs uninstall, generate vs remove)
4. Call the corresponding `run_*` / business-logic function
5. Return `"back"` or `"quit"` — never navigate directly

**After any action**, call `_nav_choice()` which offers Back / Quit to the user.

**Idempotency markers:**
- XML injection (`build.xml`): `MARKER_BEGIN` / `MARKER_END` HTML comment pair
- Plain-text files (`.gitignore`): `GITIGNORE_MARKER` as a `#` comment on the first line

**Adding a new feature checklist:**
1. Add `is_<feature>_configured(project)` — pure predicate, no side effects
2. Add `generate_<feature>` / `remove_<feature>` (or `run_install_*` / `run_uninstall_*`)
3. Add `_<feature>_flow(console)` following the contract above
4. Register in `main()` with a new numbered `questionary.Choice`
5. Write tests for all behaviours before implementing (TDD)

## Key design decisions

- **Relative paths**: JARs are placed in `<project>/lib/junit5/` — portable across machines without reconfiguration.
- **String-based XML editing**: `build.xml` is edited with markers (`cct-netbeans-setup:begin/end`), not `ElementTree`, to preserve comments and formatting.
- **Idempotency**: all install/uninstall operations are safe to run multiple times.
- **Single-file delivery**: everything lives in `setup.py` to enable `uv run <url>`. Tests import it via `sys.path` injection (see `tests/conftest.py`).

## Quality

Pre-commit is installed system-wide and configured in `.pre-commit-config.yaml`. The pipeline validates:
- `check-abbrev`, `check-comments`, `ruff check`, `ruff format`, `mypy`, `vulture`, `bandit`, `pylint`, `pytest`

Before writing any code, load the `/dev-quality` skill — it enforces all quality rules inline.
