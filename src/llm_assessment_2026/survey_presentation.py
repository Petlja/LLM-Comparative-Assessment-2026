"""Render the presentation elements used by ranking survey pages."""

from plct_llm_compare.models import TestCaseResponce

COMPLETED_HTML = "<h3>Hvala vam!</h3>"

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


def build_page_title(meta: TestCaseResponce) -> str:
    """Render the lesson context and prompt shown above a ranking question."""
    return (
        f'<h4>Poređenje odgovora u kontekstu lekcije '
        f'<a href="{meta.activity_url}" target="_blank">{meta.activity_desc}</a></h4>'
        f'<h3>Prompt: {meta.prompt}</h3>'
    )


def build_ranking_presentation(
    page_name: str,
    question_name: str,
    entries: list[tuple[TestCaseResponce, str, str]],
) -> tuple[dict, list[dict[str, str]]]:
    """Build draggable ranking tabs and their scrollable model-answer panels."""
    presentation_id = f"{page_name}_rankingPresentation"
    model_choices = []
    tab_panels = []

    for model_meta, alias, html_content in entries:
        tab_id = f"{page_name}_llm{alias}_tab"
        panel_id = f"{page_name}_llm{alias}_panel"
        model_choices.append(
            {
                "value": model_meta.model,
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
    presentation_html = f"""
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
            #{presentation_id} {{ margin: 0 0 1.5rem; }}
            #{presentation_id} .llm-tab-panel {{
                display: none;
                box-sizing: border-box;
                padding: 1rem 1.25rem;
                overflow-x: auto;
                border: 1px solid #c7ced8;
                background: #fff;
            }}
            #{presentation_id} .llm-tab-panel img {{ max-width: 100%; height: auto; }}
            #{presentation_id} .llm-tab-panel pre {{ overflow-x: auto; }}
            {initial_panel_rules}
            {active_panel_rules}
        </style>
        <div id="{presentation_id}" class="llm-ranking-presentation">{''.join(tab_panels)}</div>
    """
    return (
        {
            "type": "html",
            "name": f"{page_name}_rankingPresentation",
            "html": presentation_html,
        },
        model_choices,
    )