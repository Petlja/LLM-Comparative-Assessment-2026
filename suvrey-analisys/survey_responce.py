import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any


def load_responses(path: str | Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as responses_file:
        return json.load(responses_file)


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


def rank_llms_by_category_borda(
    responses: list[dict[str, Any]],
    survey_path: str | Path,
    *,
    skip_incomplete: bool = False,
) -> dict[str, list[dict[str, str | int | float]]]:
    """Rank models by mean Borda points per valid appearance: best=5, middle=3, worst=1."""
    choices_by_question, category_names = _load_ranking_questions(survey_path)
    scores_by_category: dict[str, Counter[str]] = defaultdict(Counter)
    counts_by_category: dict[str, Counter[str]] = defaultdict(Counter)

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
                scores = scores_by_category[category_id]
                scores[best] += 5
                scores[middle[0]] += 3
                scores[worst] += 1
                counts_by_category[category_id].update((best, middle[0], worst))

    result = {}
    for category_id, category_name in category_names.items():
        scores = {
            model: total / counts_by_category[category_id][model]
            for model, total in scores_by_category[category_id].items()
        }
        if not scores:
            continue
        ordered_models = sorted(scores, key=lambda model: (-scores[model], model))
        result[category_name] = [
            {"rank": rank, "model": model, "score": scores[model]}
            for rank, model in enumerate(ordered_models, start=1)
        ]

    return result


def rank_llms_by_category_pl(
    responses: list[dict[str, Any]],
    survey_path: str | Path,
    *,
    skip_incomplete: bool = False,
) -> dict[str, list[dict[str, str | int | float]]]:
    choices_by_question, category_names = _load_ranking_questions(survey_path)
    rankings_by_category: dict[str, list[tuple[str, str, str]]] = defaultdict(list)

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
                rankings_by_category[category_id].append((best, middle[0], worst))

    result = {}
    for category_id, category_name in category_names.items():
        rankings = rankings_by_category[category_id]
        if not rankings:
            continue
        # Partial answers can leave a model unranked in some categories.
        models = {model for ranking in rankings for model in ranking}
        scores = _fit_plackett_luce(rankings, models)
        ordered_models = sorted(models, key=lambda model: (-scores[model], model))
        result[category_name] = [
            {"rank": rank, "model": model, "score": round(scores[model], 6)}
            for rank, model in enumerate(ordered_models, start=1)
        ]

    return result