"""Generate the SurveyJS survey.json for this assessment round."""

import json
from collections import OrderedDict
from pathlib import Path

import click
from plct_llm_compare.models import TestCaseResponce

OUTPUT_DIR = "eval/output"

RANKING_CATEGORIES = [
    ("q1", "Korisnost za nastavnu praksu"),
    ("q2", "Izbor termina"),
    ("q3", "Prirodnost srpskog jezika"),
    ("q4", "Ukupan utisak"),
]

HORIZONTAL_DRAG_HANDLER = (
    "window.__llmRankingPointerX=event.clientX;"
    "if(!window.__llmRankingPointerTracker){"
    "document.addEventListener('pointermove',function(pointerEvent){"
    "window.__llmRankingPointerX=pointerEvent.clientX;"
    "},true);"
    "window.__llmRankingPointerTracker=true;"
    "}"
    "var questionName=this.closest('[data-name]').dataset.name;"
    "var dragDrop=survey.getQuestionByName(questionName).dragDropRankingChoices;"
    "if(!dragDrop.__llmHorizontalHitTest){"
    "dragDrop.calculateIsBottom=function(_clientY,dropTargetNode){"
    "var rect=dropTargetNode.getBoundingClientRect();"
    "return window.__llmRankingPointerX>=rect.left+rect.width/2;"
    "};"
    "dragDrop.__llmHorizontalHitTest=true;"
    "}"
)


def _build_response_viewer(
    page_name: str,
    question_name: str,
    entries: list[tuple[TestCaseResponce, str, str]],
) -> tuple[dict, list[dict[str, str]]]:
    """Build draggable ranking tabs and their scrollable response panels."""
    viewer_id = f"{page_name}_responseViewer"
    model_choices = []
    tab_panels = []

    for model_meta, alias, html_content in entries:
        tab_id = f"{page_name}_llm{alias}_tab"
        panel_id = f"{page_name}_llm{alias}_panel"
        model_choices.append(
            {
                "value": model_meta.model.split("/")[-1],
                "text": (
                    f'<input class="llm-rank-tab-input" type="radio" '
                    f'name="{page_name}_modelTabs" id="{tab_id}" '
                    f'aria-label="LLM {alias}">'
                    f'<span class="llm-rank-tab-label" '
                    f'aria-controls="{panel_id}" '
                    f'onpointerdown="{HORIZONTAL_DRAG_HANDLER}" '
                    f'onclick="this.previousElementSibling.checked = true">'
                    f'LLM {alias}</span>'
                ),
            }
        )
        tab_panels.append(
            f'<section class="llm-tab-panel llm-tab-panel-{alias}" id="{panel_id}" '
            f'aria-label="Odgovor LLM {alias}">{html_content}</section>'
        )

    active_panel_rules = "\n".join(
        f"body:has(#{page_name}_llm{alias}_tab:checked) #{page_name}_llm{alias}_panel "
        "{ display: block; }"
        for _, alias, _ in entries
    )
    initial_panel_rules = "\n".join(
        f'body:not(:has(input[name="{page_name}_modelTabs"]:checked))'
        f':has([data-name="{question_name}"] .sv-ranking-item:first-child '
        f'#{page_name}_llm{alias}_tab) #{page_name}_llm{alias}_panel '
        "{ display: block; }"
        for _, alias, _ in entries
    )
    viewer_html = f"""
        <style>
            .sd-body.sd-body--static {{ max-width: 1280px; }}
            [data-name="{question_name}"] .sv-ranking {{
                display: flex;
                flex-wrap: wrap;
                gap: 0.5rem;
            }}
            [data-name="{question_name}"] .sv-ranking-item {{
                flex: 1 1 9rem;
                width: auto !important;
                min-width: 8rem;
            }}
            [data-name="{question_name}"] .sv-ranking-item > div,
            [data-name="{question_name}"] .sv-ranking-item__content {{ height: 100%; }}
            [data-name="{question_name}"] .sv-ranking-item__content {{
                position: relative;
                box-sizing: border-box;
                border: 1px solid #c7ced8;
                background: #eef1f5;
                color: #263238;
            }}
            [data-name="{question_name}"] .sv-ranking-item:has(.llm-rank-tab-input:checked)
                .sv-ranking-item__content {{
                border-color: #167d6a;
                background: #167d6a;
                color: #fff;
            }}
            body:not(:has(input[name="{page_name}_modelTabs"]:checked))
                [data-name="{question_name}"] .sv-ranking-item:first-child
                .sv-ranking-item__content {{
                border-color: #167d6a;
                background: #167d6a;
                color: #fff;
            }}
            [data-name="{question_name}"] .sv-ranking-item__text {{ flex: 1; }}
            .llm-rank-tab-input {{
                position: absolute;
                width: 1px;
                height: 1px;
                opacity: 0;
            }}
            .llm-rank-tab-label {{
                position: absolute;
                inset: 0;
                z-index: 1;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 2.5rem;
                box-sizing: border-box;
                padding: 0 0.75rem 0 4.5rem;
                font-weight: 600;
                text-align: center;
                cursor: pointer;
            }}
            .sv-ranking-item:focus-visible .llm-rank-tab-label {{
                outline: 3px solid #f0b429;
                outline-offset: 2px;
            }}
            #{viewer_id} {{ margin: 0 0 1.5rem; }}
            #{viewer_id} .llm-tab-panel {{
                display: none;
                box-sizing: border-box;
                padding: 1rem 1.25rem;
                overflow-x: auto;
                border: 1px solid #c7ced8;
                background: #fff;
            }}
            #{viewer_id} .llm-tab-panel img {{ max-width: 100%; height: auto; }}
            #{viewer_id} .llm-tab-panel pre {{ overflow-x: auto; }}
            {initial_panel_rules}
            {active_panel_rules}
        </style>
        <div id="{viewer_id}" class="llm-response-viewer">{''.join(tab_panels)}</div>
    """
    return (
        {
            "type": "html",
            "name": f"{page_name}_responses",
            "html": viewer_html,
        },
        model_choices,
    )


def _build_ranking_page(
    page_index: int,
    case_key: str,
    entries: list[tuple[TestCaseResponce, str, str]],
    question_id: str,
    category_title: str,
) -> dict:
    """Build one SurveyJS page with draggable response tabs for one category."""
    page_name = f"page{page_index}"
    question_name = f"{case_key}__0__-__{question_id}"
    meta = entries[0][0]
    title_html = (
        f'<h4>Poređenje odgovora u kontekstu lekcije '
        f'<a href="{meta.activity_url}" target="_blank">{meta.activity_desc}</a></h4>'
        f'<h3>Prompt: {meta.prompt}</h3>'
    )
    response_viewer, model_choices = _build_response_viewer(page_name, question_name, entries)
    elements = [
        {
            "type": "html",
            "name": f"{page_name}_title",
            "html": title_html,
        },
        {
            "type": "ranking",
            "name": question_name,
            "title": category_title,
            "description": (
                "Prevucite LLM kartice da ih rangirate od najboljeg ka najlošijem. "
                "Kliknite naziv modela da prikažete njegov odgovor."
            ),
            "isRequired": True,
            "selectToRankEnabled": False,
            "choicesOrder": "random",
            "choices": model_choices,
        },
        response_viewer,
    ]
    if question_id == RANKING_CATEGORIES[-1][0]:
        elements.append(
            {
                "type": "comment",
                "name": f"{case_key}__0__-__q5",
                "title": "Šta smatrate da je bolje ili lošije u odgovorima jednog ili drugog LLM-a?",
            }
        )
    return {
        "name": page_name,
        "elements": elements,
    }


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

    # Build one page per case and ranking category.
    pages = []
    page_idx = 1
    for case_key, entries in case_groups.items():
        for question_id, category_title in RANKING_CATEGORIES:
            pages.append(
                _build_ranking_page(
                    page_idx,
                    case_key,
                    entries,
                    question_id,
                    category_title,
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
        "completedHtml": "<h3>Hvala vam!</h3>",
    }

    survey_path = Path(survey_file)
    survey_path.parent.mkdir(parents=True, exist_ok=True)
    survey_path.write_text(json.dumps(survey, indent=2, ensure_ascii=False), encoding="utf-8")
    click.echo(f"Survey saved to {survey_path} ({len(pages)} pages)")
