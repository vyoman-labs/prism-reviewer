# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-08-10

### Added
- **Multi-Agent Council Architecture**: Orchestrated via LangGraph, running specialized review nodes concurrently (Warden for security, Architect for design/performance, and Inspector for code style/readability).
- **Dual-Safeguard Verification**:
  - *Hallucination Guard*: Prevents out-of-context review findings by validating reports against actual modified git diff files and line ranges.
  - *Idempotent Deduplication*: Uses content-hash signatures stored in `.prism_reviewer/signatures.json` to ignore previously reported findings across pushes.
- **AST CodeLens Engine**: Built on Tree-Sitter grammars for Python and Java, allowing structural symbol-boundary context mapping around modified code regions.
- **Large PR Partitioning**: Automatically partitions large code diffs into logical, line-count bounded regions (`max_region_lines`) to respect LLM context windows and maintain review accuracy.
- **Resilient LiteLLM Client**: Features automated exponential backoff retries, connection limits, and request throttling configs to prevent API rate limit exhaustion.
- **Configurable Cognitive Reasoning**: Allows specifying custom reasoning effort levels (`high`, `medium`, `low`) for individual agent council nodes.
- **Unified CLI and Local Run Script**: Features a CLI interface (`prism-review`) and a script (`scripts/run_local/run_local.py`) to execute full PR reviews locally using a GitHub Pull Request ID.
- **`.env` File Support**: Automatically loads local `.env` configuration files to supply `GITHUB_TOKEN`, `LLM_PROVIDER_API_KEY`, and `LLM_MODEL_OVERRIDE` for local runs.
- **GitHub Inline Review Comments**: Submits code findings directly onto GitHub PR file diff lines as inline code review comments alongside the aggregated review report.
- **Versioned Footer Notes**: Appends versioned attribution footers (`Prism Reviewer AI v<VERSION>`) to review summary reports and individual inline code comments.
- **Root README Context Integration**: Automatically loads root `README.md` into review prompt context, with configurable character-based truncation (`max_readme_chars`, defaulting to 10,000 chars) snapped to line boundaries.
- **GitHub Action & Marketplace Support**: Added composite `action.yml` metadata file and example workflow configuration (`docs/examples/prism-reviewer-external.yml`) enabling external repositories to integrate Prism Reviewer AI via GitHub Marketplace.


