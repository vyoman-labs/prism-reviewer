# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0]

### Added
- **Automatic GitHub API PR Details Resolution**: Added automatic resolution of Pull Request title, description, and ID from GitHub API (`GitHubAppBridge.fetch_pull_request_details`) in `prism-review` CLI execution.
- **Cross-Organization GitHub App Token Support**: Added `app-id`, `private-key`, and `owner` inputs to `action.yml` and explicitly set `owner: ${{ github.repository_owner }}` in workflow definitions to ensure GitHub App installation tokens are properly generated for repositories outside the GitHub App's parent organization.
- **Explicit GitHub Token Logging**: Added log messages in CLI, `scripts/post_review.py`, and GitHub Action workflows specifying whether a GitHub App token (`GITHUB_APP_TOKEN`) or default repository token (`GITHUB_TOKEN`) is being used for API operations.

### Fixed
- **`GITHUB_APP_TOKEN` Environment Alias & Resolution**: Updated `GlobalConfig._substitute_env`, `scripts/post_review.py`, and `cli._resolve_pr_api_details` to seamlessly resolve and fall back between `GITHUB_APP_TOKEN` and `GITHUB_TOKEN`.
- **Package Prompt Files Inclusion**: Updated `pyproject.toml` setuptools package data to include `agents/prompts/*.md` persona prompt Markdown files in built package wheels, resolving runtime `FileNotFoundError` when `prism-reviewer` is executed after pip installation.

## [0.1.1] - 2026-08-10

### Fixed
- **Built-in Configuration Fallback**: Fixed `GlobalConfig` to load package-bundled `prism_reviewer.toml` via `importlib.resources` (and fallback code defaults) when `prism_reviewer.toml` is missing from the target repository root, preventing `FileNotFoundError` during package execution.

## [0.1.0] - 2026-08-10

### Added
- **Multi-Agent Council Architecture**: Orchestrated via LangGraph, running specialized review nodes concurrently (Warden for security, Architect for design/performance, and Inspector for code style/readability).
- **Dual-Safeguard Verification**:
  - *Hallucination Guard*: Prevents out-of-context review findings by validating reports against actual modified git diff files and line ranges.
  - *Idempotent Deduplication*: Uses content-hash signatures stored in `.prism_reviewer/signatures.json` to ignore previously reported findings across pushes.
- **AST CodeLens Engine**: Built on Tree-Sitter grammars for Python and Java, allowing structural symbol-boundary context mapping around modified code regions.
- **Large PR Partitioning**: Automatically partitions large code diffs into logical, line-count bounded regions (`max_region_lines`) to respect LLM context windows and maintain review accuracy.
- **Resilient LiteLLM Client**: Features automated exponential backoff retries, connection limits, and request throttling configs to prevent API rate limit exhaustion.
- **Automated TestPyPI Publishing Workflow**: Added `.github/workflows/publish-testpypi.yml` to automatically build (`sdist` & `wheel`) and publish `prism-reviewer` to TestPyPI upon GitHub release publication using OIDC Trusted Publishing.
- **Configurable Cognitive Reasoning**: Allows specifying custom reasoning effort levels (`high`, `medium`, `low`) for individual agent council nodes.
- **Unified CLI and Local Run Script**: Features a CLI interface (`prism-review`) and a script (`scripts/run_local/run_local.py`) to execute full PR reviews locally using a GitHub Pull Request ID.
- **`.env` File Support**: Automatically loads local `.env` configuration files to supply `GITHUB_TOKEN`, `LLM_PROVIDER_API_KEY`, and `LLM_MODEL_OVERRIDE` for local runs.
- **GitHub Inline Review Comments**: Submits code findings directly onto GitHub PR file diff lines as inline code review comments alongside the aggregated review report.
- **Versioned Footer Notes**: Appends versioned attribution footers (`Prism Reviewer AI v<VERSION>`) to review summary reports and individual inline code comments.
- **Root README Context Integration**: Automatically loads root `README.md` into review prompt context, with configurable character-based truncation (`max_readme_chars`, defaulting to 10,000 chars) snapped to line boundaries.
- **GitHub Action & Marketplace Support**: Added composite `action.yml` metadata file and example workflow configuration (`docs/examples/prism-reviewer-external.yml`) enabling external repositories to integrate Prism Reviewer AI via GitHub Marketplace.

### Changed
- **Enhanced Rate Limit Resilience**: Updated default retry thresholds (`backoff_seconds = 30`, `retries = 5`) in `prism_reviewer.toml` to gracefully handle strict provider per-minute rate limits (RPM/TPM).


