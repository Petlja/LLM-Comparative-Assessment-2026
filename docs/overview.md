# LLM Comparative Assessment 2026 - Codebase Overview

> This document is the gateway to understanding the codebase. Start here before diving into the code.

## Purpose

This repository contains the test cases, generated assessment artifacts, survey
definition, responses, and results for the 2026 comparative assessment of LLM
responses to educational prompts. Reusable inference and comparison tooling lives in
the sibling `AI-Assistant-LLM-Compare` repository and is consumed here through the
`plct-llm-compare` editable dependency.

## Architecture

The project is a small Python package with three responsibilities specific to this
assessment round:

1. Validate the round's YAML test case definitions through `llmcmp check_cases`.
2. Build a SurveyJS survey from HTML responses and their matching JSON metadata
   through `llmcmp survey`.
3. Exercise a running Simple Survey instance as a participant and verify the stored
  response through its admin API with `llmcmp test_survey`.

The shared `plcmp` CLI prepares cases, runs model inference, and performs judge
comparisons. Those commands produce intermediate artifacts under `eval/output/`,
which the round-specific survey generator consumes. Generated output is ignored by
Git; assessment definitions and durable results should be committed in their
designated source locations.

## Key directories

| Path | Description |
|------|-------------|
| `src/llm_assessment_2026/` | Round-specific Python package and `llmcmp` CLI |
| `eval/` | Test case definitions and generated assessment output |
| `docs/` | Architecture notes, decisions, and deeper project documentation |

## Development conventions

- Use Python 3.13 and manage the environment with `uv`.
- Run project commands through `uv run` so they use the synchronized environment.
- Keep reusable assessment behavior in `AI-Assistant-LLM-Compare`; add code here only
  when it is specific to the 2026 round.
- Treat `eval/test-cases.yml` and committed survey or result files as source data.
  Do not commit generated files from `eval/output/`.
- Validate test case changes with
  `uv run llmcmp check_cases -c eval/test-cases.yml`.
- Run `uv run pytest` when tests are present or added.

## Further reading

- [README.md](../README.md) - setup and end-to-end assessment workflow
- [AGENTS.md](../AGENTS.md) - guidance for AI assistants working in this repository
