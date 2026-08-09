# GitHub App Setup & Integration Guide

To have code reviews posted by a dedicated bot identity (e.g. `Prism Reviewer AI[bot]`) instead of the default `github-actions[bot]`, you can register and install a custom GitHub App.

This document walks you through creating the GitHub App, configuring its permissions, subscribing to repository events, and integrating it with your GitHub Actions workflow.

---

## 1. Creating the GitHub App

1. Navigate to your GitHub Organization or personal profile settings:
   - **Organization**: `Settings` > `Developer settings` > `GitHub Apps` > `New GitHub App`.
   - **Personal**: `Settings` > `Developer settings` > `GitHub Apps` > `New GitHub App`.
2. Fill out the basic registration details:
   - **GitHub App name**: `Prism Reviewer AI` (or a custom name).
   - **Homepage URL**: Your repository URL or organization site.
   - **Webhook**: Set to **Inactive** (the bot runs entirely inside GitHub Actions compute, so we do not need GitHub to send webhook events to a custom server).

---

## 2. Setting Required Permissions

Your GitHub App requires specific permissions to fetch PR diffs, read files, and write review comments:

| Permission Category | Scope | Purpose |
| :--- | :--- | :--- |
| **Repository: Pull Requests** | `Read & write` | Required to fetch PR details and publish review comments. |
| **Repository: Contents** | `Read-only` | Required to checkout repository code and perform AST parsing. |
| **Repository: Metadata** | `Read-only` | Automatically granted; used to fetch repository information. |

---

## 3. Subscribing to Events

Under **Subscribe to events**, select:
- [x] **Pull request** (triggers when pull requests are opened, synchronized, or reopened).

---

## 4. Installation & Secrets Setup

### 4.1 Install the App
1. Once registered, click **Install App** in the left sidebar.
2. Install the app on the organization or specific repositories you want to review.

### 4.2 Save Credentials
1. **App ID**: Locate the App ID on the App settings general page. Save this value.
2. **Private Key**: Scroll down to the bottom of the page and click **Generate a private key**. A `.pem` file will be downloaded to your machine. Open this file and copy its entire contents (including `-----BEGIN RSA PRIVATE KEY-----` and `-----END RSA PRIVATE KEY-----`).

### 4.3 Configure Repository Secrets
In the repository where you want to run the reviews (or at the organization level), add the following secrets under **Settings > Secrets and variables > Actions**:

* `PRISM_REVIEWER_APP_ID`: The App ID of your GitHub App.
* `PRISM_REVIEWER_PRIVATE_KEY`: The entire contents of the private key `.pem` file.
* `LLM_PROVIDER_API_KEY`: The API key for your LLM Provider (e.g., OpenRouter, OpenAI, Gemini).

---

## 5. Workflow Integration Details

The workflow in `.github/workflows/prism-reviewer.yml` leverages `actions/create-github-app-token` to authenticate:

```yaml
- name: Generate GitHub App Token
  id: app-token
  uses: actions/create-github-app-token@v1
  with:
    app-id: ${{ secrets.PRISM_REVIEWER_APP_ID }}
    private-key: ${{ secrets.PRISM_REVIEWER_PRIVATE_KEY }}
```

This token is passed as `GITHUB_TOKEN` to `scripts/post_review.py`. If the secrets are missing (e.g., in forks or before setup), it automatically falls back to the default `secrets.GITHUB_TOKEN`, ensuring the workflow is resilient.
