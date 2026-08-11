# GitHub App & Integration Setup Guide

This guide details how to integrate **Prism Reviewer** as an automated gatekeeper on GitHub Pull Requests using a GitHub App or Personal Access Token (PAT) combined with GitHub Actions.

---

## 1. Registering a GitHub App

To run Prism Reviewer as a bot user on pull requests, you should register a GitHub App:

1. Navigate to your organization or personal settings: **Settings** > **Developer settings** > **GitHub Apps** > **New GitHub App**.
2. Fill out the application details:
   - **GitHub App name**: e.g., `Prism Reviewer AI`
   - **Homepage URL**: URL of your project repository.
   - **Active Webhook**: (Optional) Check this if you want to stream telemetry to the PrismReviewer Dashboard. Provide your webhook endpoint URL.
3. Scroll to the **Permissions** section and configure the following access rights:
   - **Repository permissions**:
     - **Pull requests**: `Read and write` (required to read PR diffs and publish review reports as issue comments).
     - **Contents**: `Read-only` (required for AST scanning and checking out files).
     - **Metadata**: `Read-only` (mandatory default).
4. In the **Subscribe to events** section (if active webhooks are checked):
   - Select **Pull request** (triggered on open, sync, etc.).
   - Select **Pull request review comment** (to track developer replies).
5. Click **Create GitHub App**.
6. Generate a **Private Key** and note down the **App ID** and **Client ID**. Install the app to your target repository.

---

## 2. Configuring Repository Secrets

To run the review agent in a GitHub Actions workflow, configure the following secrets under **Settings** > **Secrets and variables** > **Actions** > **Repository secrets**:

| Secret Name | Description |
| --- | --- |
| `LLM_PROVIDER_API_KEY` | API Key for LiteLLM (e.g., OpenRouter, OpenAI, Anthropic, Gemini). |
| `GITHUB_TOKEN` | Automatically supplied by GitHub Actions runner, or a custom Personal Access Token (PAT) / GitHub App installation token. |

---

## 3. GitHub Actions Workflow Configuration

Create a file named `.github/workflows/prism-reviewer.yml` in your repository:

```yaml
name: Prism Reviewer Code Review

on:
  pull_request:
    types: [opened, synchronize]

permissions:
  contents: read
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Codebase
        uses: actions/checkout@v4
        with:
          fetch-depth: 0 # Fetch all history for precise git diff calculations

      - name: Set Up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Install Prism Reviewer
        run: |
          pip install --upgrade pip
          pip install prism-reviewer

      - name: Run Deterministic Code Review
        env:
          # Credentials & Model Config
          LLM_PROVIDER_API_KEY: ${{ secrets.LLM_PROVIDER_API_KEY }}
          LLM_MODEL: "gemini/gemini-3.1-flash-lite" # or any model supported by LiteLLM
          
          # Optional environment overrides for prism_reviewer.toml
          AGENTS_MODE: "parallel"
          MAX_REGION_LINES: "500"
          WARDEN_REASONING_EFFORT: "high"
        run: |
          # 1. Run the core review graph on the PR's local unstaged/staged diff
          # This generates prism_review_report.md
          prism-review --pr --base origin/${{ github.base_ref }}

      - name: Publish Review Comment
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const path = 'prism_review_report.md';
            if (fs.existsSync(path)) {
              const body = fs.readFileSync(path, 'utf8');
              github.rest.issues.createComment({
                issue_number: context.issue.number,
                owner: context.repo.owner,
                repo: context.repo.repo,
                body: body
              });
            } else {
              core.warning('No Prism Reviewer report file found.');
            }
```

---

## 4. Alternate PAT Integration (No GitHub App)

If you do not wish to register a GitHub App, you can use a Personal Access Token (PAT) with `repo` scopes:

1. Generate a classic PAT or fine-grained token with access to `Pull Requests (Read & Write)` and `Contents (Read)`.
2. Add it as a secret named `PR_REVIEW_PAT` in your repository.
3. In your workflow YAML, replace the token in actions/github-script:
   ```yaml
   uses: actions/github-script@v7
   with:
     github-token: ${{ secrets.PR_REVIEW_PAT }}
     script: |
       // Code remains the same
   ```

---

## 5. Adding Project Context & Custom Review Rules (`.prism_reviewer/`)

To significantly improve the relevance, domain awareness, and quality of automated GitHub Actions PR reviews, commit custom context and rules files directly to your repository:

```
my-repository/
├── .prism_reviewer/
│   ├── context.md   # Project architecture, technology stack, data models & system boundaries
│   └── rules.md     # Team coding standards, security constraints & review rules
├── .github/workflows/prism-reviewer.yml
└── ...
```

- **`.prism_reviewer/context.md`**: Provides background context on your tech stack, invariants, design patterns, and microservices architecture so the Agent Council understands intentional design choices.
- **`.prism_reviewer/rules.md`**: Enforces strict security constraints, performance guidelines (e.g. N+1 queries), and style conventions.

The CLI command `prism-review --pr` automatically detects and loads both files from the root of your checked-out repository in CI/CD.
