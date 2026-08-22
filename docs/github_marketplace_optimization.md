# GitHub Action Marketplace Visibility & Optimization Strategy

This guide outlines actionable steps to maximize the discoverability, search ranking, and user adoption of **Prism Reviewer AI** on the GitHub Action Marketplace.

---

## 1. Versioning & Floating Release Tag Strategy (`@v1` vs `v1.1.0`)

### Why Floating Tags Matter for Marketing
When developers discover an action on the GitHub Marketplace, they expect a simple, stable action reference such as:
```yaml
uses: vyoman-labs/prism-reviewer@v1
```

If marketing copy forces users to write `uses: vyoman-labs/prism-reviewer@v1.1.0`, any minor patch (`v1.1.1`) requires users to manually update their workflow files. Using a major floating tag (`@v1`) eliminates adoption friction.

### Git Tag Release Workflow for `v1.1.0` Launch

When publishing the upcoming `v1.1.0` release:

1. **Tag the Semantic Release**:
   ```bash
   git tag -a v1.1.0 -m "Release v1.1.0: Multi-Agent Council, AST CodeLens Map & Smart Hybrid Incremental Review"
   git push origin v1.1.0
   ```

2. **Update the Floating Major Tag (`v1`)**:
   ```bash
   git tag -fa v1 -m "Update v1 major tag to point to v1.1.0"
   git push origin v1 --force
   ```

3. **GitHub Marketplace Publication**:
   - Go to GitHub Repository &rarr; **Releases** &rarr; **Draft a new release**.
   - Select tag `v1.1.0`.
   - Check the box **"Publish this Action to the GitHub Marketplace"**.

---

## 2. Action Metadata Optimization (`action.yml`)

GitHub Marketplace indexes the fields defined in `action.yml` for keyword search.

### Recommended `action.yml` Configuration:

```yaml
name: 'Prism Reviewer AI'
description: 'Resilient multi-agent AI code review for Pull Requests. Features Tree-Sitter AST parsing, zero-hallucination line verification, and 90% token savings.'
author: 'Vyoman Labs'

branding:
  icon: 'eye'      # Alternatives: 'shield', 'check-circle', 'cpu'
  color: 'purple'  # Options: 'purple', 'blue', 'green', 'black'
```

### Key Search Engine Keywords Included:
- `multi-agent`
- `ai code review`
- `pull request`
- `AST parsing`
- `zero-hallucination`
- `token savings`

---

## 3. GitHub Repository Topics (SEO Tags)

GitHub uses repository topic tags to surface projects in search results and topic hubs. Add the following topics under **Repository Settings &rarr; General &rarr; Topics**:

| Topic Tag | Target Search Intent |
|---|---|
| `github-action` | Developers browsing GitHub Actions |
| `ai-code-review` | Teams searching for AI review solutions |
| `code-reviewer` | PR reviewer searches |
| `multi-agent` | AI agent council & multi-agent systems |
| `langgraph` | LangGraph ecosystem showcases |
| `litellm` | Multi-LLM provider compatibility |
| `static-analysis` | Tree-Sitter AST static analysis |
| `devops` | CI/CD automation tools |
| `pr-reviewer` | Pull Request automation |
| `security-scanner` | Security & vulnerability auditing |

---

## 4. GitHub Marketplace Category Selection

When submitting the action on GitHub Marketplace, select:
- **Primary Category**: `Code review`
- **Secondary Category**: `Code quality`

---

## 5. README & Marketplace Listing Visuals

A high-converting Marketplace listing requires clear visual hierarchy:

1. **Marketplace Badge Header**:
   ```markdown
   [![GitHub Marketplace](https://img.shields.io/badge/Marketplace-Prism%20Reviewer%20AI-purple?style=for-the-badge&logo=github)](https://github.com/marketplace/actions/prism-reviewer-ai)
   [![Release](https://img.shields.io/github/v/release/vyoman-labs/prism-reviewer?style=for-the-badge&color=blue)](https://github.com/vyoman-labs/prism-reviewer/releases)
   [![License](https://img.shields.io/github/license/vyoman-labs/prism-reviewer?style=for-the-badge&color=green)](LICENSE)
   ```

2. **Hero Integration SVG Graphic**:
   Embed `docs/assets/integration_guide.svg` directly at the top of `README.md` and the Marketplace description page.

3. **Copy-Paste Workflow Snippet & Live Demo PR**:
   Provide a 5-line minimal workflow snippet and a link to a live working PR ([savourly-recipes PR #33](https://github.com/aravinthan-n/savourly-recipes/pull/33)) at the top of the listing page so developers can see real-time agent comments before installing.

---

## Checklist Before Publishing `v1.1.0` to Marketplace

- [ ] Updated `action.yml` description and branding.
- [ ] Created SVG integration graphic in `docs/assets/integration_guide.svg`.
- [ ] Added repository topic tags on GitHub repo page.
- [ ] Pushed semantic tag `v1.1.0` and updated floating tag `v1`.
- [ ] Checked "Publish this Action to the GitHub Marketplace" in GitHub release UI.
