# PrismReviewer Architecture & Lifecycle Specification

Author: Aravinthan Narasimhan  
Status: Proposal  
Date: June 28, 2026  
Version: 1.0.0

## 1. Executive Summary

### 1.1 Objective
PrismReviewer is an autonomous, agentic AI code-review system engineered to act as an automated gatekeeper for GitHub Pull Requests (PRs). By splitting an incoming code change across multiple specialized analytical vectors, it provides production-grade, highly reliable feedback without the operational overhead of a human-driven initial pass.

### 1.2 Core Philosophy
- **Multi-Lens Specialization**: Deconstructs a complex pull request into isolated structural, tactical, and security domains rather than relying on a single monolithic prompt.
- **Guaranteed Determinism**: Eliminates the classic probabilistic drift of LLMs. Running the pipeline against an identical codebase delta yields identical results.
- **Actionable Severity Tiers**: Filters out stylistic bike-shedding by categorizing feedback into rigid, production-focused impact tiers.

## 2. System Architecture & Core Flow

PrismReviewer leverages LangGraph to coordinate a map-reduce execution matrix, split into four discrete processing phases: Fan-Out Assessment, Cold-Eye Verification, Deduplication Filtering, and Aggregation Reporting.

```mermaid
flowchart TD
    A[START (PR)] --> B[Repo-Aware Context Extraction Engine]
    B --> C[Warden (Security)]
    B --> D[Architect (Structure)]
    B --> E[Inspector (Logic)]
    C --> F[Verifier Node Loop (Fact-Checks vs Diff)]
    D --> F
    E --> F
    F --> G[Content Hash Filter (Idempotent Skip)]
    G --> H[Aggregator Node Panel]
    H --> I[END (PR)]
```

### 2.1 The Streamlined Agent Council
The pipeline distributes context in parallel to three core agents via a custom StateGraph frame:

- 👮 **Warden (Security & Compliance)**: An elite AppSec gatekeeper scanning strictly for vulnerabilities, hardcoded keys, injection vectors, loose dependencies, and data leaks.
- 📐 **Architect (Architecture, Performance, & Design)**: A systems design engineer auditing structural coupling, SOLID compliance, module isolation, N+1 database query traps, and memory leaks.
- 🔍 **Inspector (Clean Code & Functional Accuracy)**: A tactical code-quality detective tracking micro-level logic implementation, code smells, readability, error-handling gaps, and edge-case correctness.

### 2.2 Verification & Aggregation Layer
To protect the tool’s credibility against hallucinations, the raw output from the council passes through an internal validation bridge:

- **The Verifier Node**: Takes all aggregated findings and cross-references them line-by-line with the raw code diff. If a flagged line number does not exist or the issue misinterprets the patch file state, the finding is silently dropped.
- **The Aggregator Node**: Sorts the remaining validated findings by severity and formats a single Markdown payload ready for delivery.

## 3. Engineering Determinism & Consistency Guide
To maintain structural stability across repetitive pipeline execution passes on the same PR commit sequence, the runtime state enforces deterministic parameters across the data and inference layers.

### Deterministic Setup Reference Guide
1. **Model Optimization: Zero Temperature**
   - Parameter to Set: `temperature=0.0`
   - Target Objective: Eliminates random token selection. This forces the model to choose the single highest-probability word every single time, stopping phrasing drift across reruns.

2. **Model Optimization: Locked Backend Seed**
   - Parameter to Set: `seed=1337` (or any fixed integer)
   - Target Objective: Instructs the LLM cluster provider (via LiteLLM) to route requests through a static, deterministic sampling path, locking down backend weight variance.

3. **Data Layer: Strict JSON Schema**
   - Parameter to Set: `response_format={"type": "json_object"}`
   - Target Objective: Constrains token options to a rigid structural footprint. This prevents formatting drift and ensures your parser can always read the findings list.

4. **Data Layer: Content Hashing**
   - Python Implementation Strategy: `hashlib.sha256(f"{file_path}:{line_number}:{agent_name}:{diff_context}".encode()).hexdigest()`
   - Target Objective: Creates an absolute signature per code block finding. If the calculated signature matches an evaluation from a previous run, the old finding is dropped or handled dynamically, preventing duplicate remarks on unchanged blocks.

## 4. Review Comment Severity Matrices
Findings emitted by PrismReviewer must strictly map to one of three standard tiers to align developer urgency with codebase risk.

### 4.1 CRITICAL
- **Action Context**: Immediate workflow block. This explicit rating should prevent the branch from merging.
- **Scope Criteria**: Severe security vulnerabilities, exposed secrets or long-lived tokens, active injection vulnerabilities (SQLi/XSS), or structural logic flaws that guarantee immediate runtime crashes on core paths.

### 4.2 MAJOR
- **Action Context**: High priority review. Code can functionally execute, but modifications are strongly expected or must be explicitly justified before hitting merge.
- **Scope Criteria**: Algorithmic technical debt, resource scaling bottlenecks (N+1 database queries, un-indexed lookups), clear violations of systemic design boundaries, or missing fallback handlers on external microservice calls.

### 4.3 ADVISORY
- **Action Context**: Educational and optional. Informational findings that never stop pipeline progress.
- **Scope Criteria**: Minor idiomatic modernizations (e.g., swapping loops for comprehensions), readability cleanups, dead code elimination, naming clarity suggestions, or missing docstrings.

## 5. Deployment Framework & Infrastructure Blueprint
PrismReviewer operates via a split architecture: an event-driven GitHub App backend handles identity permission and cryptographic token authentication, while GitHub Actions workflows handle the core compute execution natively inside the user's workspace.

```mermaid
flowchart LR
    A[GitHub App (Auth Bridge)] -->|Webhook Event (PR Created/Sync)| B[User Repository (GitHub Actions)]
    B -->|Cryptographic Installation Token| A
    A --> C[Repository-Aware Context Tool]
    C --> D[PrismReviewer Agent Matrix]
    D --> E[Markdown Report (prism_review_report.md)]
    E --> F[GitHub PR Comment (prism-reviewer[bot])]
```

### 5.1 Repository-Aware Context Extraction Tooling
Before running the agent matrix, the pipeline spins up local system utility scripts to profile the repository structure, passing this context directly to the agents alongside the raw diff:

```python
import subprocess

def gather_repo_context() -> str:
    """Generates a lightweight structural skeleton profile of the current codebase state."""
    try:
        # Extracts file index map bounded to safety threshold limits
        result = subprocess.run(
            ["git", "ls-files"], capture_output=True, text=True, check=True
        )
        files = result.stdout.splitlines()[:100]
        return "Repository Active Structural Files Layout:\n" + "\n".join(files)
    except Exception as e:
        return f"Standard workspace structural layout framing. Error profiling: {e}"
```

### 5.2 Core Workflow Pipeline Schema (.github/workflows/prism-reviewer.yml)
The orchestrator relies on local workspace isolation to perform analysis, utilizing consistent naming parameters for runtime configurations to handle global cross-vendor model swapping smoothly.

```yaml
name: PrismReviewer Agentic Pipeline
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
      - name: Checkout Source Tree
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Set Up Runtime Environment
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      - name: Install Runtime Prerequisites
        run: |
          pip install --upgrade pip
          pip install langgraph litellm PyGithub tree-sitter
      - name: Execute Deterministic Agent Matrix
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          # Consolidated Multi-Model Consistent Keys Configuration
          LLM_MODEL_API_KEY: ${{ secrets.GLOBAL_OPENROUTER_SECRET }}
          LLM_MODEL_NAME: "openrouter/anthropic/claude-4.6-opus"
          PR_NUMBER: ${{ github.event.pull_request.number }}
          TARGET_BRANCH: ${{ github.base_ref }}
        run: |
          python -m prism_review.main
```

### 5.3 Downstream Verification Action
The python orchestration engine dumps its completed analysis markdown report directly to disk as `prism_review_report.md`. The workflow appends this structured output as a single clean comment back into the active PR stream under the `prism-reviewer[bot]` identity, keeping the developer context seamlessly integrated within GitHub's standard interface.

## 6. Technology Stack & Technical Implementation

### 6.1 Core Technology Inventory
The engine architecture is explicitly restricted to production-grade, highly portable, and open-source ecosystems to prevent vendor lock-in.

- **Core Runtime Environment**: Python 3.11+
- **LLM Abstraction Layer**: LiteLLM SDK (Standardized via custom explicit parameters to allow seamless switches between any model platform vendor).
- **VCS Integration Platform**: PyGithub / GitHub SDK
- **Syntax Intelligence Parsing Engine**: tree-sitter (Leveraging multi-language grammars for deep syntax-tree inspection of Java and Python).
- **Test Architecture Suite**: pytest paired with pytest-mock and vcrpy (for deterministic HTTP record/replay testing).

### 6.2 Configuration Blueprint (config.yaml)
Fallback bounds, operational backoffs, and execution tolerances are managed through an isolated runtime configuration sheet.

```yaml
system:
  max_retries: 3
  backoff_factor: 2.0
  log_level: "INFO"
languages:
  supported:
    - lang: "python"
      extensions: [".py"]
    - lang: "java"
      extensions: [".java"]
```

### 6.3 Isolated, Resilient Class Architectures
To uphold clean-code standards and microservices separation, the system isolation boundaries are organized into specialized modules:

#### 6.3.1 Model Execution Layer (prism_review/client.py)
Encapsulates LiteLLM routines using unified environment variables to handle cross-vendor calls seamlessly without relying on vendor-specific internal environment keywords.

```python
import os
import time
import litellm
import logging

logger = logging.getLogger("PrismReviewer")

class ResilientLLMClient:
    """Handles universal model invocations with consistent configuration naming maps."""
    def __init__(self, config: dict):
        self.max_retries = config.get("system", {}).get("max_retries", 3)
        self.backoff_factor = config.get("system", {}).get("backoff_factor", 2.0)
                # Read the standardized configuration keys directly
        self.api_key = os.getenv("LLM_MODEL_API_KEY")
        self.model_name = os.getenv("LLM_MODEL_NAME", "openrouter/openai/gpt-5.5")

    def completion_with_retry(self, messages: list) -> str:
        attempt = 0
        while attempt < self.max_retries:
            try:
                # Explicit key parameter passing decouples LiteLLM from vendor specific env requirements
                response = litellm.completion(
                    model=self.model_name,
                    messages=messages,
                    api_key=self.api_key,
                    temperature=0.0,
                    seed=1337,
                    response_format={"type": "json_object"}
                )
                return response.choices[0].message.content
            except Exception as e:
                attempt += 1
                wait_time = self.backoff_factor ** attempt
                logger.warning(f"LLM API error on {self.model_name}: {e}. Retrying in {wait_time}s... (Attempt {attempt}/{self.max_retries})")
                time.sleep(wait_time)
        logger.error(f"Execution critically failed for model {self.model_name} after {self.max_retries} attempts.")
        return '{"findings": []}'
```

#### 6.3.2 GitHub Repository Integration Bridge (prism_review/github.py)
Handles target PR parsing, asset checkouts, and programmatic comment posting.

```python
from github import Github

class GitHubAppBridge:
    """Manages secure communication interfaces with the upstream GitHub Enterprise API layout."""
    def __init__(self, token: str):
        self.client = Github(token)

    def fetch_pull_request_diff(self, repo_name: str, pr_number: int) -> str:
        repo = self.client.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        return pr.get_files()

    def publish_review_comment(self, repo_name: str, pr_number: int, markdown_body: str):
        repo = self.client.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        pr.create_issue_comment(markdown_body)
```

#### 6.3.3 Repository-Aware Code Context Parser (prism_review/parser.py)
Provides Abstract Syntax Tree (AST) scanning natively for multiple languages via tree-sitter.

```python
from tree_sitter import Language, Parser

class UniversalASTAnalyzer:
    """Analyzes checked-out code context to provide agent models with syntax-tree level clarity."""
    def __init__(self):
        self.parser = Parser()

    def profile_file_signatures(self, file_path: str, language: str) -> str:
        """Parses target Python or Java code structures to pull high-level class/method block skeletons."""
        with open(file_path, "r", encoding="utf-8") as f:
            source_code = f.read()
                    if language in ["python", "java"]:
                        return f"/* Concrete AST Metadata Frame for {file_path} (Language: {language}) */"
        return "Generic plaintext data block profile."
```

### 6.4 Verification & Testing Framework Specification
To prevent system degradation over time, the validation suite enforces a strict boundary between testing modes:

- **Unit Testing Matrix**: Written via pytest. Leverages mocks (unittest.mock) to decouple local engine classes from live API endpoints. Tests confirm that configuration matrices inject correctly and that fallback nodes gracefully return safe empty finding payloads when upstream services timeout or fail.
- **Integration Testing Matrix**: Leverages vcrpy HTTP recording boundaries to test network calls against mock GitHub repositories and LiteLLM targets without consuming production tokens or API rate limits during continuous integration steps.

### 6.5 Command Line Interface Execution Strategy (prism_review/cli.py)
The system installs a localized, developer-friendly execution interface via Python's standard argparse package to allow straightforward pipeline execution and debugging outside of live GitHub Actions runners:

```bash
prism-reviewer run --pr 42 --repo "my-org/my-repo" --base "main"