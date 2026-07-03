# update-changelog Skill

A project-local skill to create or update `CHANGELOG.md` version entries.

## When to use
- Creating a new version entry.
- Updating or refining an existing version entry.
- Ensuring release notes are clean, concise, and structured.

## How to invoke
Ask the agent (Gemini, Claude, or Antigravity) to run the skill:
```text
Use the update-changelog skill for version 2.0.0.
```

## Expected Output Format

```markdown
## [<version>] - YYYY-MM-DD

### Added
- <new capability>

### Changed
- <behavior or configuration change>

### Fixed
- <bug fix or stability improvement>
```
