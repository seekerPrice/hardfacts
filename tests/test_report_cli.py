"""`hardfacts report`: a dataset-level audit of transcripts (the freelance deliverable)."""

import json

from hardfacts.cli import main

ROWS = [
    {"id": "t1", "output": "Tracking EN123456780MY arrives 2 October.", "sources": [{"tracking": "EN123456789MY", "eta": "2026-10-03"}]},
    {"id": "t2", "output": "Your refund of RM 45 is on its way.", "sources": [{"refund": 45}]},
    {"id": "t3", "output": "We open at 8 AM daily.", "sources": ["Hours: 9:00-17:00, Sat 10:00-14:00"]},
]


def write_jsonl(tmp_path, rows):
    path = tmp_path / "transcripts.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return str(path)


def test_report_counts_responses_with_unsupported_facts_by_kind(tmp_path, capsys):
    out = tmp_path / "report.json"

    assert main(["report", write_jsonl(tmp_path, ROWS), "--json", str(out)]) == 0

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["responses"] == 3
    assert data["responses_with_unsupported"] == 2
    assert data["unsupported_by_kind"] == {"identifier": 1, "date": 1, "time": 1}
    assert [e["id"] for e in data["examples"]] == ["t1", "t1", "t3"]


def test_report_writes_a_self_contained_html_page(tmp_path, capsys):
    html = tmp_path / "report.html"

    main(["report", write_jsonl(tmp_path, ROWS), "--html", str(html)])

    page = html.read_text(encoding="utf-8")
    assert "EN123456780MY" in page and "<script src" not in page


def test_fail_over_turns_the_report_into_a_ci_gate(tmp_path, capsys):
    path = write_jsonl(tmp_path, ROWS)

    assert main(["report", path, "--fail-over", "0.5"]) == 1   # 2/3 responses exceed 50%
    assert main(["report", path, "--fail-over", "0.9"]) == 0


def test_a_malformed_line_is_a_usage_error_naming_the_line(tmp_path, capsys):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"output": "ok", "sources": []}\nnot json\n', encoding="utf-8")

    assert main(["report", str(path)]) == 2
    assert "line 2" in capsys.readouterr().err


def test_null_or_string_sources_are_usage_errors_naming_the_line(tmp_path, capsys):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"output": "RM 45", "sources": [{"refund": 45}]}\n{"output": "RM 45", "sources": null}\n', encoding="utf-8")
    assert main(["report", str(path)]) == 2
    assert "line 2" in capsys.readouterr().err
    path.write_text('{"output": "RM 45", "sources": "refund RM 45"}\n', encoding="utf-8")
    assert main(["report", str(path)]) == 2


def test_jsonl_with_a_bom_and_unicode_line_separators_inside_strings(tmp_path, capsys):
    path = tmp_path / "ok.jsonl"
    row = {"output": "Line one RM 45", "sources": [{"refund": 45}]}
    path.write_bytes(b"\xef\xbb\xbf" + (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
    assert main(["report", str(path)]) == 0


def test_fail_over_must_be_a_share_between_0_and_1(tmp_path, capsys):
    path = write_jsonl(tmp_path, ROWS)
    assert main(["report", path, "--fail-over", "nan"]) == 2
    assert main(["report", path, "--fail-over", "1.5"]) == 2


def test_report_separates_arithmetic_from_unexplained_values(tmp_path, capsys):
    rows = ROWS + [{"id": "t4", "output": "The new kettle is $101.12 and yours was $94.80, so you pay $6.32 more.",
                    "sources": [{"current": 94.8, "new": 101.12}]}]
    out, page = tmp_path / "report.json", tmp_path / "report.html"

    main(["report", write_jsonl(tmp_path, rows), "--json", str(out), "--html", str(page)])

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["unsupported_with_derivation"] == 1
    assert data["responses_with_unexplained"] == 2  # t1 and t3; t4's only flag is arithmetic
    assert [x["derivation"] for x in data["examples"]][-1] == "$101.12 − $94.80"
    assert "$101.12 − $94.80" in page.read_text(encoding="utf-8")
