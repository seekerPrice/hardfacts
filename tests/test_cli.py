import json

from hardfacts.cli import main


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_exit_code_is_zero_when_every_claim_is_supported(tmp_path, capsys):
    out = write(tmp_path, "out.txt", "Delivery in 3 days.")
    src = write(tmp_path, "src.txt", "Standard delivery: 3 days.")

    assert main(["check", out, src]) == 0


def test_exit_code_is_one_and_the_unsupported_claim_is_printed(tmp_path, capsys):
    out = write(tmp_path, "out.txt", "Delivery in 5 days.")
    src = write(tmp_path, "src.txt", "Standard delivery: 3 days.")

    assert main(["check", out, src]) == 1
    assert "5" in capsys.readouterr().out


def test_json_flag_prints_the_report(tmp_path, capsys):
    out = write(tmp_path, "out.txt", "Delivery in 5 days.")
    src = write(tmp_path, "src.txt", "Standard delivery: 3 days.")

    main(["check", "--json", out, src])

    assert json.loads(capsys.readouterr().out)["unsupported"][0]["text"] == "5"


def test_json_source_files_are_parsed_as_structured_sources(tmp_path, capsys):
    out = write(tmp_path, "out.txt", "It weighs 2.5 kg.")
    src = write(tmp_path, "tool.json", '{"weight_kg": 2.5}')

    assert main(["check", out, src]) == 0


def test_missing_file_is_a_usage_error(tmp_path, capsys):
    assert main(["check", str(tmp_path / "nope.txt")]) == 2


def test_kinds_flag_limits_the_check(tmp_path, capsys):
    out = write(tmp_path, "out.txt", "Parcel 1Z999AA10123456784 arrives in 5 days.")
    src = write(tmp_path, "src.txt", "Tracking 1Z999AA10123456784, ETA 3 days.")

    assert main(["check", "--kinds", "identifier,phone", out, src]) == 0


def test_unknown_kind_is_a_usage_error(tmp_path, capsys):
    out = write(tmp_path, "out.txt", "Hi")

    assert main(["check", "--kinds", "names", out]) == 2


def test_a_file_that_is_not_utf8_is_a_usage_error(tmp_path, capsys):
    bad = tmp_path / "out.txt"
    bad.write_bytes(b"\xff\xfe\xfa not utf-8")

    assert main(["check", str(bad)]) == 2


def test_an_empty_kinds_list_is_a_usage_error_not_a_silent_pass(tmp_path, capsys):
    out = write(tmp_path, "out.txt", "Refund RM 99")
    assert main(["check", "--kinds", "", out]) == 2
    assert main(["check", "--kinds", ",", out]) == 2


def test_crlf_and_bom_files_keep_their_offsets(tmp_path, capsys):
    bom, crlf = tmp_path / "bom.txt", tmp_path / "crlf.txt"
    bom.write_bytes(b"\xef\xbb\xbfRefund RM 45")
    crlf.write_bytes(b"Hi\r\nRefund RM 45")
    main(["check", "--json", str(bom)])
    assert json.loads(capsys.readouterr().out)["claims"][0]["span"] == [7, 12]    # the BOM is not text
    main(["check", "--json", str(crlf)])
    assert json.loads(capsys.readouterr().out)["claims"][0]["span"] == [11, 16]   # the \r is kept, as TS keeps it


def test_a_derivation_is_printed_next_to_its_flag(tmp_path, capsys):
    out = write(tmp_path, "out.txt", "The new kettle is $101.12 and yours was $94.80, so you pay $6.32 more.")
    src = write(tmp_path, "src.json", '{"current": 94.8, "new": 101.12}')
    assert main(["check", out, src]) == 1
    assert "UNSUPPORTED money      '$6.32' at 59-64 = $101.12 − $94.80" in capsys.readouterr().out
