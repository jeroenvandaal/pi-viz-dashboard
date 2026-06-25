from scanner.markers import parse_markers, closure_items

def test_parses_start_and_done():
    text = (
        "Some prose.\n"
        "▶ feature start — pi-dashboard: Website metrics board\n"
        "more prose\n"
        "✅ feature done — viz-dashboard: Pi viz dashboard\n"
    )
    items = parse_markers(text)
    assert items == [
        {"project": "pi-dashboard", "title": "Website metrics board", "status": "in_progress", "source": "marker", "summary": ""},
        {"project": "viz-dashboard", "title": "Pi viz dashboard", "status": "done", "source": "marker", "summary": ""},
    ]

def test_name_may_contain_colon():
    items = parse_markers("✅ feature done — vector: Email integration: approve-by-email")
    assert items[0]["project"] == "vector"
    assert items[0]["title"] == "Email integration: approve-by-email"

def test_ignores_non_markers_and_plain_prose():
    assert parse_markers("we finished the feature done today") == []
    assert parse_markers("feature done — x: y") == []   # missing the ▶/✅ glyph
    assert parse_markers("") == []

def test_closure_items_active_passes_through():
    text = "▶ feature start — p: Alpha\n✅ feature done — p: Beta\n"
    assert closure_items(text, ended=False) == parse_markers(text)

def test_closure_items_ended_soft_closes_unclosed_starts():
    text = "▶ feature start — p: Alpha\n✅ feature done — p: Beta\n"
    by = {i["title"]: i for i in closure_items(text, ended=True)}
    assert by["Alpha"]["status"] == "done" and by["Alpha"]["auto_closed"] is True
    assert by["Beta"]["status"] == "done" and "auto_closed" not in by["Beta"]  # explicit done stays hard

def test_closure_items_ended_skips_started_then_done():
    text = "▶ feature start — p: Alpha\n✅ feature done — p: Alpha\n"
    items = closure_items(text, ended=True)
    assert len(items) == 1 and items[0]["status"] == "done" and "auto_closed" not in items[0]

def test_closure_items_ended_deduplicates_repeated_unclosed_starts():
    text = "▶ feature start — p: Alpha\n▶ feature start — p: Alpha\n"
    items = closure_items(text, ended=True)
    assert len(items) == 1
    assert items[0]["title"] == "Alpha"
    assert items[0]["auto_closed"] is True
