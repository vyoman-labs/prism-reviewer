# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0]

### Added
- **LLM Prompt Caching Structure**: Reordered prompt context sections in `_build_user_turn` to place static repository-wide shared context (Repo Structure, Codelens AST/Search/Dep Data, README, Context, Rules) at the top prefix, enabling 50%–90% prompt cache hit rates across parallel reviewer nodes and region evaluations.
- **Expanded Codelens Search Cap**: Increased cross-reference search file cap from 5 to 25 files (`touched_files[:25]`), configurable via `max_search_files` under `[codelens]` in `prism_reviewer.toml` and environment variable `MAX_SEARCH_FILES`.
- **Granular Prompt & Response Token Logging**: Added detailed token breakdown logging before and after LLM execution, recording AST Symbol Map, Code Search Hits, Dependency Scan, individual prompt categories (input tokens), and raw response completion (output & total tokens) separately.
- **Automatic GitHub API PR Details Resolution**: Added automatic resolution of Pull Request title, description, and ID from GitHub API (`GitHubAppBridge.fetch_pull_request_details`) in `prism-review` CLI execution.
- **Cross-Organization GitHub App Token Support**: Added `app-id`, `private-key`, and `owner` inputs to `action.yml` and explicitly set `owner: ${{ github.repository_owner }}` in workflow definitions to ensure GitHub App installation tokens are properly generated for repositories outside the GitHub App's parent organization.
- **Explicit GitHub Token Logging**: Added log messages in CLI, `scripts/post_review.py`, and GitHub Action workflows specifying whether a GitHub App token (`GITHUB_APP_TOKEN`) or default repository token (`GITHUB_TOKEN`) is being used for API operations.

### Changed
- **Standardized Model Environment Variable Naming**: Replaced `LLM_MODEL_OVERRIDE` and `LLM_MODEL_NAME` with `LLM_MODEL` as the single global LLM model environment variable. Standardized per-agent model overrides to `<AGENT>_MODEL_OVERRIDE` (`WARDEN_MODEL_OVERRIDE`, `ARCHITECT_MODEL_OVERRIDE`, `INSPECTOR_MODEL_OVERRIDE`, `VERIFIER_MODEL_OVERRIDE`), removing legacy fallback aliases.

### Fixed
- **Multi-Layered Inline Comment Deduplication**: Added intra-run signature and location deduplication in `verifier_node` to drop duplicate findings generated within the same run. Enhanced `GitHubAppBridge.publish_review_comment` with in-memory comment payload deduplication and automatic query of existing PR review comments (`pr.get_review_comments()`) to skip comments already published on GitHub PRs.
- **GitHub App Token Warning Logging & Fallback**: Updated `Resolve GitHub Token` step in `action.yml` to log an explicit `::warning::` workflow notice when `app-id` or `private-key` credentials are provided but `actions/create-github-app-token` fails to generate an installation token, while safely preserving fallback to `GITHUB_TOKEN` without failing the workflow step.
- **Unbuffered Rate Limit & Retry Warning Logging**: Added explicit `sys.stdout.flush()` call before sleeping on LLM rate-limit retries in `ResilientLLMClient` and set `PYTHONUNBUFFERED="1"` in `action.yml` step execution. This delivers instant, real-time warning logs to GitHub Actions console windows without breaking the non-interleaved log buffering of normal agent node outputs.
- **Buffered Parallel Node Execution & Sequential Logging**: Restored full parallel agent fan-out across council nodes (`warden`, `architect`, `inspector`) and diff regions while buffering output blocks into state. Log blocks are flushed sequentially in rank order at the verifier node, combining maximum parallel execution speed with 100% linear, non-interleaved log outputs.
- **Inline PR Review Comments Resolution & Persistence**: Added path normalization (`normalize_file_path`) across diff parsing, line validation, and GitHub API review posting to prevent relative file path mismatches.
- **Findings Artifact Persistence**: Added automatic generation of `reports/prism_review_findings.json` artifact in `cli.py` and `run_local.py`, and updated `scripts/post_review.py` to read and forward findings to `publish_review_comment`.
- **Resilient GitHub Inline Comment Fallback**: Enhanced `GitHubAppBridge.publish_review_comment` to attempt individual inline comment posting when batch review creation fails, preserving valid inline comments rather than dropping them.
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


