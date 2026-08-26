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


def rank_llms_by_category(
    responses: list[dict[str, Any]],
    survey_path: str | Path,
) -> dict[str, list[dict[str, str | int | float]]]:
    choices_by_question, category_names = _load_ranking_questions(survey_path)
    rankings_by_category: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    models = set()

    for response in responses:
        for question_name, answer in response["answers"].items():
            if question_name not in choices_by_question:
                continue

            choices = choices_by_question[question_name]
            models.update(choices)
            for category_id, selection in answer.items():
                best = selection["best"]
                worst = selection["worst"]
                middle = [model for model in choices if model not in {best, worst}]
                if best not in choices or worst not in choices or len(middle) != 1:
                    raise ValueError(f"Invalid ranking in {question_name}, {category_id}.")
                rankings_by_category[category_id].append((best, middle[0], worst))

    result = {}
    for category_id, category_name in category_names.items():
        rankings = rankings_by_category[category_id]
        scores = _fit_plackett_luce(rankings, models)
        ordered_models = sorted(models, key=lambda model: (-scores[model], model))
        result[category_name] = [
            {"rank": rank, "model": model, "score": round(scores[model], 6)}
            for rank, model in enumerate(ordered_models, start=1)
        ]

    return result