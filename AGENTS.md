# AGENTS.md - AI Agent Guidelines for LLM Comparative Assessment 2026

This file contains instructions that apply specifically to AI coding assistants.
Keep it minimal and use the human-facing guideline files as the primary source of
project knowledge.

## Project guideline files

The following files are collectively referred to as the **project guidelines**. Read
and interpret them together according to the scope of each file.

| File | Orientation | Guideline scope |
|------|-------------|-----------------|
| `README.md` | Human-facing | Project overview, setup, and assessment workflow |
| `docs/**/*.md` | Human-facing | Detailed documentation; `docs/overview.md` is the primary entry point |
| `AGENTS.md` | Agent-oriented | Minimal shared instructions specific to AI agents |
| `CLAUDE.md` | Agent-oriented | Claude-specific entry point to these shared instructions |

Use the human-facing guidelines for project context, architecture, conventions, and
workflows. Avoid duplicating that knowledge in agent-oriented files. When changing
code or durable data formats, consider whether the project guidelines must also
change, but update them only when existing guidance becomes inaccurate or important
long-lived knowledge is introduced.

## Workflow

1. Read the relevant code and project guidelines before making changes.
2. Keep reusable comparison tooling in the sibling `AI-Assistant-LLM-Compare`
   project; changes here should remain specific to the 2026 assessment round.
3. Make the smallest change that correctly addresses the requirement.
4. Add or update tests for changed behavior when appropriate.
5. Validate test cases with
   `uv run llmcmp check_cases -c eval/test-cases.yml` and run relevant tests.

Keep all test changes within the project's existing `pytest` setup and conventions.
Do not commit generated artifacts from `eval/output/`.
