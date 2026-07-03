# Repository Rules: prism-reviewer

This file outlines the guidelines, architectural patterns, and standards for agents contributing to the `prism-reviewer` repository.

## 1. Environment & Architecture
- **Language**: Python 3.13+ compatibility is required.
- **Dependencies**: Use Python 3.13+ built-in `tomllib` when reading configuration.
- **Modules Structure**:
  - `src/prism_reviewer/` containing the core logic.
  - `tests/` containing tests.
  - Entry point is managed through `cli.py` and package-level exports.

## 2. Coding Standards
- **Typing**: Use static type hints (`typing` module) for all function arguments, return values, and class properties.
- **Docstrings**: Provide clear, descriptive docstrings for all modules, classes, and public functions, indicating arguments, return types, and exceptions raised.
- **Imports**: Organize imports logically (standard library first, third-party libraries second, local imports third).
- **Asynchronous Code / Retries**: Follow the patterns established in `litellm_client.py` for retry logic, exponential backoff, and concurrency thresholds.

## 3. Configuration Management
- **Centralized Config**: Do not read environment variables directly using `os.environ` or `os.getenv` outside of `config.py`.
- **GlobalConfig**: Always use the `GlobalConfig` singleton from `prism_reviewer.config` to fetch project settings.
- **TOML Rules**: Update `prism_reviewer.toml` when introducing new configuration parameters. Use placeholders like `${VAR_NAME|-fallback}` for flexible environment overrides.
- **README Updates**: Always update `README.md` whenever the configuration options or their corresponding environment variable placeholders are added, removed, or changed.

## 4. Logging
- **Standardized Logging**: Do not use `print()` statements or initialize independent `logging` objects in core code.
- **Logger Module**: Import and use the shared logger from `prism_reviewer.logger` to ensure consistent log formats and levels across the utility.
- **Logger Naming**: When renaming modules or files, always check and update the logger names (e.g., `get_logger("prism_reviewer.<module_name>")`) to match the new module names.

## 5. Testing & Verification
- **Test Framework**: Use `pytest` for all unit and integration testing.
- **Coverage**: Every new module or feature must be accompanied by comprehensive tests in the `tests/` directory named with the `test_*.py` pattern.
- **Test Command**: Run `pytest` to verify the codebase after any modifications.

## 6. Static Analysis & Type Checking
- **Type Checker**: Use `pyright` (the engine behind VS Code Pylance) to perform static type analysis on the codebase.
- **Zero Warnings**: Code must contain zero typing errors or warnings when analyzed by pyright. Run `.venv\Scripts\pyright src` to verify correctness.

