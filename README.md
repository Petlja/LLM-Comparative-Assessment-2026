# LLM Comparative Assessment 2026

Working repository for the 2026 round of comparative assessment of LLM responses to
educational prompts.

It holds the material specific to this round — test case definitions, generated
answers, judge results, and the survey definition together with its collected
responses and analysis. Surveys are normally tailored to a particular assessment, so
the survey definition used here is maintained in this repository rather than in the
shared tooling.

Reusable tooling is kept separately in the `AI-Assistant-LLM-Compare` repository,
which provides the general-purpose `plcmp` CLI. This repository adds the `llmcmp`
CLI for validation, survey generation, and survey testing that are specific to the
2026 assessment design.

## How this repo relates to AI-Assistant-LLM-Compare

| Repository | Role |
| --- | --- |
| `AI-Assistant-LLM-Compare` | Reusable tooling: CLI, prompts, judging, survey generation |
| `LLM-Comparative-Assessment-2026` (this repo) | Test cases, survey definition, responses, and results for the 2026 assessment round |

The shared package is consumed as an editable dependency from the sibling checkout
`../AI-Assistant-LLM-Compare`. This repository is itself a Python package under
[`src/llm_assessment_2026`](src/llm_assessment_2026).

## Assessment tools

| Tool | Purpose | Owner |
| --- | --- | --- |
| `llmcmp check_cases` | Validate this round's YAML cases and reject duplicate case keys | This repository |
| `plcmp prepare` | Fetch lesson context and create cases with system messages | Shared tooling |
| `plcmp inference` | Generate model responses and their HTML/JSON metadata | Shared tooling |
| `plcmp judge_compare` | Compare two sets of responses with a third model as judge | Shared tooling |
| `plcmp human_eval` | Create a blind pairwise annotation file and side-by-side viewer | Shared tooling |
| `plcmp calibrate` | Compare the fine-tuning pointwise scorer with blind human preference | Shared tooling |
| `llmcmp survey` | Build this round's balanced three-model SurveyJS survey | This repository |
| `survey-preview` | Serve a generated survey in a temporary local Simple Survey instance | Simple Survey dependency |
| `llmcmp test_survey` | Submit synthetic responses through Chromium and verify the API result | This repository |
| `suvrey-analisys/*.py` | Calculate Plackett-Luce rankings and response-size summaries | This repository |

The shared CLI also has a generic `plcmp survey` command. Do not use it for the 2026
round: `llmcmp survey` implements this assessment's triplet assignment, presentation,
and six-criterion ranking design.

## Setup

Requirements:

- Python 3.13 (the package currently requires `>=3.13,<3.14`).
- [`uv`](https://docs.astral.sh/uv/) for dependency and environment management.
- A sibling checkout of `AI-Assistant-LLM-Compare` at
  `../AI-Assistant-LLM-Compare`.
- Access to the configured PLCT AI context and model providers.

Synchronize the project environment from this repository:

```bash
uv sync
```

Run every project command through `uv run`; no separate virtual-environment
activation is required.

### Configuration

| Environment variable | Used by | Default / requirement |
| --- | --- | --- |
| `OPENAI_API_KEY` | OpenAI inference, judging, and calibration | Required when the selected model/scorer uses OpenAI |
| `VLLM_URL` | Local or self-hosted model inference | `http://localhost:8000/v1` |
| `PLCT_AI_CTX_URL` | Lesson-context retrieval during `prepare` | Hosted PLCT AI context URL from the shared package |
| `AI_ASSISTANT_FINE_TUNING_PATH` | `plcmp calibrate` | Sibling `../AI-Assistant-Fine-Tuning` checkout |
| `SIMPLE_SURVEY_ADMIN_TOKEN` | `llmcmp test_survey` | Required; printed when `survey-preview` starts |

For example, in PowerShell, read secrets interactively so their values are not part
of the command history:

```powershell
$env:OPENAI_API_KEY = Read-Host "OpenAI API key"
$env:VLLM_URL = "http://localhost:8000/v1"
```

## End-to-end workflow

### 1. Validate the cases

[`eval/test-cases.yml`](eval/test-cases.yml) is the source definition for this
assessment round. Validate its schema and case-key uniqueness before generating
anything:

```bash
uv run llmcmp check_cases -c eval/test-cases.yml
```

The current file contains 55 cases across 7 courses.

### 2. Prepare lesson context

Enrich each case with the lesson-derived system message:

```bash
uv run plcmp prepare -c eval/test-cases.yml
```

This writes `eval/output/test-cases-sysmsg.json`. Re-run preparation when a case,
lesson source, or context-generation behavior changes.

### 3. Generate model responses

Run inference once for every model included in the comparison. Pass the prepared
file explicitly so the data dependency is visible:

```bash
uv run plcmp inference -c eval/output/test-cases-sysmsg.json -m Qwen/Qwen3-14B
uv run plcmp inference -c eval/output/test-cases-sysmsg.json -m Qwen3-14B-t7-sft
uv run plcmp inference -c eval/output/test-cases-sysmsg.json -m Qwen/Qwen3-32B
uv run plcmp inference -c eval/output/test-cases-sysmsg.json -m gpt-5.2
uv run plcmp inference -c eval/output/test-cases-sysmsg.json -m nvidia/Llama-3.3-70B-Instruct-FP8
```

For each case, model, and take, inference writes a response triplet beside the
prepared file:

- `<case>_<take>_<model>.txt`: raw model response.
- `<case>_<take>_<model>.html`: rendered response used by viewers and surveys.
- `<case>_<take>_<model>.json`: model, prompt, activity, take, and temperature metadata.

Model names are made filesystem-safe in these names. Use `--take N` and
`--temperature VALUE` to generate repeated samples. The survey uses take 1 only;
additional takes support pairwise stability, judge, and calibration experiments.

### 4. Run automated judge comparison (optional)

Compare two already-generated response sets with a third model:

```bash
uv run plcmp judge_compare -c eval/output/test-cases-sysmsg.json --model-a Qwen/Qwen3-14B --model-b Qwen/Qwen3-32B --judge-model gpt-5.2
```

The judge evaluates every pair twice with the A/B order swapped. A disagreement
after restoring canonical order is reported as `Inconsistent`, exposing position
bias instead of silently converting it to a tie. The command writes per-case HTML
and JSON, a text summary, and `judge_results_*.yml` under `eval/output/`.

Use `--model-a-take` and `--model-b-take` to compare repeated samples. Use
`--cases-b` when the two sides were prepared with different system messages and the
experiment is testing prompt/context changes rather than models.

### 5. Collect blind pairwise human preferences (optional)

For judge-versus-human alignment, generate a blind annotation set from the same two
response collections:

```bash
uv run plcmp human_eval -c eval/output/test-cases-sysmsg.json --model-a Qwen/Qwen3-14B --model-b Qwen/Qwen3-32B --model-a-take 1 --model-b-take 1
```

The command writes a pair-specific directory under `eval/output/human_eval/` with:

- `human_feedback.yml`: blind `A`, `B`, or `Tie` fields for annotators.
- `index.html`: self-contained side-by-side reading aid.
- `assignment.yml`: answer key mapping displayed sides to models; do not give it to annotators.

The side assignment is deterministic for a given `--seed`. Re-running preserves
existing annotations; `--force` intentionally discards them.

To check whether the pointwise scorer used by the fine-tuning pipeline agrees with
human preference on the same pair, run:

```bash
uv run plcmp calibrate -c eval/output/test-cases-sysmsg.json --model-a Qwen/Qwen3-14B --model-b Qwen/Qwen3-32B --model-a-take 1 --model-b-take 1 --scorer v1-baseline --tie-band 5
```

Calibration requires the sibling `AI-Assistant-Fine-Tuning` repository, or an
explicit `AI_ASSISTANT_FINE_TUNING_PATH`. It adds scorer results, improved answers,
and a disk cache under `eval/output/calibrate/`. It does not calculate agreement;
compare `eval_answers.yml` with the completed `human_feedback.yml` separately.

### 6. Generate the 2026 triplet survey

After all take-1 inference files are present, generate the SurveyJS definition:

```bash
uv run llmcmp survey --survey-file eval/output/survey.json
```

The generator requires the same complete model set for every case and at least
three models. It ignores inference takes greater than 1 and rejects incomplete or
duplicate response sets.

For $n$ models, it constructs all $\binom{n}{3}$ model triplets and creates one
participant group per triplet. The triplet is rotated across cases, and model column
positions are deterministically counterbalanced. Five models therefore produce 10
groups. Each visible page presents three responses and asks for the best and worst
model under six criteria; the remaining model receives the middle rank.

Configure every Simple Survey participant with a numeric `group` variable in the
generated range. For example:

```json
{
  "variables": {
    "group": 1
  }
}
```

SurveyJS uses this variable to show only that participant's assigned pages. Missing,
string-valued, or out-of-range groups do not select the intended page set.

### 7. Preview and test participant flows

Start a temporary Simple Survey instance in one terminal:

```bash
uv run survey-preview eval/output/survey.json
```

The default URL is `http://127.0.0.1:5000`; use `--port` if it is occupied. The
launcher prints participant information and an admin token.

Install Chromium once, then exercise the survey from another PowerShell terminal:

```powershell
uv run playwright install chromium
$env:SIMPLE_SURVEY_ADMIN_TOKEN = Read-Host "Simple Survey admin token"
uv run llmcmp test_survey --seed 42
```

By default, `test_survey` fetches participants from the API, ignores participants
without a `group`, and tests the first participant for every distinct group. Pass
`--group 1` to create, test, and delete one temporary participant instead. Useful
diagnostic options include `--headed`, `--base-url`, `--timeout`, `--output-file`,
and `--responses-output-file`.

The synthetic heuristic ranks the longest rendered response best and the shortest
worst, using the seed only for exact length ties and comments. Chromium submits the
answers, and the command then fetches `/api/responses` to verify each tested
participant. It writes:

- `eval/output/survey-test.json`: generated answers, response sizes, and verification metadata.
- `eval/output/survey-test-responces.json`: literal API response, including participant tokens.

The `responces` spelling is retained because it is the command's current default.
Treat that file as sensitive. Synthetic responses validate the delivery and analysis
pipeline only; never include them in human assessment results.

For real data collection, deploy or import the generated survey into the managed
Simple Survey instance, create participants across all generated groups, and retain
the participant-to-group assignment with the response export.

### 8. Analyze collected responses

Analysis lives in [`suvrey-analisys/`](suvrey-analisys/) as notebook-style Python
scripts using `# %%` cells. Open
[`basic-analisys.py`](suvrey-analisys/basic-analisys.py) in VS Code, select the
actual response export and survey definition in its setup cell, and run the cells
interactively. The supporting
[`survey_responce.py`](suvrey-analisys/survey_responce.py) module:

- reconstructs best-middle-worst rankings from each triplet response;
- fits per-criterion Plackett-Luce model scores; and
- summarizes average raw response size by model.

The default setup reads the synthetic files under `eval/output`; change it before
analyzing human responses. Keep synthetic and human exports separate.

## Artifact lifecycle

| Path | Contents | Handling |
| --- | --- | --- |
| `eval/test-cases.yml` | Round-specific source cases | Tracked source data |
| `eval/output/test-cases-sysmsg.json` | Prepared cases with lesson context | Generated; reproducible |
| `eval/output/*_<take>_<model>.{txt,html,json}` | Inference responses and metadata | Generated; input to later stages |
| `eval/output/judge_results_*.yml` and judge HTML/JSON | Automated comparison evidence | Generated experiment output |
| `eval/output/human_eval/` | Blind pairwise annotation packages | Generated; completed feedback may be retained as evidence |
| `eval/output/calibrate/` | Pointwise scorer calibration packages and cache | Generated experiment output |
| `eval/output/survey.json` | 2026 SurveyJS definition | Generated from take-1 inference |
| `eval/output/survey-test*.json` | Synthetic flow-test evidence | Generated; not human results |

The entire `eval/output/` directory is ignored by Git. Do not assume that an
assessment artifact there is part of the permanent record. Before archiving final
human results, place the selected export and enough provenance to reproduce it in a
deliberately tracked location agreed for the assessment; never commit participant
tokens or other secrets.

## Development checks

After changing cases or round-specific tooling, run:

```bash
uv run llmcmp check_cases -c eval/test-cases.yml
uv run pytest
```

Use CLI help for the authoritative option list:

```bash
uv run llmcmp --help
uv run llmcmp test_survey --help
uv run plcmp --help
uv run plcmp judge_compare --help
```

## Documentation

Deeper project documentation lives in [`docs/`](docs/). Start with the
[codebase overview](docs/overview.md). AI assistants should also read
[`AGENTS.md`](AGENTS.md).

## Status

`eval/test-cases.yml` contains 55 assessment cases across 7 courses, with generated
responses available for five models. The survey pipeline has been validated with
synthetic responses; human evaluation results are still pending.
