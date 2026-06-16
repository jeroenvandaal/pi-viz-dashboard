import pathlib
from scanner import transcripts

FIX = pathlib.Path(__file__).parent / "fixtures"

def test_project_label_from_encoded_dir():
    enc = "-Users-dev-Documents-AI-Projects-myapp"
    assert transcripts.project_label(enc) == "myapp"

def test_read_assistant_text_since_offset():
    path = FIX / "session_sample.jsonl"
    text, new_offset = transcripts.read_new_assistant_text(path, offset=0)
    assert "approve-by-email webhook" in text
    assert "354 tests pass" in text
    assert new_offset == path.stat().st_size

def test_read_from_offset_returns_only_new():
    path = FIX / "session_sample.jsonl"
    _, mid = transcripts.read_new_assistant_text(path, offset=0)
    text2, end = transcripts.read_new_assistant_text(path, offset=mid)
    assert text2 == ""
    assert end == mid
