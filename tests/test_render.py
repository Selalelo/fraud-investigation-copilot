from fraud_copilot.pipeline import process_alert
from fraud_copilot.render import render_case, render_case_markdown
from fraud_copilot.storage import Store

from .factories import clean_world, make_alert


def test_render_case_contains_all_case_screen_sections():
    store = Store()
    case = process_alert(make_alert(), clean_world(), store)
    text = render_case(case)
    assert "PRIORITY" in text
    assert "SLA" in text
    assert "Potential typology" in text
    assert "INDICATORS" in text
    assert "COUNTER-INDICATORS" in text
    assert "LINKED ENTITIES" in text
    assert "AI NARRATIVE" in text
    assert "ACTIONS" in text
    assert "Reason code" in text


def test_render_markdown_contains_all_sections():
    store = Store()
    case = process_alert(make_alert(), clean_world(), store)
    md = render_case_markdown(case)
    assert md.startswith("# Case #")
    assert "## Indicators" in md
    assert "## Counter-indicators" in md
    assert "## Linked entities" in md
    assert "## AI narrative" in md
    assert "## Actions" in md


def test_render_shows_evidence_incomplete_warning():
    store = Store()
    world = clean_world()
    del world.devices["CUST-1"]
    case = process_alert(make_alert(), world, store)
    text = render_case(case)
    assert "Evidence incomplete" in text
    assert "device" in text.lower()


def test_render_shows_narrative_unavailable_fallback():
    store = Store()
    world = clean_world()
    case = process_alert(make_alert(amount=2000.0), world, store)
    # clean, quiet case -> only counter-indicators, which still validate and produce a narrative;
    # force the fallback path directly to test the render branch.
    from fraud_copilot.models import NarrativeStatus
    case.narrative_status = NarrativeStatus.UNAVAILABLE
    case.narrative = None
    text = render_case(case)
    assert "AI narrative unavailable" in text

    md = render_case_markdown(case)
    assert "_AI narrative unavailable._" in md
