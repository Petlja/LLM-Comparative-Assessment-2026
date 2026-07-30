"""Test case handling for this assessment round."""

from collections import Counter
from pathlib import Path

import yaml
from plct_llm_compare.models import TestCase


def load_cases(cases_path: str | Path) -> list[TestCase]:
    """Load and validate test cases from a YAML file."""
    raw = yaml.safe_load(Path(cases_path).read_text(encoding="utf-8")) or []
    return [TestCase.model_validate(item) for item in raw]


def do_check_cases(cases_path: str | Path) -> None:
    cases = load_cases(cases_path)
    counts = Counter(c.case_key for c in cases)
    duplicates = sorted(key for key, count in counts.items() if count > 1)

    print(f"Cases: {len(cases)}")
    print(f"Courses: {len({c.course_key for c in cases})}")
    if duplicates:
        raise SystemExit(f"Duplicate case keys: {', '.join(duplicates)}")
