"""Generate the SurveyJS survey.json for this assessment round."""

import json
from collections import OrderedDict
from pathlib import Path

import click
from plct_llm_compare.models import TestCaseResponce

from .comparison_design import (
    MODELS_PER_COMPARISON,
    ComparisonAssignment,
    build_group_assignments,
    group_visibility_expression,
    order_models_for_presentation,
)
from .survey_presentation import COMPLETED_HTML, build_page_title, build_response_comparison

OUTPUT_DIR = "eval/output"

RANKING_CATEGORIES = [
    ("q1", "Korisnost za nastavnu praksu"),
    ("q2", "Izbor termina"),
    ("q3", "Prirodnost srpskog jezika"),
    ("q4", "Ukupan utisak"),
]

def _build_comparison_page(
    page_index: int,
    case_key: str,
    entries: list[tuple[TestCaseResponce, str, str]],
    group: int,
) -> dict:
    """Build one page for comparing a model triplet across all categories."""
    page_name = f"page{page_index}_group{group:02d}"
    question_name = f"{case_key}__0__group-{group:02d}__ranking"
    meta = entries[0][0]
    model_choices = [
        {"value": model_meta.model, "text": f"LLM {alias}"}
        for model_meta, alias, _ in entries
    ]
    distinct_choice_expressions = [
        (
            f"({{{question_name}.{question_id}.best}} empty or "
            f"{{{question_name}.{question_id}.worst}} empty or "
            f"{{{question_name}.{question_id}.best}} != "
            f"{{{question_name}.{question_id}.worst}})"
        )
        for question_id, _ in RANKING_CATEGORIES
    ]
    elements = [
        {
            "type": "html",
            "name": f"{page_name}_title",
            "html": build_page_title(meta),
        },
        build_response_comparison(page_name, entries),
        {
            "type": "matrixdropdown",
            "name": question_name,
            "title": "Poređenje odgovora",
            "description": (
                "Za svaki kriterijum izaberite najbolji i najlošiji odgovor. "
                "Preostali odgovor se smatra srednje rangiranim."
            ),
            "isRequired": True,
            "rows": [
                {"value": question_id, "text": category_title}
                for question_id, category_title in RANKING_CATEGORIES
            ],
            "columns": [
                {
                    "name": "best",
                    "title": "Najbolji",
                    "cellType": "dropdown",
                    "isRequired": True,
                    "choices": model_choices,
                },
                {
                    "name": "worst",
                    "title": "Najlošiji",
                    "cellType": "dropdown",
                    "isRequired": True,
                    "choices": model_choices,
                },
            ],
            "validators": [
                {
                    "type": "expression",
                    "expression": " and ".join(distinct_choice_expressions),
                    "text": "Najbolji i najlošiji odgovor moraju biti različiti.",
                }
            ],
        },
        {
            "type": "comment",
            "name": f"{case_key}__0__group-{group:02d}__q5",
            "title": "Šta smatrate da je bolje ili lošije u odgovorima jednog ili drugog LLM-a?",
        },
    ]
    return {
        "name": page_name,
        "visibleIf": group_visibility_expression(group),
        "elements": elements,
    }


def _get_shared_model_ids(
    case_groups: OrderedDict[str, list[tuple[TestCaseResponce, str, str]]],
) -> tuple[str, ...]:
    """Return the common model order, rejecting incomplete case comparisons."""
    first_case_key, first_entries = next(iter(case_groups.items()))
    model_ids = tuple(meta.model for meta, _, _ in first_entries)
    if len(set(model_ids)) != len(model_ids):
        raise click.ClickException(f"Case {first_case_key} contains duplicate model responses.")

    expected_models = set(model_ids)
    for case_key, entries in case_groups.items():
        case_models = {meta.model for meta, _, _ in entries}
        if case_models != expected_models:
            missing = sorted(expected_models - case_models)
            extra = sorted(case_models - expected_models)
            raise click.ClickException(
                f"Case {case_key} has a different model set "
                f"(missing={missing}, extra={extra})."
            )
    return model_ids


def _entries_for_assignment(
    entries: list[tuple[TestCaseResponce, str, str]],
    assignment: ComparisonAssignment,
) -> list[tuple[TestCaseResponce, str, str]]:
    """Select an assignment's responses and apply page-local A/B/C aliases."""
    entries_by_model = {meta.model: (meta, html_content) for meta, _, html_content in entries}
    return [
        (entries_by_model[model_id][0], chr(ord("A") + index), entries_by_model[model_id][1])
        for index, model_id in enumerate(order_models_for_presentation(assignment))
    ]


def do_survey(survey_file: str) -> None:
    """Scan the inference output directory for *.html files and generate the survey definition."""
    output_path = Path(OUTPUT_DIR)
    html_files = sorted(output_path.glob("*.html"))

    if not html_files:
        click.echo("No HTML files found in the output directory.")
        return

    # Collect entries grouped by case_key (preserving insertion order)
    case_groups: OrderedDict[str, list[tuple[TestCaseResponce, str, str]]] = OrderedDict()
    model_aliases: dict[str, str] = {}
    next_model_alias = "A"

    for html_file in html_files:
        json_file = html_file.with_suffix(".json")
        if not json_file.exists():
            click.echo(f"  Skipping {html_file.name}: no matching JSON metadata.")
            continue

        meta = TestCaseResponce.model_validate_json(json_file.read_text(encoding="utf-8"))
        if meta.take > 1:
            click.echo(f"  Skipping {html_file.name}: take {meta.take} > 1.")
            continue

        model_alias = model_aliases.get(meta.model)
        if not model_alias:
            model_alias = next_model_alias
            model_aliases[meta.model] = model_alias
            next_model_alias = chr(ord(next_model_alias) + 1)

        html_content = html_file.read_text(encoding="utf-8")
        case_groups.setdefault(meta.case_key, []).append((meta, model_alias, html_content))
        click.echo(f"  Added {html_file.name} to group {meta.case_key}")

    if not case_groups:
        raise click.ClickException("No eligible model responses were found.")

    model_ids = _get_shared_model_ids(case_groups)
    assignments = build_group_assignments(case_groups, model_ids)

    # Build one group-specific page per case.
    pages = []
    page_idx = 1
    for assignment in assignments:
        entries = _entries_for_assignment(case_groups[assignment.case_key], assignment)
        pages.append(
            _build_comparison_page(
                page_idx,
                assignment.case_key,
                entries,
                assignment.group,
            )
        )
        page_idx += 1

    survey = {
        "title": "Upitnik o odgovorima AI Asistenta",
        "description": (
            "U ovom upitniku će se nalaziti primeri raznih odgovora AI asistenta "
            "na razne prompt-ove i od vas se očekuje da ocenite svaki od odgovora"
        ),
        "pages": pages,
        "showProgressBar": "top",
        "checkErrorsMode": "onValueChanged",
        "completedHtml": COMPLETED_HTML,
    }

    survey_path = Path(survey_file)
    survey_path.parent.mkdir(parents=True, exist_ok=True)
    survey_path.write_text(json.dumps(survey, indent=2, ensure_ascii=False), encoding="utf-8")
    group_count = len(assignments) // len(case_groups)
    click.echo(
        f"Survey saved to {survey_path} ({len(pages)} pages, {group_count} participant "
        f"groups, {MODELS_PER_COMPARISON} models per comparison)"
    )
