from scanner import extract

def test_parse_items_filters_invalid():
    raw = '''[
      {"title": "Email webhook", "summary": "shipped PR #4", "status": "done"},
      {"title": "", "summary": "ignore me", "status": "done"},
      {"summary": "no title", "status": "in_progress"},
      {"title": "Mapping UX", "summary": "wip", "status": "weird"}
    ]'''
    items = extract.parse_items(raw, fallback_project="webapp")
    assert len(items) == 2
    assert items[0] == {"project": "webapp", "title": "Email webhook", "summary": "shipped PR #4", "status": "done"}
    assert items[1]["status"] == "in_progress"  # invalid status coerced to default

def test_parse_items_handles_empty_and_fenced():
    assert extract.parse_items("[]", "p") == []
    assert extract.parse_items("```json\n[]\n```", "p") == []

def test_parse_items_prefers_model_project_over_fallback():
    raw = '[{"project":"Viz Dashboard","title":"X","summary":"s","status":"done"}]'
    items = extract.parse_items(raw, fallback_project="vandaal")
    assert items[0]["project"] == "viz-dashboard"  # slugified, fallback ignored

def test_parse_items_uses_fallback_when_project_blank():
    raw = '[{"project":"","title":"X","summary":"s","status":"done"}]'
    assert extract.parse_items(raw, fallback_project="home")[0]["project"] == "home"

def test_extract_features_calls_runner_and_parses():
    captured = {}
    def fake_runner(prompt):
        captured["prompt"] = prompt
        return '[{"title":"X","summary":"did x","status":"done"}]'
    items = extract.extract_features("some transcript text", project="apiservice", runner=fake_runner)
    assert items == [{"project": "apiservice", "title": "X", "summary": "did x", "status": "done"}]
    assert "some transcript text" in captured["prompt"]  # transcript is fed to the model

def test_extract_features_empty_text_skips_runner():
    def boom(prompt):
        raise AssertionError("runner should not be called for empty text")
    assert extract.extract_features("   ", project="p", runner=boom) == []
