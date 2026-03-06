# Contributing

Thanks for your interest in CodeBoard! Here's how to get started.

## Setup

```bash
git clone https://github.com/shaoyiyang/codeboard.git
cd codeboard
pip install -e ".[dev]"
```

## Development

CodeBoard is a single-file CLI tool (`codeboard.py`). All logic lives in one file — keep it that way.

### Running

```bash
python codeboard.py           # run directly
# or after pip install -e .:
cb                            # use the alias
```

### Adding a Subcommand

1. Write a `cmd_xxx(args)` function
2. Register it in `main()`: add argparse subparser + entry in `commands` dict
3. Add any new user-facing strings to `_I18N` (both `en` and `zh` keys)

### i18n

All user-facing strings must go through the `T(key, **kw)` function. When adding new strings:

```python
# Add to _I18N dict — both languages required:
"en": { "my_key": "Hello {name}", },
"zh": { "my_key": "你好 {name}", },

# Use in code:
console.print(T("my_key", name="world"))
```

### Code Style

- Python 3.11+, no type stubs needed
- Use `rich` for all terminal output (Table, Panel, Text)
- Write operations (push/commit/stash) must ask for user confirmation
- Git commands should fail silently (return empty string), never crash the scan

## Testing

```bash
pytest
```

## Submitting Changes

1. Fork the repo
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Make your changes
4. Run tests: `pytest`
5. Commit with a descriptive message: `git commit -m "feat: add my feature"`
6. Push and open a PR

## Reporting Issues

Open an issue at [github.com/shaoyiyang/codeboard/issues](https://github.com/shaoyiyang/codeboard/issues). Include:

- What you expected vs what happened
- Your OS and Python version
- The command you ran

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
