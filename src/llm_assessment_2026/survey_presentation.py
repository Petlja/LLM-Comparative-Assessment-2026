"""Render the presentation elements used by model-comparison survey pages."""

from plct_llm_compare.models import TestCaseResponce

COMPLETED_HTML = "<h3>Hvala vam!</h3>"


def build_page_title(meta: TestCaseResponce) -> str:
    """Render the lesson context and prompt shown above a ranking question."""
    return (
        f'<h4>Poređenje odgovora u kontekstu lekcije '
        f'<a href="{meta.activity_url}" target="_blank">{meta.activity_desc}</a></h4>'
        f'<h3>Prompt: {meta.prompt}</h3>'
    )


def build_response_comparison(
    page_name: str,
    entries: list[tuple[TestCaseResponce, str, str]],
) -> dict:
    """Build three response columns that collapse to tabs on narrow screens."""
    presentation_id = f"{page_name}_responseComparison"
    tab_controls = []
    tab_panels = []

    for index, (_, alias, html_content) in enumerate(entries):
        tab_id = f"{page_name}_llm{alias}_tab"
        panel_id = f"{page_name}_llm{alias}_panel"
        checked = " checked" if index == 0 else ""
        tab_controls.append(
            f'<input class="llm-response-tab-input" type="radio" '
            f'name="{page_name}_modelTabs" id="{tab_id}"{checked}>'
            f'<label class="llm-response-tab-label" for="{tab_id}" '
            f'aria-controls="{panel_id}">LLM {alias}</label>'
        )
        tab_panels.append(
            f'<section class="llm-response-panel" id="{panel_id}" '
            f'aria-label="Odgovor LLM {alias}">'
            f'<h4 class="llm-response-heading">LLM {alias}</h4>'
            f'<div class="llm-response-content">{html_content}</div></section>'
        )

    mobile_active_panel_rules = "\n".join(
        f"body:has(#{page_name}_llm{alias}_tab:checked) #{page_name}_llm{alias}_panel "
        "{ display: block; }"
        for _, alias, _ in entries
    )
    presentation_html = f"""
        <style>
            #surveyContainer {{ max-width: 1800px; }}
            .sd-body.sd-body--static {{ max-width: none; }}
            #{presentation_id} {{ margin: 0 0 1.5rem; }}
            #{presentation_id} .llm-response-tabs {{ display: none; }}
            #{presentation_id} .llm-response-tab-input {{
                position: absolute;
                width: 1px;
                height: 1px;
                opacity: 0;
            }}
            #{presentation_id} .llm-response-grid {{
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 0.75rem;
                align-items: stretch;
            }}
            #{presentation_id} .llm-response-panel {{
                min-width: 0;
                box-sizing: border-box;
                border: 1px solid #c7ced8;
                background: #fff;
            }}
            #{presentation_id} .llm-response-heading {{
                position: sticky;
                top: 0;
                z-index: 1;
                margin: 0;
                padding: 0.75rem 1rem;
                border-bottom: 1px solid #c7ced8;
                background: #eef1f5;
                font-size: 1.25rem;
            }}
            #{presentation_id} .llm-response-content {{ padding: 0.25rem 1rem 1rem; }}
            #{presentation_id} .llm-response-content h1,
            #{presentation_id} .llm-response-content h2,
            #{presentation_id} .llm-response-content h3,
            #{presentation_id} .llm-response-content h4,
            #{presentation_id} .llm-response-content h5,
            #{presentation_id} .llm-response-content h6 {{
                margin: 1rem 0 0.5rem;
                line-height: 1.2;
            }}
            #{presentation_id} .llm-response-content h1 {{ font-size: 1.75rem; }}
            #{presentation_id} .llm-response-content h2 {{ font-size: 1.5rem; }}
            #{presentation_id} .llm-response-content h3 {{ font-size: 1.25rem; }}
            #{presentation_id} .llm-response-content h4,
            #{presentation_id} .llm-response-content h5,
            #{presentation_id} .llm-response-content h6 {{ font-size: 1.125rem; }}
            #{presentation_id} .llm-response-content p {{
                margin: 0.5rem 0;
                line-height: 1.5;
            }}
            #{presentation_id} .llm-response-content ul,
            #{presentation_id} .llm-response-content ol {{ margin: 0.5rem 0; }}
            #{presentation_id} .llm-response-content li {{ margin: 0.125rem 0; }}
            #{presentation_id} img {{ max-width: 100%; height: auto; }}
            #{presentation_id} pre {{ overflow-x: auto; }}
            @media (max-width: 900px) {{
                #{presentation_id} .llm-response-tabs {{
                    display: grid;
                    grid-template-columns: repeat(3, minmax(0, 1fr));
                    gap: 0.375rem;
                    margin-bottom: 0.5rem;
                }}
                #{presentation_id} .llm-response-tab-label {{
                    padding: 0.625rem;
                    border: 1px solid #c7ced8;
                    background: #eef1f5;
                    font-weight: 600;
                    text-align: center;
                    cursor: pointer;
                }}
                #{presentation_id} .llm-response-tab-input:checked +
                    .llm-response-tab-label {{
                    border-color: #167d6a;
                    background: #167d6a;
                    color: #fff;
                }}
                #{presentation_id} .llm-response-tab-input:focus-visible +
                    .llm-response-tab-label {{
                    outline: 3px solid #f0b429;
                    outline-offset: 2px;
                }}
                #{presentation_id} .llm-response-grid {{ display: block; }}
                #{presentation_id} .llm-response-panel {{ display: none; }}
                {mobile_active_panel_rules}
            }}
        </style>
        <div id="{presentation_id}" class="llm-response-comparison">
            <div class="llm-response-tabs">{''.join(tab_controls)}</div>
            <div class="llm-response-grid">{''.join(tab_panels)}</div>
        </div>
    """
    return {
        "type": "html",
        "name": f"{page_name}_responseComparison",
        "html": presentation_html,
    }