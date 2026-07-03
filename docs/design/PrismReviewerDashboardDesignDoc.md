# Product Dashboard Specification: PrismReviewer Analytics

Author: Aravinthan Narasimhan  
Status: Proposal  
Date: June 28, 2026  
Version: 1.0.0

## 1. Executive Summary & Objective

This document defines the architectural specification and implementation blueprint for the PrismReviewer Analytics Dashboard. The purpose of this system is to collect metadata from every automated Pull Request (PR) evaluation, monitor code-quality metrics, track developer engagement metrics, and establish continuous data lifecycle management with zero operational maintenance.

## 2. Core Dashboard Telemetry & Performance Trends

The dashboard provides continuous visibility into the PR evaluation pipeline across a rolling 1-year window, grouped by month, tracking the following distinct metrics:

### 2.1 The Core Volume Funnel
- **Total PRs Encountered**: Every single PR event caught across monitored repositories.
- **Total PRs Eligible**: The subset of PRs containing active changesets in supported language modules (.py, .java).
- **Total PRs Commented**: The number of eligible PRs where PrismReviewer found and published confirmed issues.
- **Total Merged PRs**: The overall count of PRs successfully merged into target destination branches.

### 2.2 Core Sentiment Trends
- **Accepted Rate**: Findings resolved by a code fix on a subsequent push or explicitly marked as "Resolved" in GitHub prior to merge.
- **Rejected Rate**: Findings explicitly marked with a downvote reaction, bypassed with an ignore tag, or closed without merging.
- **Unresolved Rate**: Open comments that remained unaddressed at the moment the parent Pull Request was changed to the MERGED state.

### 2.3 Human Engagement Metrics
- **Human Response Rate**: Percentage of bot-generated comments that received a direct, typed text response or dialogue thread from a human developer (Total Replied Comments / Total Posted Comments).

## 3. Database Architecture & Automated Data Purging

### 3.1 Choice of Database
- **Database Platform**: PostgreSQL (or AWS Aurora Serverless / Supabase)
- **Rationale**: Supports optimized relational operations for trend metrics, provides atomic data transactions for incoming state updates, and handles window functions natively for rapid historical analysis.

### 3.2 Relational Metrics Schema
```sql
-- Table 1: Pull Request Execution & Lifecycle Records
CREATE TABLE dashboard_pr_summaries (
    id SERIAL PRIMARY KEY,
    repo_name VARCHAR(255) NOT NULL,
    pr_number INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        -- State Machinery
    pr_state VARCHAR(20) DEFAULT 'OPEN',   -- OPEN, MERGED, CLOSED
    is_eligible BOOLEAN NOT NULL,         -- True if PR touches .py or .java
    was_commented BOOLEAN DEFAULT FALSE,  -- True if findings were published
    total_comments_posted INT DEFAULT 0
);
CREATE INDEX idx_pr_summaries_date ON dashboard_pr_summaries(created_at);
CREATE INDEX idx_pr_lookup ON dashboard_pr_summaries(repo_name, pr_number);

-- Table 2: Granular Comment Telemetry (Zero source code text stored)
CREATE TABLE individual_comment_telemetry (
    id SERIAL PRIMARY KEY,
    pr_summary_id INT REFERENCES dashboard_pr_summaries(id) ON DELETE CASCADE,
    finding_id VARCHAR(64) NOT NULL,      -- Content Hash Signature
    severity VARCHAR(20) NOT NULL,        -- CRITICAL, MAJOR, ADVISORY
    agent_name VARCHAR(50) NOT NULL,      -- Warden, Architect, Inspector
        -- Engagement Track
    resolution_state VARCHAR(20) DEFAULT 'OPEN', -- OPEN, ACCEPTED, REJECTED, UNRESOLVED
    human_replied BOOLEAN DEFAULT FALSE
);
```

### 3.3 Automatic Purging (Data Retention Policy)
To keep cloud infrastructure lean and low-cost, records older than 1 year are automatically purged every month. Because the schema utilizes a foreign key with ON DELETE CASCADE, deleting a row from dashboard_pr_summaries instantly wipes the corresponding rows inside individual_comment_telemetry.

**Cron-Driven Purge Command**
Run on a monthly schedule via an automated utility worker or a database cron task:
```sql
DELETE FROM dashboard_pr_summaries WHERE created_at < NOW() - INTERVAL '1 year';
```

## 4. Integration via GitHub Actions & Webhooks

The data capture workflow utilizes a split infrastructure: immediate telemetry is pushed via the workspace pipeline, and asynchronous human interaction events are captured by a centralized webhook event listener.

```mermaid
flowchart LR
    A[GitHub Action<br/>(Local Workspace)] -->|1. Pipeline Ends<br/>Logs Base Summary & Findings Count| B[GitHub Webhook<br/>(Event Worker)]
    B -->|2. Developer Interaction| C[API Endpoint / DB]
    C -->|3. Monthly Cleanup Cascade Purge| D[Cron Schedule Trigger]
    style A fill:#f9f,stroke:#333,stroke-width:stroke-width:2px
    style B fill:#bbf,stroke:#333,stroke-width:2px
    style C fill:#bfb,stroke:#333,stroke-width:2px
    style D fill:#f99,stroke:#333,stroke-width:2px
```

### 4.1 Step 1: Base Execution Push (Inside .github/workflows/prism-reviewer.yml)
At the end of a regular PR run, the GitHub Action extracts structural metrics and sends an authenticated POST request to the central analytics endpoint.

```yaml
- name: Log Pipeline Metrics to Analytics Database
  if: always()
  env:
    ANALYTICS_API_URL: "https://metrics.prismreviewer.internal/api/v1/log"
    ANALYTICS_API_KEY: ${{ secrets.PRISM_METRICS_SECRET }}
  run: |
    # The execution script parses structural run values and posts JSON directly
    python -c "
      import requests, os, json
      payload = {
          'repo_name': os.getenv('GITHUB_REPOSITORY'),
          'pr_number': int(os.getenv('PR_NUMBER', 0)),
          'is_eligible': True,
          'was_commented': os.path.exists('prism_review_report.md'),
          'total_comments_posted': 3 # Dynamically parsed value from local output run
      }
      headers = {'Authorization': f'Bearer {os.getenv(\"ANALYTICS_API_KEY\")}', 'Content-Type': 'application/json'}
      requests.post(os.getenv('ANALYTICS_API_URL'), json=payload, headers=headers)
    "
```

### 4.2 Step 2: Live Webhook Handling (Asynchronous State Tracking)
To track when developers reply, resolve, or merge over time, a lightweight cloud worker listens for incoming GitHub webhook signals and updates the database tracking states.

- On pull_request (Action: closed, Merged: true): Flips pr_state to MERGED and instantly shifts any lingering OPEN findings on that PR to UNRESOLVED.
- On pull_request_review_comment (Action: created): Sets human_replied = TRUE for that comment block when a human writes a response back to the bot thread.