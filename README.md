# LLM Comparative Assessment 2026

Working repository for the 2026 round of comparative assessment of LLM responses to
educational prompts.

It holds the material specific to this round — test case definitions, generated
answers, judge results, and the survey definition together with its collected
responses and analysis. Surveys are normally tailored to a particular assessment, so
the survey definition used here is maintained in this repository rather than in the
shared tooling.

The tooling that produces those artifacts is kept separately, in the
`AI-Assistant-LLM-Compare` repository, which provides the general-purpose `plcmp` CLI
(prepare → inference → judge compare → survey).

## How this repo relates to AI-Assistant-LLM-Compare

| Repository | Role |
| --- | --- |
| `AI-Assistant-LLM-Compare` | Reusable tooling: CLI, prompts, judging, survey generation |
| `LLM-Comparative-Assessment-2026` (this repo) | Test cases, survey definition, responses, and results for the 2026 assessment round |

The tooling is consumed as an editable dependency from the sibling checkout
`../AI-Assistant-LLM-Compare`. This repository is itself a Python package
(`src/llm_assessment_2026`) providing the `llmcmp` CLI for round-specific tasks that
do not belong in the shared tooling.

## Usage

1.  Synchronize the environment:
    ```bash
    uv sync
    ```

2.  Check the test case definitions:
    ```bash
    uv run llmcmp check_cases -c eval/test-cases.yml
    ```

3.  Prepare the test cases:
    ```bash
    uv run plcmp prepare -c eval/test-cases.yml
    ```

4.  Run inference for each model you want to compare, using commands like:

    ```bash
    plcmp inference -m gpt-4o
    plcmp inference -m gpt-4o --take 2
    plcmp inference -m Qwen/Qwen3-14B
    plcmp inference -m Qwen/Qwen3-32B
    ```

5.  Run judge comparison:


    ```bash
    uv run plcmp judge_compare -c eval/output/test-cases-sysmsg.json --model-a Qwen/Qwen3-14B --model-b Qwen/Qwen3-32B --judge-model gpt-5.2
    ```

6.  Generate the survey definition from the inference outputs:
    ```bash
    uv run llmcmp survey -o eval/output -s survey/survey.json
    ```

Generated artifacts under `eval/output` are not tracked; the survey definition under
`survey/` and the results kept for the record are committed.

## Status

Setup in progress. `eval/test-cases.yml` currently holds a placeholder case and is to
be replaced with the 2026 assessment material.
