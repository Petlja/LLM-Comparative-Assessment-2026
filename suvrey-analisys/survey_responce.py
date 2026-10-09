import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any, Callable

import yaml


def load_responses(path: str | Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as responses_file:
        return json.load(responses_file)


def limit_response_cases(
    responses: list[dict[str, Any]],
    survey_path: str | Path,
    n_cases: int,
) -> list[dict[str, Any]]:
    """Keep answers from the first n case pages per group, in survey order."""
    if n_cases < 0:
        raise ValueError("n_cases must be non-negative.")

    with open(survey_path, encoding="utf-8") as survey_file:
        survey = json.load(survey_file)

    cases_by_visibility: Counter[str] = Counter()
    included_questions: set[str] = set()
    for page in survey["pages"]:
        if not any(
            element.get("type") == "matrixdropdown"
            for element in page["elements"]
        ):
            continue
        visibility = page.get("visibleIf", "")
        cases_by_visibility[visibility] += 1
        if cases_by_visibility[visibility] <= n_cases:
            included_questions.update(element["name"] for element in page["elements"])

    return [
        {
            **response,
            "answers": {
                name: answer
                for name, answer in response["answers"].items()
                if name in included_questions
            },
        }
        for response in responses
    ]


def average_response_size_by_model(
    output_dir: str | Path,
) -> list[dict[str, str | int | float]]:
    sizes_by_model: dict[str, list[int]] = defaultdict(list)

    for response_path in Path(output_dir).glob("TC-*_*.txt"):
        model = response_path.stem.split("_", maxsplit=2)[2].replace("--", "/")
        sizes_by_model[model].append(response_path.stat().st_size)

    return [
        {
            "model": model,
            "response_count": len(sizes),
            "average_size_bytes": round(fmean(sizes), 2),
        }
        for model, sizes in sorted(
            sizes_by_model.items(),
            key=lambda item: (-fmean(item[1]), item[0]),
        )
    ]


def _load_ranking_questions(
    survey_path: str | Path,
) -> tuple[dict[str, tuple[str, ...]], dict[str, str]]:
    with open(survey_path, encoding="utf-8") as survey_file:
        survey = json.load(survey_file)

    choices_by_question = {}
    category_names = {}
    for page in survey["pages"]:
        for element in page["elements"]:
            if element.get("type") != "matrixdropdown":
                continue

            question_name = element["name"]
            choices_by_question[question_name] = tuple(
                choice["value"] for choice in element["columns"][0]["choices"]
            )
            for row in element["rows"]:
                category_names[row["value"]] = row["text"]

    return choices_by_question, category_names


def _load_cases(survey_path: str | Path) -> tuple[dict[str, int], dict[str, str]]:
    """Return criteria count per case and the case of every question, keyed by ranking matrix name."""
    with open(survey_path, encoding="utf-8") as survey_file:
        survey = json.load(survey_file)

    criteria_by_case = {}
    case_by_question = {}
    for page in survey["pages"]:
        matrix = next(
            element for element in page["elements"] if element.get("type") == "matrixdropdown"
        )
        criteria_by_case[matrix["name"]] = len(matrix["rows"])
        for element in page["elements"]:
            case_by_question[element["name"]] = matrix["name"]

    return criteria_by_case, case_by_question


def _count_complete_rankings(answer: dict[str, dict[str, str]]) -> int:
    return sum(
        1
        for selection in answer.values()
        if selection.get("best") and selection.get("worst")
        and selection["best"] != selection["worst"]
    )


def summarize_participants(
    responses: list[dict[str, Any]],
    participants: list[dict[str, Any]],
    survey_path: str | Path,
) -> list[dict[str, Any]]:
    criteria_by_case, case_by_question = _load_cases(survey_path)
    group_by_token = {
        participant["token"]: (participant.get("variables") or {}).get("group")
        for participant in participants
    }
    summaries = []
    for response in responses:
        answers = response["answers"]
        touched_cases = {
            case_by_question[name]
            for name, answer in answers.items()
            if answer and name in case_by_question
        }
        complete_rankings_by_case = {
            case: _count_complete_rankings(answers.get(case, {}))
            for case in touched_cases
        }
        completed_cases = sum(
            count == criteria_by_case[case]
            for case, count in complete_rankings_by_case.items()
        )
        summaries.append({
            "participant": response["label"],
            "group": group_by_token.get(response["token"]),
            "status": response["status"],
            "last_page": response["last_page"],
            "saved_at": response["submitted_at"],
            "completed_cases": completed_cases,
            "incomplete_cases": len(touched_cases) - completed_cases,
            "complete_rankings": sum(complete_rankings_by_case.values()),
        })

    return summaries


def _fit_plackett_luce(
    rankings: list[tuple[str, str, str]],
    models: set[str],
    *,
    tolerance: float = 1e-10,
    max_iterations: int = 10_000,
) -> dict[str, float]:
    scores = {model: 1.0 / len(models) for model in models}
    selections = Counter(
        model
        for best, middle, _ in rankings
        for model in (best, middle)
    )

    for _ in range(max_iterations):
        exposure = dict.fromkeys(models, 0.0)
        for best, middle, worst in rankings:
            first_choice = 1 / (scores[best] + scores[middle] + scores[worst])
            second_choice = 1 / (scores[middle] + scores[worst])

            exposure[best] += first_choice
            exposure[middle] += first_choice + second_choice
            exposure[worst] += first_choice + second_choice

        new_scores = {
            model: selections[model] / exposure[model]
            for model in models
        }
        score_total = sum(new_scores.values())
        if score_total == 0:
            raise ValueError("Plackett-Luce scores cannot be estimated from these rankings.")
        new_scores = {
            model: score / score_total
            for model, score in new_scores.items()
        }

        if max(abs(new_scores[model] - scores[model]) for model in models) < tolerance:
            return new_scores
        scores = new_scores

    return scores


Triplet = tuple[str, str, str]
RankingRows = list[dict[str, str | int | float]]


def extract_triplets_by_category(
    responses: list[dict[str, Any]],
    survey_path: str | Path,
    *,
    skip_incomplete: bool = False,
) -> dict[str, list[Triplet]]:
    """Return (best, middle, worst) triplets per category name, in survey order."""
    choices_by_question, category_names = _load_ranking_questions(survey_path)
    triplets_by_category: dict[str, list[Triplet]] = defaultdict(list)

    for response in responses:
        for question_name, answer in response["answers"].items():
            if question_name not in choices_by_question:
                continue

            choices = choices_by_question[question_name]
            for category_id, selection in answer.items():
                best = selection.get("best")
                worst = selection.get("worst")
                middle = [model for model in choices if model not in {best, worst}]
                if best not in choices or worst not in choices or len(middle) != 1:
                    if skip_incomplete:
                        continue
                    raise ValueError(f"Invalid ranking in {question_name}, {category_id}.")
                triplets_by_category[category_id].append((best, middle[0], worst))

    return {
        category_name: triplets_by_category[category_id]
        for category_id, category_name in category_names.items()
        if triplets_by_category[category_id]
    }


def extract_triplets_by_case_type(
    responses: list[dict[str, Any]],
    survey_path: str | Path,
    cases_path: str | Path,
    *,
    skip_incomplete: bool = False,
) -> dict[str, dict[str, list[Triplet]]]:
    """Split rankings using case flags; missing inclusive flags mean general."""
    with open(cases_path, encoding="utf-8") as cases_file:
        cases = yaml.safe_load(cases_file)
    inclusive_by_case = {case["case_key"]: case.get("inclusive", False) for case in cases}
    choices_by_question, _ = _load_ranking_questions(survey_path)
    questions_by_type: dict[str, set[str]] = {"inclusive": set(), "general": set()}
    for question in choices_by_question:
        case_key = question.split("__", maxsplit=1)[0]
        if case_key not in inclusive_by_case:
            raise ValueError(f"No case definition for ranking question {question!r}.")
        case_type = "inclusive" if inclusive_by_case[case_key] else "general"
        questions_by_type[case_type].add(question)

    triplets_by_type = {
        case_type: extract_triplets_by_category(
            [
                {
                    **response,
                    "answers": {
                        question: answer
                        for question, answer in response["answers"].items()
                        if question in questions
                    },
                }
                for response in responses
            ],
            survey_path,
            skip_incomplete=skip_incomplete,
        )
        for case_type, questions in questions_by_type.items()
    }
    triplets_by_type["total"] = extract_triplets_by_category(
        responses, survey_path, skip_incomplete=skip_incomplete,
    )
    return triplets_by_type


def _ranking_rows(scores: dict[str, float], counts: Counter[str]) -> RankingRows:
    ordered_models = sorted(scores, key=lambda model: (-scores[model], model))
    return [
        {
            "rank": rank,
            "model": model,
            "score": scores[model],
            "answer_count": counts[model],
        }
        for rank, model in enumerate(ordered_models, start=1)
    ]


def rank_borda(triplets: list[Triplet]) -> RankingRows:
    """Rank models by mean Borda points per appearance: best=5, middle=3, worst=1."""
    totals: Counter[str] = Counter()
    counts: Counter[str] = Counter()
    for best, middle, worst in triplets:
        totals.update({best: 5, middle: 3, worst: 1})
        counts.update((best, middle, worst))

    return _ranking_rows(
        {model: total / counts[model] for model, total in totals.items()},
        counts,
    )


def rank_plackett_luce(triplets: list[Triplet]) -> RankingRows:
    counts = Counter(model for triplet in triplets for model in triplet)
    if not counts:
        return []
    scores = _fit_plackett_luce(triplets, set(counts))
    return _ranking_rows(
        {model: round(score, 6) for model, score in scores.items()},
        counts,
    )


def rank_by_category(
    triplets_by_category: dict[str, list[Triplet]],
    rank: Callable[[list[Triplet]], RankingRows],
) -> dict[str, RankingRows]:
    return {
        category: rank(triplets)
        for category, triplets in triplets_by_category.items()
    }


def rank_overall(
    triplets_by_category: dict[str, list[Triplet]],
    rank: Callable[[list[Triplet]], RankingRows],
) -> RankingRows:
    """Rank models on the triplets pooled across all categories."""
    return rank([
        triplet
        for triplets in triplets_by_category.values()
        for triplet in triplets
    ])


def rank_llms_by_category_borda(
    responses: list[dict[str, Any]],
    survey_path: str | Path,
    *,
    skip_incomplete: bool = False,
) -> dict[str, RankingRows]:
    return rank_by_category(
        extract_triplets_by_category(responses, survey_path, skip_incomplete=skip_incomplete),
        rank_borda,
    )


def rank_llms_by_category_pl(
    responses: list[dict[str, Any]],
    survey_path: str | Path,
    *,
    skip_incomplete: bool = False,
) -> dict[str, RankingRows]:
    return rank_by_category(
        extract_triplets_by_category(responses, survey_path, skip_incomplete=skip_incomplete),
        rank_plackett_luce,
    )