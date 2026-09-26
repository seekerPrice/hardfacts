"""Properties every Report must have, whatever text goes in."""

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from hardfacts import check

# Text that is dense in the characters hardfacts cares about, plus arbitrary Unicode.
alphabet = st.sampled_from(list("0123456789 .,:-/$%°#@()+RMkKaApPmMCFx年月日元万亿三十百千") + ["\n", "twenty", "one ", "May ", "Jan "])
dense = st.lists(alphabet, max_size=80).map("".join)
texts = st.one_of(dense, st.text(max_size=200))


@settings(max_examples=400, deadline=None)
@given(output=texts, source=texts)
def test_spans_always_quote_the_text_they_point_at(output, source):
    report = check(output, [source])

    for claim in report.claims:
        assert output[claim.span[0]:claim.span[1]] == claim.text
        for e in claim.evidence:
            assert report.sources[e.source][e.span[0]:e.span[1]] == e.text


@settings(max_examples=300, deadline=None)
@given(output=texts, source=texts)
def test_reports_always_serialise(output, source):
    json.dumps(check(output, [source]).to_dict())


@settings(max_examples=300, deadline=None)
@given(output=texts)
def test_an_output_always_supports_itself(output):
    report = check(output, [output])

    assert report.ok, [c.text for c in report.unsupported]


@settings(max_examples=200, deadline=None)
@given(output=texts, source=texts)
def test_the_same_input_gives_the_same_report(output, source):
    assert check(output, [source]).to_dict() == check(output, [source]).to_dict()
