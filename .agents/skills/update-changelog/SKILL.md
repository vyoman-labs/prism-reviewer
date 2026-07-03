---
name: update-changelog
description: Create or update a local CHANGELOG.md version entry with concise, high-signal release notes.
---

# Update Changelog

Use this skill to create or update a version entry in `CHANGELOG.md`.

## Version & Date Handling

1. **Target Version**: Use the version provided by the user. If not specified or clear from context, ask the user.
2. **Release Date**: 
   - For new/pending releases, use `Unreleased` or the current ISO date (`YYYY-MM-DD`).
   - For existing/published releases, use their actual release date (lookup on PyPI if needed).

## Categories & Format

Use standard Keep a Changelog categories in this order (skip empty ones):
1. `### Added`
2. `### Changed`
3. `### Fixed`
4. `### Deprecated` / `### Removed` / `### Security` (only when relevant)

### Template

```markdown
## [<version>] - YYYY-MM-DD

### Added
- <new capability or feature>

### Changed
- <behavioral, configuration, or operational change>

### Fixed
- <correctness, reliability, or bug fix>
```

## Writing Rules

- **Concise**: Focus on 3–8 high-signal bullets explaining user-facing or operational impact.
- **High-level**: Avoid implementation logs, commits, internal refactoring details, or test-only changes.
- **Clean**: No secrets, raw payloads, diffs, or duplicate entries across categories.

## Workflow

1. Read `CHANGELOG.md`.
2. Inspect the git diff or commits for the version.
3. Draft concise release notes.
4. Add or update the version section in `CHANGELOG.md` (keep older versions unchanged).
