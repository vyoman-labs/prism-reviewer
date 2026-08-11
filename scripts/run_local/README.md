# 🔌 Local PR Review Utility (`run_local.py`)

This directory contains `run_local.py`, a developer utility script designed to fetch Pull Request details (git diff, title, and description) from GitHub and run the Prism Reviewer AI multi-agent review flow entirely locally.

It is particularly useful for:
- Testing and debugging agent council behavior/prompts on real-world pull requests.
- Reviewing pull requests locally before they are approved or merged.
- Offloading review execution to a developer workstation instead of relying on CI resources.

---

## 🛠️ Prerequisites

Before running the script, make sure you complete the following setup steps:

### 1. Install the Package in Editable Mode
From the root of the repository, install `prism-reviewer` along with its development dependencies:
```bash
pip install -e ".[dev]"
```

### 2. Configure Environment Variables or `.env` File
The script requires access to GitHub (to fetch the PR) and your chosen LLM provider. You can supply these values using a `.env` file in your repository root or by setting environment variables in your terminal.

**Option A: Using a `.env` file (Recommended)**
Copy `.env.example` to `.env` and fill in your details:
```bash
cp .env.example .env
```
Edit `.env`:
```env
GITHUB_TOKEN=your_github_personal_access_token
LLM_PROVIDER_API_KEY=your_llm_provider_api_key
LLM_MODEL=gpt-4o
```

**Option B: Setting terminal environment variables**
```bash
# GitHub Access Token (PAT)
export GITHUB_TOKEN="your_github_personal_access_token"

# LLM Provider Configuration
export LLM_MODEL="gpt-4o"  # Or anthropic/claude-3-5-sonnet, gemini-1.5-pro, etc.
export LLM_PROVIDER_API_KEY="your_llm_provider_api_key"
```

> [!NOTE]
> You can also place these configurations in a `prism_reviewer.toml` configuration file in the project directory, as described in the root [README.md](../../README.md#7-configuration-guide).

---

## 💻 Usage

Run the script from the root of the repository:

```bash
python scripts/run_local/run_local.py --repo "owner/repository" --pr <PR_NUMBER> [options]
```

### Options

| Option | Type | Required | Description |
| --- | --- | --- | --- |
| `--repo` | String | **Yes** | Full repository name on GitHub (e.g., `"octocat/Hello-World"`). |
| `--pr` | Integer | **Yes** | The numeric ID of the Pull Request. |
| `--token` | String | No | GitHub Personal Access Token. Defaults to the `GITHUB_TOKEN` environment variable or `.env` file. |
| `--output` | String | No | Output file path for the Markdown report (defaults to `prism_review_report.md` in the current directory). |
| `--context` | String | No | Path to optional project context file (defaults to `.prism_reviewer/context.md`). |
| `--rules` | String | No | Path to optional custom review rules file (defaults to `.prism_reviewer/rules.md`). |

### Example Command

```bash
python scripts/run_local/run_local.py --repo "google/git-app-restrict" --pr 12 --output custom_report.md
```

This will:
1. Connect to GitHub and fetch the diff and metadata for PR #12 in `google/git-app-restrict`.
2. Construct the local review context (AST mapping, dependency scanning, etc.).
3. Run the Agent Council (Warden, Architect, and Inspector) in parallel.
4. Execute the verifier and aggregator nodes to deduplicate and compile the final report.
5. Save the report to `custom_report.md`.
