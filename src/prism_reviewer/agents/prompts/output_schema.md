---

## Required Output Format

Respond with **only** a valid JSON object. No markdown fences, no explanation
text, no preamble. The response must be parseable by `json.loads()` with no
pre-processing.

```json
{
  "findings": [
    {
      "file": "relative/path/to/file.py",
      "line": 42,
      "severity": "CRITICAL",
      "agent": "warden",
      "message": "Precise, single-sentence description of the issue and why it matters."
    }
  ]
}
```

### Field Rules

| Field      | Type    | Constraint                                              |
|------------|---------|---------------------------------------------------------|
| `file`     | string  | Relative path **exactly** as it appears in the diff header. |
| `line`     | integer | Line number that **exists** in the diff (added or context line). |
| `severity` | string  | Exactly one of: `CRITICAL`, `MAJOR`, `ADVISORY`.       |
| `agent`    | string  | Exactly one of: `warden`, `architect`, `inspector`.    |
| `message`  | string  | Single actionable sentence. No markdown inside the string. |

- If you find **no issues**, return `{"findings": []}`.
- Do **not** include findings for lines that are not in the diff.
- Do **not** include markdown formatting inside any field value.
