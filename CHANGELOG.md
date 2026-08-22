# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Marketing Collateral & Integration Visual SVG**: Added production-ready marketing launch package (`docs/marketing/MEDIUM_ARTICLE.md`, `docs/marketing/HACKER_NEWS_SUBMISSION.md`, `docs/marketing/REDDIT_POSTS.md`), GitHub Marketplace optimization guide (`docs/github_marketplace_optimization.md`), and an SVG integration diagram (`docs/assets/integration_guide.svg`) showcasing 3-step setup, floating `@v1` release action tagging, pluggable token telemetry, and authentic real-time PR review comments.
- **Final PR Total Token Telemetry Log**: Added automatic PR-level token consumption tracking (`total_prompt_tokens`, `total_completion_tokens`, `total_tokens`, and `request_count`) in `TokenUsageManager`. Emits a structured log summary (`📊 Final PR Token Telemetry Summary — Input Tokens: ..., Output Tokens: ..., Total Tokens: ...`) before flushing telemetry callbacks.
- **Prior PR Comments & Discussion Context**: Added automatic fetching of prior PR review comments and discussion history (`GitHubAppBridge.fetch_pull_request_comments`) during PR updates. Injects conversation context into prompt memory so LLM agents (Warden, Architect, Inspector) can verify whether past findings were resolved in the latest diff and avoid re-flagging agreed decisions.
- **Conditional Severity Filtering for PR Comments**: Added `include_previous_comments` (default `true`) and `max_previous_comments` (default `30`) under `[github]` in `prism_reviewer.toml` (`PRISM_INCLUDE_PREVIOUS_COMMENTS`, `PRISM_MAX_PREVIOUS_COMMENTS`). When total PR comments exceed `max_previous_comments`, severity filtering automatically prioritizes `CRITICAL` and `MAJOR` comments over low-priority `ADVISORY` comments.
- **Vyoman Labs Developer Attribution & Summary Header Branding**: Updated PR summary report headers to `# 🌌 Vyoman Labs | 🌈 Prism Reviewer AI Code Review Report` and added **Vyoman Labs** developer attribution across package metadata (`pyproject.toml`, `action.yml`) and documentation.
- **Conditional Telemetry Package Installation in GitHub Action**: Added a dedicated `Install Telemetry Dependencies (Langfuse / OpenTelemetry)` step in `action.yml` that conditionally installs telemetry packages based on action inputs (`enable-monitoring`) or environment variables (`LANGFUSE_*`, `OTEL_*`, `PRISM_MONITORING_*`), while skipping installation when monitoring is disabled.
- **Package Extras for Telemetry**: Added `langfuse`, `otel`, and `monitoring` optional dependency extras in `pyproject.toml`.

### Changed
- **Consolidated Telemetry Callback Configuration**: Standardized LiteLLM telemetry callback configuration on `PRISM_MONITORING_LITELLM_CALLBACKS` environment variable in `action.yml` and documentation, removing the redundant `litellm-callbacks` action input.

### Fixed
- **PyProject PEP 621 Dependencies Structure**: Moved `dependencies` list out of `[project.urls]` table to top-level `[project]` key in `pyproject.toml`, fixing wheel build and package installation failures (`configuration error: project.urls.dependencies must be string`).

## [1.1.0] - 2026-08-21


### Added
- **Expanded AST & Structural File Parsing**: Added AST and structural parsing support in `UniversalASTAnalyzer` for YAML (`.yml`/`.yaml`), HTML (`.html`/`.htm`), JSON (`.json`), Bash (`.sh`/`.bash`), Gherkin (`.feature`), and extensionless files (`Dockerfile`, `Makefile`, shebang scripts) using tree-sitter grammars and regex section extractors.
- **Pluggable LLM Token Usage Monitoring & Observability Framework**: Added a native event-driven token monitoring system (`prism_reviewer.monitoring`) that records `prompt_tokens`, `completion_tokens`, `total_tokens`, wall-clock latency, and caller metadata across all LLM requests.
- **Native In-App Observers**: Added built-in observers including `ConsoleLoggerObserver` (emits structured logs via `prism_reviewer.logger`), `JSONLFileObserver` (thread-safe append-only audit logger writing to `.prism_reviewer/token_usage.jsonl`), and `CustomCallbackObserver`.
- **Langfuse & OpenTelemetry Integration**: Added support for LiteLLM callback hooks, allowing seamless zero-code integration with **Langfuse** (`litellm_callbacks = "langfuse"`) for LLM tracing & cost dashboards, and **OpenTelemetry** (`litellm_callbacks = "otel"`) for enterprise APM distributed tracing.
- **`[monitoring]` Configuration Block**: Added `[monitoring]` section in `prism_reviewer.toml` and companion environment variables (`PRISM_MONITORING_ENABLED`, `PRISM_MONITORING_OBSERVERS`, `PRISM_MONITORING_JSONL_PATH`, `PRISM_MONITORING_LITELLM_CALLBACKS`).
- **Incremental PR Diff Review Mode**: Introduced a smart incremental review mode (`diff_mode = "auto"`) that analyzes only the newly pushed commit range (`previous_sha..HEAD`) on PR updates, cutting LLM token usage and API costs by up to 90% while maintaining PR-wide architectural awareness via full CodeLens AST context.
- **`[git]` Configuration Block**: Added `[git]` config section in `prism_reviewer.toml` and companion `PRISM_DIFF_MODE` environment variable supporting `auto`, `full`, and `incremental` modes.
- **CLI Diff Parameters**: Added `--diff-mode` and `--compare-range` options to the `prism-review` CLI.
- **Persistent State Tracking**: Added `.prism_reviewer/state.json` persistence to track `last_reviewed_commit_sha` and deduplication signatures across runs.

### Fixed
- **Langfuse SDK Version Compatibility**: Updated observability setup instructions and workflow guidelines to explicitly specify `langfuse>=2.0.0,<3.0.0` for LiteLLM telemetry callback compatibility. Updated minimum `litellm` dependency bound to `>=1.40.0`.
- **Langfuse Host Environment Variable Guidance**: Updated `docs/observability_setup.md` to document the requirement for `LANGFUSE_HOST` over `LANGFUSE_BASE_URL` in Langfuse Python SDK v2, and added a troubleshooting guide covering regional host endpoints and secret access in PRs from forks.
- **Telemetry Metric Publication Logging & Queue Flush**: Added `ObservabilityStatusLogger` callback and `TokenUsageManager.flush_callbacks()` in `src/prism_reviewer/monitoring/manager.py` to emit real-time success (`INFO`) and failure (`ERROR`) logs for LiteLLM/Langfuse metric publishing, and explicitly flush telemetry queues before process completion.

## [1.0.0] - 2026-08-11


### Added
- **Configurable Test File Markers**: Added `[test_files]` configuration block (`extra_dirs`, `extra_prefixes`, `extra_suffixes`, `extra_exact`) in `prism_reviewer.toml` and companion environment variables (`TEST_FILE_EXTRA_DIRS`, `TEST_FILE_EXTRA_PREFIXES`, `TEST_FILE_EXTRA_SUFFIXES`, `TEST_FILE_EXTRA_EXACT`), allowing teams to easily register custom test directories, prefixes, suffixes, or filenames.
- **Enforced ADVISORY Severity for Test Files**: Added language-agnostic test file identification (`is_test_file`) across Python, JS/TS, Go, Java, Kotlin, C#, Ruby, Rust, C/C++, PHP, Swift, and shell scripts. Comments and findings on test files are now automatically normalized to `ADVISORY` severity across LLM parsing and pipeline verification.
- **LLM Prompt Caching Structure**: Reordered prompt context sections in `_build_user_turn` to place static repository-wide shared context (Repo Structure, Codelens AST/Search/Dep Data, README, Context, Rules) at the top prefix, enabling 50%–90% prompt cache hit rates across parallel reviewer nodes and region evaluations.
- **Expanded Codelens Search Cap**: Increased cross-reference search file cap from 5 to 25 files (`touched_files[:25]`), configurable via `max_search_files` under `[codelens]` in `prism_reviewer.toml` and environment variable `MAX_SEARCH_FILES`.
- **Granular Prompt & Response Token Logging**: Added detailed token breakdown logging before and after LLM execution, recording AST Symbol Map, Code Search Hits, Dependency Scan, individual prompt categories (input tokens), and raw response completion (output & total tokens) separately.
- **Automatic GitHub API PR Details Resolution**: Added automatic resolution of Pull Request title, description, and ID from GitHub API (`GitHubAppBridge.fetch_pull_request_details`) in `prism-review` CLI execution.
- **Cross-Organization GitHub App Token Support**: Added `app-id`, `private-key`, and `owner` inputs to `action.yml` and explicitly set `owner: ${{ github.repository_owner }}` in workflow definitions to ensure GitHub App installation tokens are properly generated for repositories outside the GitHub App's parent organization.
- **Explicit GitHub Token Logging**: Added log messages in CLI, `scripts/post_review.py`, and GitHub Action workflows specifying whether a GitHub App token (`GITHUB_APP_TOKEN`) or default repository token (`GITHUB_TOKEN`) is being used for API operations.
- **Sticky In-Place PR Summary Comments**: The Prism Reviewer summary comment is now edited in-place on every new commit push (default `summary_mode = "update"`), keeping exactly one summary comment at the top of the PR timeline instead of accumulating duplicate summaries across pushes. Configurable via `PRISM_SUMMARY_MODE` env var; set to `"append"` to restore legacy behaviour.
- **Resolved Findings Section**: When a reviewer marks an inline comment thread as "Resolved" on GitHub, the corresponding finding is moved to a collapsible **✅ Resolved findings** section in the next summary report update, making it easy to track what has been addressed.
- **`resolved_signatures` State Field**: Added an optional `resolved_signatures` field to `ReviewState` to carry resolution status through the review pipeline to the aggregator.
- **`PRISM_SUMMARY_MODE` Configuration**: New `[github] summary_mode` config key (default `"update"`) and companion `PRISM_SUMMARY_MODE` environment variable documented in `README.md` and `prism_reviewer.toml`.

### Changed
- **Standardized Model Environment Variable Naming**: Replaced `LLM_MODEL_OVERRIDE` and `LLM_MODEL_NAME` with `LLM_MODEL` as the single global LLM model environment variable. Standardized per-agent model overrides to `<AGENT>_MODEL_OVERRIDE` (`WARDEN_MODEL_OVERRIDE`, `ARCHITECT_MODEL_OVERRIDE`, `INSPECTOR_MODEL_OVERRIDE`, `VERIFIER_MODEL_OVERRIDE`), removing legacy fallback aliases.
- **Inline Review Body Decoupled from Summary**: The review body submitted to `pr.create_review()` for inline code comments is now a brief acknowledgement string rather than the full summary report, preventing the full report from appearing multiple times in the PR timeline (once per inline batch).
- **`_render_markdown` no longer short-circuits on empty findings**: The Markdown renderer now always outputs all sections (including the ✅ Resolved block) in a consistent order for predictable in-place update diffing.
- **Hidden `<!-- prism-reviewer-summary -->` marker**: Every generated summary report now begins with an invisible HTML comment marker used to locate and update the sticky comment via `pr.get_issue_comments()`.

### Fixed
- **Markdown Table Cell Sanitization & Column Layout**: Added `_sanitize_table_cell` and `_format_file_cell` in `aggregator.py` to strip internal newlines (`\n`, `\r`), HTML break tags (`<br>`), escape pipe characters (`|`), and insert `<wbr>` (Word Break Opportunity) tags after `/` path separators. Also added explicit column alignment specifiers (`| :--- | :--- | :---: | :--- |`), ensuring table rows stay on single physical lines and long file paths wrap at directory boundaries so the **Message** column receives maximum horizontal width.
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


