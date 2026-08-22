# Hacker News (Show HN) Submission Strategy

---

## 📌 Submission Titles (Choose One)

1. **Show HN: Prism Reviewer – Multi-agent AI code review engine built with LangGraph & LiteLLM** *(Recommended)*
2. **Show HN: Prism Reviewer – Open-source AI code reviewer with Tree-Sitter AST parsing & zero-hallucination verification**
3. **Show HN: We built a multi-agent PR reviewer that cuts LLM token costs by 90% and monitors token usage**

---

## 📝 Submission Text Body

```markdown
Hi HN! We’re the team at Vyoman Labs, and we built Prism Reviewer (https://github.com/vyoman-labs/prism-reviewer)—an open-source multi-agent code review engine designed to automate PR reviews without the noise, line-number hallucinations, or massive LLM token bills common to single-prompt AI reviewers.

### Why We Built It

Most existing AI code review tools operate as a single prompt wrap over a raw `git diff`. In practice, we found three main issues:
1. Single prompts hallucinate comments on unchanged lines because LLMs struggle to map line numbers in large diffs accurately.
2. Re-sending full branch diffs on every commit push consumes tens of thousands of tokens per PR update.
3. Lack of token telemetry—teams have zero visibility into LLM token consumption, prompt costs, or per-agent latency breakdowns.

### Key Architectural Highlights

- **LangGraph Multi-Agent Council**: Diffs are sliced into regions and routed concurrently to three specialized agent nodes:
  - 👮 **Warden Node**: Security vulnerabilities, exposed secrets, loose dependencies.
  - 📐 **Architect Node**: System patterns, structural debt, performance traps.
  - 🔍 **Inspector Node**: Clean code, logic errors, Tree-Sitter AST symbol integrity.
- **Tree-Sitter AST CodeLens Parsing**: We use Tree-Sitter grammars across 8+ languages (Python, Java, TS, JS, Go, Rust, C, C++) to extract class/function range maps and dependency contexts before LLM evaluation.
- **Pluggable Token & Cost Monitoring (Langfuse / OpenTelemetry)**: Native callback integration with Langfuse and OTel. Pass `LANGFUSE_PUBLIC_KEY` or `OTEL_EXPORTER_OTLP_ENDPOINT` to record prompt tokens, completion tokens, latency, and costs per agent run automatically.
- **Dual-Safeguard Verifier**:
  - *Hallucination Index*: We build a precise mathematical lookup index of all modified `(filename, line_number)` tuples from the raw diff. Findings pointing outside modified ranges are dropped before posting.
  - *Content-Hash Signature Deduplication*: SHA256 content signatures of findings prevent repeating identical comments on push synchronization events.
- **Smart Hybrid Incremental Review**: On commit updates (`pull_request.synchronize`), the engine evaluates only `previous_sha..HEAD` diffs while maintaining full PR awareness by injecting past `MAJOR`/`CRITICAL` comment threads and AST symbol maps. This reduces token overhead by up to 90%.
- **LiteLLM Multi-Provider Engine**: Supports Gemini (e.g. Gemini 2.5 Pro / Flash), OpenAI (GPT-4o), Anthropic (Claude 3.7 Sonnet), DeepSeek, or local Ollama instances seamlessly.

### GitHub Action Setup

You can drop it into any GitHub repository via a simple workflow (`.github/workflows/prism.yml`):

```yaml
name: Prism Reviewer AI
on: [pull_request]

jobs:
  review:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: vyoman-labs/prism-reviewer@v1
        with:
          llm-api-key: ${{ secrets.LLM_API_KEY }}
          llm-model-name: 'gemini/gemini-2.5-pro' # Or openai/gpt-4o, anthropic/claude-3-7-sonnet
          enable-monitoring: 'auto'               # Pluggable Langfuse & OpenTelemetry monitoring
        env:
          LANGFUSE_PUBLIC_KEY: ${{ secrets.LANGFUSE_PUBLIC_KEY }}
          LANGFUSE_SECRET_KEY: ${{ secrets.LANGFUSE_SECRET_KEY }}
```

The codebase is fully open source under the Apache-2.0 license: https://github.com/vyoman-labs/prism-reviewer

You can also inspect a live example of Prism Reviewer's PR summary report and inline comments on an actual pull request here: https://github.com/aravinthan-n/savourly-recipes/pull/33

We would love to hear your thoughts, feedback, and suggestions on the architecture!
```

---

## 💬 Prepared First Comment / Founder Response Strategy

To seed high-quality discussion immediately after posting on Hacker News, post a top-level founder comment expanding on the technical decisions:

```markdown
Hey everyone, author here! A few extra technical details on how we handled state management, token telemetry, and deterministic evaluation in Prism Reviewer:

1. **Pluggable Telemetry via LiteLLM Callbacks**: We hooked LiteLLM callbacks directly into Langfuse and OpenTelemetry. This tracks token consumption, prompt/completion ratios, and API cost per agent (Warden vs Architect vs Inspector) without polluting core workflow logic.
2. **Deterministic LLM Output**: LLMs can be notoriously inconsistent across runs. We enforce zero-temperature routing, fixed-seed output generation, and strict JSON schemas to guarantee structured finding outputs across runs.
3. **Atomic Terminal Logging**: Running 3 parallel LLM agents on sliced diff regions creates race conditions in standard logging. We built a buffered `NodeLogger` that isolates per-agent execution logs in memory and flushes them as atomic log blocks upon node completion.

Happy to answer any questions about the LangGraph StateGraph design, Tree-Sitter parsing, token monitoring, or LiteLLM integration!
```

---

## 🛡️ Anticipated HN Questions & Suggested Answers

### Q1: "Why use LLMs for code review when static analysis tools (linter, SonarQube, Semgrep) already exist?"
> **Answer**: Prism Reviewer is built to complement static analysis, not replace traditional linters. While Semgrep and linters excel at deterministic rule-matching (e.g., regex patterns or defined AST signatures), LLMs excel at semantic understanding—auditing architectural flow, identifying logic flaws across functions, and checking if past review feedback was actually addressed. Prism Reviewer combines Tree-Sitter AST maps with LLMs so the AI has static structure awareness.

### Q2: "How do you track token usage and prevent unexpected cloud bills?"
> **Answer**: Prism Reviewer provides two features: 1) **Smart Incremental Mode** which cuts LLM token usage by up to 90% on PR updates by analyzing only new commit diffs (`previous_sha..HEAD`), and 2) **Pluggable Telemetry** via Langfuse and OpenTelemetry which logs exact token counts and costs to your observability dashboard.

### Q3: "How do you guarantee the AI doesn't post comments on unmodified lines?"
> **Answer**: We enforce a hard mathematical check in our `Verifier` node. Before any comment payload is sent to the GitHub API, we parse the raw git patch into a set of valid `(filepath, line_number)` tuples representing exact modified lines. If an agent emits a finding for line 150 but only lines 10-25 were modified, the verifier drops it instantly.
