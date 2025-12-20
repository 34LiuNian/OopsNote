import pytest

from app.clients.openai_client import _parse_json_block


def test_parse_json_block_repairs_invalid_backslash_escapes_in_strings() -> None:
    # The model sometimes returns LaTeX-style escapes like \(a\) with single backslashes
    # inside JSON strings, which is invalid JSON (e.g. "\(a\)" contains \( as an invalid escape).
    text = (
        "```json\n"
        "{\n"
        '  \"verdict\": \"revise\",\n'
        '  \"answer\": \"示例：已知 \\(a\\) 与 \\(b\\)，则 c=\\\\sqrt(a^2+b^2)。\",\n'
        '  \"explanation\": \"使用勾股定理：\\(a^2+b^2=c^2\\)。\"\n'
        "}\n"
        "```"
    )

    data = _parse_json_block(text)
    assert data["verdict"] == "revise"
    assert "勾股定理" in data["explanation"]


def test_parse_json_block_raises_when_no_braces() -> None:
    with pytest.raises(ValueError):
        _parse_json_block("no json here")


def test_parse_json_block_repairs_literal_newlines_inside_strings() -> None:
    # Some OpenAI-compatible gateways return JSON-like output where string values
    # contain literal newlines (invalid JSON). The parser should escape these.
    text = '{"answer": "line1\nline2", "explanation": "ok"}'
    # Inject a literal newline character inside the JSON string value.
    text_with_literal_newline = text.replace("\\n", "\n")
    data = _parse_json_block(text_with_literal_newline)
    assert data["answer"] == "line1\nline2"
    assert data["explanation"] == "ok"


def test_parse_json_block_repairs_unicode_whitespace_outside_strings() -> None:
    # NBSP (\u00A0) is not valid JSON whitespace; some gateways/models emit it.
    # Our repair should normalize it so parsing succeeds.
    raw = '{"a": 1,\u00A0"b": 2}'
    payload = _parse_json_block(raw)
    assert payload == {"a": 1, "b": 2}


def test_parse_json_block_lenient_extraction_on_truncated_json() -> None:
    # Truncated before closing quote/braces.
    text = '{"answer": "hello", "explanation": "line1\nline2", "short_answer": "oops'
    payload = _parse_json_block(text)
    assert payload["answer"] == "hello"
    assert payload["explanation"] == "line1\nline2"
    assert payload["short_answer"].startswith("oops")


def test_lenient_extraction_reports_incomplete_keys() -> None:
    from app.clients.openai_client import _extract_lenient_top_level_string_fields_with_meta

    text = '{"answer": "ok", "short_answer": "oops'
    payload, incomplete = _extract_lenient_top_level_string_fields_with_meta(text, ("answer", "short_answer"))
    assert payload["answer"] == "ok"
    assert payload["short_answer"].startswith("oops")
    assert "short_answer" in incomplete


def test_parse_json_block_lenient_extraction_on_pretty_truncated_json() -> None:
    text = (
        '{\n'
        '  "answer": "aa\\n\\n$$\\\\frac{x^2}{4}+\\\\frac{y^2}{3}=1$$",\n'
        '  "explanation": "ok",\n'
        '  "short_answer": "oops'  # truncated mid-string
    )
    payload = _parse_json_block(text)
    assert "answer" in payload
    assert payload["explanation"] == "ok"


def test_parse_json_block_balances_missing_closing_brace() -> None:
    # Some gateways omit the final closing brace even when all strings are closed.
    text = '{"answer": "ok", "explanation": "fine", "short_answer": "x"\n'
    payload = _parse_json_block(text)
    assert payload["answer"] == "ok"
    assert payload["explanation"] == "fine"
    assert payload["short_answer"] == "x"
