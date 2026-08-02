# Repository Guidelines

## Project Structure & Module Organization

This is an asynchronous Python QQ-bot RPG. Entry points are `main.py` (FastAPI webhook) and `bot_main.py` (botpy WebSocket). Command parsing and routing live in `output_main.py`. Add player-facing systems under `Game_main/` using the `g{number}_{feature}.py` pattern; database access belongs in `sql/`, shared helpers in `Tool/`, and registration guards in `func/pd_func.py`. SQL snapshots are in `数据库源文件/`; tests are in `tests/`.

## Development and Test Commands

Create or activate the project virtual environment, then install dependencies:

```powershell
python -m pip install -r requirements.txt
python main.py
python -m unittest discover -s tests
```

Run `python -m py_compile Game_main/g10_shop.py` after small module changes. Use `bot_main.py` only when testing the QQ WebSocket entry point.

## Coding Style & Naming Conventions

Use UTF-8 Python files, four-space indentation, `snake_case` functions, and descriptive Chinese player copy. Keep handlers `async`, parameterize every SQL query with `%s`, and commit only after all related writes succeed. New protected commands must use `@pd_reg_func` or `@reg_xz_func` as appropriate and return `{"type": "markdown", "content": "..."}`. Register every command in both command lists and `content()` in `output_main.py`.

## Testing Guidelines

Name tests `test_*.py` and test classes `*Tests`. Cover parsers, catalog/config rules, failure paths, and transaction-sensitive behavior. Avoid relying on a real production database in unit tests; use small pure helpers or mocks. Run the full unittest discovery suite before submitting changes.

## Commit and Pull Request Guidelines

This checkout has no Git history, so use concise imperative Conventional Commit messages, for example `feat(shop): add lingshi convenience store`. Keep each commit focused. Pull requests should explain gameplay impact, list schema changes and commands added, link the issue when applicable, and include representative bot-response screenshots for menu or interaction changes.

After every completed task, stage only the files that belong to that task, create a focused commit, and push the current branch to its configured Git remote. Do not report a task as complete until the push succeeds. If committing or pushing is blocked, report the exact blocker instead of silently leaving completed work uncommitted or unpushed. Never include unrelated working-tree changes or secrets merely to satisfy this rule.

## Security & Configuration

Never commit real QQ credentials, database passwords, private keys, or production SQL dumps with sensitive player data. Move local secrets to environment-specific configuration before deployment.
