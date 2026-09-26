# hardfacts in CI

Two ways to stop a prompt or model change that makes your bot start inventing values: gate a batch of recorded conversations, or assert inside the eval tests you already have.

## Gate recorded conversations

Record what your bot said and what it was given, one JSON object per line:

```json
{"id": "ticket-4812/turn-3", "output": "Your parcel EN123456789MY arrives 3 October.", "sources": [{"tracking": "EN123456789MY", "eta": "2026-10-03"}]}
```

Then fail the build when too many replies state a value no source contains:

```yaml
# .github/workflows/hardfacts.yml
name: hardfacts
on: [pull_request]
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10.2.0
      - run: uv tool install "git+https://github.com/seekerPrice/hardfacts"
      - run: hardfacts report evals/transcripts.jsonl --html hardfacts.html --fail-over 0.02
      - uses: actions/upload-artifact@v7
        if: always()
        with:
          name: hardfacts-report
          path: hardfacts.html
```

`--fail-over 0.02` exits 1 when more than 2% of replies have an Unsupported Claim. `--kinds identifier,money,date,phone` limits the gate to the Kinds that cost you money when wrong. The HTML report shows the worst replies in context, with the working for any value the bot calculated ([sample](../examples/sample-report/support-agents.html)).

Pick the threshold from your own data. Run the report once on a known-good set and set the gate just above what it shows. Values a bot legitimately calculates are flagged too, with their working. So a bot whose job is arithmetic needs either a higher threshold or a gate on `report.unexplained` (below).

## Assert in eval tests

```python
from hardfacts import check, feedback


def test_order_status_reply_states_only_order_facts(bot, order):
    reply = bot.answer("Where is my order?", tools={"order": order})
    report = check(reply, [order])
    assert not report.unexplained, feedback(report)  # arithmetic on the reply's own values is allowed
```

`report.ok` is stricter: it also fails on correct arithmetic, such as a refund difference. `feedback(report)` names each unsupported value, which makes the failure message readable.
