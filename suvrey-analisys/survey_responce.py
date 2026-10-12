import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import fmean
from typing import Any, Callable, Literal, TypeVar
from urllib.request import Request, urlopen

import yaml

ANALYSIS_DIR = Path(__file__).resolve().parent
CONFIG_PATH = ANALYSIS_DIR / "live-analisys-config.json"
SURVEY_PATH = ANALYSIS_DIR.parent / "eval" / "output" / "survey.json"
CASES_PATH = ANALYSIS_DIR.parent / "eval" / "test-cases.yml"
RESPONSE_DIR = ANALYSIS_DIR.parent / "eval" / "final-assesment"


def load_survey_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load the shared survey API configuration."""
    with open(path or CONFIG_PATH, encoding="utf-8") as config_file:
        return json.load(config_file)


def load_responses(path: str | Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as responses_file:
        return json.load(responses_file)


def fetch_api(path: str, config: dict[str, Any] | None = None) -> Any:
    config = load_survey_config() if config is None else config
    request = Request(
        f"{config['base_url'].rstrip('/')}{path}",
        headers={"Authorization": f"Bearer {config['admin_token']}"},
    )
    with urlopen(request, timeout=30) as api_response:
        return json.load(api_response)


def prepare_live_responses(
    survey_path: str | Path | None = None,
    cases_path: str | Path | None = None,
    response_dir: str | Path | None = None,
    *,
    n_cases_min: int,
    n_cases_max: int,
    min_completed_cases: int,
    course_keys: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch live data, save a raw snapshot, and apply the analysis filters."""
    if min_completed_cases < 0:
        raise ValueError("min_completed_cases must be non-negative.")
    survey_path = SURVEY_PATH if survey_path is None else survey_path
    cases_path = CASES_PATH if cases_path is None else cases_path
    response_dir = RESPONSE_DIR if response_dir is None else response_dir

    raw_responses = fetch_api("/api/responses")
    response_dir = Path(response_dir)
    response_dir.mkdir(parents=True, exist_ok=True)
    response_path = response_dir / f"responce-{datetime.now():%y-%m-%d-%H-%M}.json"
    with response_path.open("w", encoding="utf-8") as response_file:
        json.dump(raw_responses, response_file, ensure_ascii=False, indent=2)

    responses = [
        response
        for response in raw_responses
        if re.match(r"^p\d{2}", str(response.get("label") or ""))
    ]
    if course_keys:
        with open(cases_path, encoding="utf-8") as cases_file:
            cases = yaml.safe_load(cases_file)
        course_by_case = {case["case_key"]: case["course_key"] for case in cases}
        available_course_keys = set(course_by_case.values())
        unknown_course_keys = set(course_keys) - available_course_keys
        if unknown_course_keys:
            raise ValueError(f"Unknown course keys: {sorted(unknown_course_keys)}")
        selected_case_keys = {
            case_key for case_key, course_key in course_by_case.items()
            if course_key in course_keys
        }
        responses = [
            {
                **response,
                "answers": {
                    question_name: answer
                    for question_name, answer in response["answers"].items()
                    if question_name.partition("__")[0] in selected_case_keys
                },
            }
            for response in responses
        ]

    participants = fetch_api("/api/participants/")
    if min_completed_cases > 0:
        full_survey_stats = summarize_participants(responses, participants, survey_path)
        responses = [
            response
            for response, stats in zip(responses, full_survey_stats)
            if stats["completed_cases"] >= min_completed_cases
        ]
    responses = limit_response_cases(
        responses, survey_path, n_cases_max, min_cases=n_cases_min,
    )
    return responses, participants


def limit_response_cases(
    responses: list[dict[str, Any]],
    survey_path: str | Path,
    n_cases: int,
    *,
    min_cases: int = 1,
) -> list[dict[str, Any]]:
    """Keep inclusive 1-based case positions per group; n_cases=0 keeps none."""
    if n_cases < 0:
        raise ValueError("n_cases must be non-negative.")
    if min_cases < 1:
        raise ValueError("min_cases must be at least 1.")
    if n_cases > 0 and min_cases > n_cases:
        raise ValueError("min_cases must not exceed n_cases.")

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
        if min_cases <= cases_by_visibility[visibility] <= n_cases:
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
    survey_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    survey_path = SURVEY_PATH if survey_path is None else survey_path
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
RankingMethod = Literal["borda", "plackett_luce", "stratified_borda"]
RankingItem = TypeVar("RankingItem")


@dataclass(frozen=True)
class RankingObservation:
    case_key: str
    group: int
    category_id: str
    triplet: Triplet


def _ranking_question_identity(question_name: str) -> tuple[str, int]:
    match = re.fullmatch(r"(.+)__0__group-([0-9]+)__ranking", question_name)
    if match is None:
        raise ValueError(f"Invalid ranking question name: {question_name!r}.")
    return match[1], int(match[2])


def extract_observations_by_category(
    responses: list[dict[str, Any]],
    survey_path: str | Path,
    *,
    skip_incomplete: bool = False,
) -> dict[str, list[RankingObservation]]:
    """Return rankings per category name, retaining case, group, and row IDs."""
    choices_by_question, category_names = _load_ranking_questions(survey_path)
    observations_by_category: dict[str, list[RankingObservation]] = defaultdict(list)

    for response in responses:
        for question_name, answer in response["answers"].items():
            if question_name not in choices_by_question:
                continue

            case_key, group = _ranking_question_identity(question_name)
            choices = choices_by_question[question_name]
            for category_id, selection in answer.items():
                best = selection.get("best")
                worst = selection.get("worst")
                middle = [model for model in choices if model not in {best, worst}]
                if best not in choices or worst not in choices or len(middle) != 1:
                    if skip_incomplete:
                        continue
                    raise ValueError(f"Invalid ranking in {question_name}, {category_id}.")
                observations_by_category[category_id].append(
                    RankingObservation(case_key, group, category_id, (best, middle[0], worst))
                )

    return {
        category_name: observations_by_category[category_id]
        for category_id, category_name in category_names.items()
        if observations_by_category[category_id]
    }


def extract_observations_by_case_type(
    responses: list[dict[str, Any]],
    survey_path: str | Path | None = None,
    cases_path: str | Path | None = None,
    *,
    skip_incomplete: bool = False,
) -> dict[str, dict[str, list[RankingObservation]]]:
    """Split rankings using case flags; missing inclusive flags mean general."""
    survey_path = SURVEY_PATH if survey_path is None else survey_path
    cases_path = CASES_PATH if cases_path is None else cases_path
    with open(cases_path, encoding="utf-8") as cases_file:
        cases = yaml.safe_load(cases_file)
    inclusive_by_case = {case["case_key"]: case.get("inclusive", False) for case in cases}
    choices_by_question, _ = _load_ranking_questions(survey_path)
    cases_by_type: dict[str, set[str]] = {"inclusive": set(), "general": set()}
    for question in choices_by_question:
        case_key, _ = _ranking_question_identity(question)
        if case_key not in inclusive_by_case:
            raise ValueError(f"No case definition for ranking question {question!r}.")
        case_type = "inclusive" if inclusive_by_case[case_key] else "general"
        cases_by_type[case_type].add(case_key)

    observations_by_category = extract_observations_by_category(
        responses, survey_path, skip_incomplete=skip_incomplete,
    )
    observations_by_type: dict[str, dict[str, list[RankingObservation]]] = {}
    for case_type, case_keys in cases_by_type.items():
        categories = {}
        for category, observations in observations_by_category.items():
            selected = [
                observation for observation in observations
                if observation.case_key in case_keys
            ]
            if selected:
                categories[category] = selected
        observations_by_type[case_type] = categories
    observations_by_type["total"] = observations_by_category
    return observations_by_type


def extract_triplets_by_category(
    responses: list[dict[str, Any]],
    survey_path: str | Path,
    *,
    skip_incomplete: bool = False,
) -> dict[str, list[Triplet]]:
    """Return (best, middle, worst) triplets per category name, in survey order."""
    return {
        category: [observation.triplet for observation in observations]
        for category, observations in extract_observations_by_category(
            responses, survey_path, skip_incomplete=skip_incomplete,
        ).items()
    }


def extract_triplets_by_case_type(
    responses: list[dict[str, Any]],
    survey_path: str | Path,
    cases_path: str | Path,
    *,
    skip_incomplete: bool = False,
) -> dict[str, dict[str, list[Triplet]]]:
    """Split rankings using case flags; missing inclusive flags mean general."""
    return {
        case_type: {
            category: [observation.triplet for observation in observations]
            for category, observations in categories.items()
        }
        for case_type, categories in extract_observations_by_case_type(
            responses, survey_path, cases_path, skip_incomplete=skip_incomplete,
        ).items()
    }


def _ranking_rows(
    scores: dict[str, float],
    counts: Counter[str],
    *,
    stratum_counts: Counter[str] | None = None,
) -> RankingRows:
    ordered_models = sorted(scores, key=lambda model: (-scores[model], model))
    return [
        {
            "rank": rank,
            "model": model,
            "score": scores[model],
            "answer_count": counts[model],
            **({"stratum_count": stratum_counts[model]} if stratum_counts is not None else {}),
        }
        for rank, model in enumerate(ordered_models, start=1)
    ]


def _borda_totals(triplets: list[Triplet]) -> tuple[Counter[str], Counter[str]]:
    totals: Counter[str] = Counter()
    counts: Counter[str] = Counter()
    for best, middle, worst in triplets:
        totals.update({best: 5, middle: 3, worst: 1})
        counts.update((best, middle, worst))
    return totals, counts


def rank_borda(triplets: list[Triplet]) -> RankingRows:
    """Rank models by mean Borda points per appearance: best=5, middle=3, worst=1."""
    totals, counts = _borda_totals(triplets)
    return _ranking_rows(
        {model: total / counts[model] for model, total in totals.items()},
        counts,
    )


def rank_stratified_borda(observations: list[RankingObservation]) -> RankingRows:
    """Pool rankings within cases, then average 5/3/1 case means equally per model."""
    strata: dict[str, list[Triplet]] = defaultdict(list)
    for observation in observations:
        strata[observation.case_key].append(observation.triplet)

    mean_totals: dict[str, float] = defaultdict(float)
    answer_counts: Counter[str] = Counter()
    stratum_counts: Counter[str] = Counter()
    for triplets in strata.values():
        totals, counts = _borda_totals(triplets)
        for model, total in totals.items():
            mean_totals[model] += total / counts[model]
            stratum_counts[model] += 1
        answer_counts.update(counts)

    return _ranking_rows(
        {model: total / stratum_counts[model] for model, total in mean_totals.items()},
        answer_counts,
        stratum_counts=stratum_counts,
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


def rank_observations(
    observations: list[RankingObservation],
    method: RankingMethod = "borda",
) -> RankingRows:
    """Apply a ranking method without discarding stratum identity prematurely."""
    if method == "stratified_borda":
        return rank_stratified_borda(observations)
    if method == "borda":
        return rank_borda([observation.triplet for observation in observations])
    if method == "plackett_luce":
        return rank_plackett_luce([observation.triplet for observation in observations])
    raise ValueError(f"Unknown ranking method: {method!r}.")


def rank_by_category(
    triplets_by_category: dict[str, list[RankingItem]],
    rank: Callable[[list[RankingItem]], RankingRows],
) -> dict[str, RankingRows]:
    return {
        category: rank(triplets)
        for category, triplets in triplets_by_category.items()
    }


def rank_overall(
    triplets_by_category: dict[str, list[RankingItem]],
    rank: Callable[[list[RankingItem]], RankingRows],
) -> RankingRows:
    """Rank models on rankings pooled across categories, retaining any metadata."""
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


def rank_llms_by_category_stratified_borda(
    responses: list[dict[str, Any]],
    survey_path: str | Path,
    *,
    skip_incomplete: bool = False,
) -> dict[str, RankingRows]:
    return rank_by_category(
        extract_observations_by_category(
            responses, survey_path, skip_incomplete=skip_incomplete,
        ),
        rank_stratified_borda,
    )