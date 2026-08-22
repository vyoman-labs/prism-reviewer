# Reddit Posts Strategy: Tailored Content for r/programming & r/DevOps

---

## POST 1: Targeted for `r/programming` & `r/coding`

### 📌 Post Title
**We built an open-source Multi-Agent AI Code Reviewer using LangGraph, Tree-Sitter AST, and LiteLLM**

### 📝 Post Body
```markdown
Hey r/programming!

Over the past few months, we've been working on **Prism Reviewer** ([GitHub link](https://github.com/vyoman-labs/prism-reviewer)), an open-source Python system that automates code reviews on GitHub PRs using a multi-agent council architecture.

### The Problem with Naive AI Code Reviewers
Most AI reviewers send a raw `git diff` to a single LLM prompt. In real-world engineering workflows, this breaks down:
- **Context Overload & Generic Advice**: A single prompt trying to evaluate security, architecture, performance, and formatting yields surface-level nitpicks.
- **Line Hallucinations**: LLMs frequently comment on lines outside the diff because they lose track of patch boundaries.
- **Token Inflation & Unmonitored Spending**: Re-analyzing full branch diffs on every commit push explodes API costs without token telemetry.

### How Prism Reviewer Works Under the Hood

```
                    ┌──────────────────────────────┐
                    │      Git Diff / PR Event     │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │ Tree-Sitter AST CodeLens Map │
                    └──────────────┬───────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
     ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
     │ 👮 Warden Node  │  │ 📐 Architect    │  │🔍 Inspector     │
     │ (Security/Secrets)││ (Design/Perf)   │  │ (Logic/Clean)   │
     └────────┬────────┘  └────────┬────────┘  └────────┬────────┘
              │                    │                    │
              └────────────────────┼────────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │🛡️ Dual-Safeguard Verifier   │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │ 📈 Pluggable Telemetry       │
                    │   (Langfuse / OpenTelemetry) │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │ 📊 GitHub PR Review Render   │
                    └──────────────────────────────┘
```

1. **Tree-Sitter AST CodeLens Parsing**: Before calling LLMs, we parse modified files into AST symbol maps (functions, classes, dependencies) across 8+ languages (Python, Java, TS, JS, Go, Rust, C, C++).
2. **LangGraph Parallel Agent Council**: Large diffs are sliced into region chunks and fanned out in parallel to three specialized agent personas:
   - **Warden**: Security vulnerabilities, exposed credentials, dependency risks.
   - **Architect**: Software architecture, performance bottlenecks, design pattern compliance.
   - **Inspector**: Clean code, readability, edge-case logic bugs.
3. **Dual-Safeguard Verifier**:
   - *Hallucination Guard*: Compiles a strict index of modified `(filename, line_number)` tuples. Any comment targeting an un-modified line is automatically discarded.
   - *Content-Hash Deduplication*: SHA256 signatures of findings prevent duplicate comments on commit pushes.
4. **Smart Hybrid Incremental Review**: On push updates (`synchronize`), it reviews only new commits (`previous_sha..HEAD`) while keeping full PR AST context, saving up to 90% in token costs.
5. **Pluggable Token & Cost Monitoring**: Built-in callbacks for Langfuse and OpenTelemetry track token usage, cost per agent, and latency automatically.
6. **LiteLLM Multi-Provider Abstraction**: Allows developers to switch between Gemini 2.5 Pro/Flash, OpenAI GPT-4o, Anthropic Claude 3.7 Sonnet, DeepSeek, or local Ollama models with a single configuration flag.

### Try It Out

You can install it locally via `pip install prism-reviewer` or run it as a GitHub Action:

```yaml
uses: vyoman-labs/prism-reviewer@v1
with:
  llm-api-key: ${{ secrets.LLM_API_KEY }}
  llm-model-name: 'gemini/gemini-2.5-pro' # flexible LiteLLM string!
```

Repo: https://github.com/vyoman-labs/prism-reviewer
Live Demo PR: https://github.com/aravinthan-n/savourly-recipes/pull/33

We’d love to hear your thoughts on multi-agent graph architecture for code reviews!
```

---

## POST 2: Targeted for `r/DevOps`, `r/github`, & `r/sysadmin`

### 📌 Post Title
**Automating GitHub PR Reviews with an Open-Source Multi-Agent Action (Pluggable Token Telemetry & 90% Cost Savings)**

### 📝 Post Body
```markdown
Hey r/DevOps!

If your engineering teams are struggling with slow PR review turnarounds or burnt-out senior devs, we built an open-source GitHub Action called **Prism Reviewer AI** ([GitHub Action Marketplace link](https://github.com/marketplace/actions/prism-reviewer-ai)).

### Why We Built It for DevOps Pipelines

Most AI PR reviewers cost a fortune to run in CI pipelines because they re-evaluate the whole codebase diff every time a developer pushes a new commit. 

Prism Reviewer solves this with **Smart Hybrid Incremental Review** and **Pluggable Token Telemetry**:
- **Initial PR**: Performs a full architectural audit (`base..HEAD`).
- **Commit Pushes**: Reviews *only* the incremental delta (`previous_sha..HEAD`), while passing prior `MAJOR`/`CRITICAL` comment threads and AST maps to the LLM.
- **Cost Reduction**: Reduces LLM API token consumption by up to **90%** on continuous PR updates!
- **Token & Cost Monitoring**: Built-in Langfuse & OpenTelemetry integration tracks exact token counts, LLM API costs, and latency metrics across workflow runs.

### 3-Minute Integration Guide

Add `.github/workflows/prism-reviewer.yml` to your repository:

```yaml
name: Prism Reviewer AI

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  review:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write

    steps:
      - name: Checkout Code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Run Prism Reviewer AI
        uses: vyoman-labs/prism-reviewer@v1
        with:
          llm-api-key: ${{ secrets.LLM_API_KEY }}
          llm-model-name: 'gemini/gemini-2.5-pro' # Works with OpenAI, Gemini, Anthropic, DeepSeek, Ollama!
          enable-monitoring: 'auto'               # Pluggable Langfuse & OTel monitoring
        env:
          LANGFUSE_PUBLIC_KEY: ${{ secrets.LANGFUSE_PUBLIC_KEY }}
          LANGFUSE_SECRET_KEY: ${{ secrets.LANGFUSE_SECRET_KEY }}
```

### Key Enterprise Features

- 🔒 **Zero Code Storage**: Operates entirely inside your GitHub Actions runner sandbox.
- 🔑 **Flexible Authentication**: Works via default `GITHUB_TOKEN`, Personal Access Tokens (PAT), or dedicated GitHub App installations.
- 🛡️ **Zero Hallucinations**: Includes a line-number verifier so the bot never posts comments on unmodified code lines.
- 📊 **Telemetry & Observability**: Native integration with Langfuse and OpenTelemetry for tracking token usage, costs, and review latency.

Check out the project on GitHub: https://github.com/vyoman-labs/prism-reviewer

Feedback and pull requests are very welcome!
```
