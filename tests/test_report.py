import json

from hardfacts import check


def test_report_is_ok_only_when_every_claim_is_supported():
    assert check("We open at 9.", ["Opening time: 9"]).ok
    assert not check("We open at 10.", ["Opening time: 9"]).ok


def test_report_serialises_to_plain_json():
    report = check("Call back in 2 days, ref 77.", ["Ticket 77 opened."])

    data = json.loads(json.dumps(report.to_dict()))

    assert data["ok"] is False
    assert data["unsupported"] == [{"kind": "quantity", "text": "2", "span": [13, 14], "value": "2", "derivation": None}]
    assert data["claims"][1]["evidence"] == [{"source": 0, "span": [7, 9], "text": "77"}]
