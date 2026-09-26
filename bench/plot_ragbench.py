"""Draw the README's RAGBench chart from the committed held-out result.

    uv run python bench/plot_ragbench.py   →  docs/img/ragbench-precision.svg

Precision at equal flag counts on RAGBench's ten non-numeric datasets: each checker flags as many
responses as hardfacts did, and a bar is the share of those that the GPT-4 annotator judged
unfaithful. The numbers come from bench/results/ragbench-2c41f4e.json, the pre-registered run.
The SVG follows the viewer's light or dark theme.
"""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HERE = Path(__file__).parent
RESULT = HERE / "results" / "ragbench-2c41f4e.json"
OUT = HERE.parent / "docs" / "img" / "ragbench-precision.svg"
NAMES = {"ragas_faithfulness": "RAGAS faithfulness", "gpt3_adherence": "GPT-3.5 judge",
         "trulens_groundedness": "TruLens groundedness"}


def pct(v: float) -> str:
    """Half-up to one decimal, as the docs round (0.4095 is 41.0%, not binary float's 40.9%)."""
    return str((Decimal(str(v)) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def main() -> None:
    block = json.loads(RESULT.read_text(encoding="utf-8"))["by_subset"]["other ten"]
    base = block["not_adherent"] / block["responses"]
    rows = [("hardfacts (no model calls)", block["baselines_at_equal_flags"]["ragas_faithfulness"]["hardfacts_precision_same_rows"], True)]
    rows += [(NAMES[k], v["precision"], False) for k, v in block["baselines_at_equal_flags"].items()]
    rows.sort(key=lambda r: -r[1])
    width, label_w, left, bar_h, gap, top = 640, 190, 200, 22, 12, 56
    scale_max = 0.6
    plot_w = width - left - 60
    x = lambda v: left + plot_w * v / scale_max  # noqa: E731
    height = top + len(rows) * (bar_h + gap) + 48
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
             'role="img" aria-labelledby="t d">',
             '<title id="t">Precision at equal flag counts, RAGBench (10 non-numeric datasets)</title>',
             '<desc id="d">' + "; ".join(f"{n}: {pct(v)}%" for n, v, _ in rows)
             + f"; share of unfaithful responses overall: {pct(base)}%</desc>",
             "<style>",
             ".bg{fill:#fcfcfb}.ink{fill:#1f2328}.muted{fill:#59636e}.grid{stroke:#e6e8eb}.base{stroke:#59636e}"
             ".us{fill:#2c4bb3}.them{fill:#9aa3ad}",
             "@media (prefers-color-scheme:dark){.bg{fill:#1a1a19}.ink{fill:#e6e8eb}.muted{fill:#9aa3ad}"
             ".grid{stroke:#2e3238}.base{stroke:#9aa3ad}.us{fill:#6f86e8}.them{fill:#5f6670}}",
             "text{font:13px -apple-system,Segoe UI,Helvetica,Arial,sans-serif}.h{font-weight:600;font-size:14px}",
             "</style>",
             f'<rect class="bg" width="{width}" height="{height}" rx="8"/>',
             '<text class="ink h" x="16" y="26">Of the responses each checker flags, how many are really unfaithful?</text>',
             '<text class="muted" x="16" y="44">RAGBench, 10 non-numeric datasets, same number of flags each, GPT-4 labels (pre-registered run)</text>']
    for tick in (0, 0.2, 0.4, 0.6):
        tx = x(tick)
        parts.append(f'<line class="grid" x1="{tx:.1f}" x2="{tx:.1f}" y1="{top - 4}" y2="{height - 36}"/>')
        parts.append(f'<text class="muted" x="{tx:.1f}" y="{height - 20}" text-anchor="middle">{int(tick * 100)}%</text>')
    for i, (name, value, ours) in enumerate(rows):
        y = top + i * (bar_h + gap)
        parts.append(f'<text class="ink" x="{label_w}" y="{y + 16}" text-anchor="end"'
                     f'{" font-weight=\"600\"" if ours else ""}>{name}</text>')
        w = x(value) - left
        parts.append(f'<path class="{"us" if ours else "them"}" d="M{left},{y} h{w - 4:.1f} q4,0 4,4 v{bar_h - 8} '
                     f'q0,4 -4,4 h{-(w - 4):.1f} z"/>')
        parts.append(f'<text class="ink" x="{x(value) + 6:.1f}" y="{y + 16}">{pct(value)}%</text>')
    bx = x(base)
    parts.append(f'<line class="base" x1="{bx:.1f}" x2="{bx:.1f}" y1="{top - 8}" y2="{height - 36}" stroke-dasharray="3 3"/>')
    parts.append(f'<text class="muted" x="{bx + 4:.1f}" y="{height - 38}">{base * 100:.0f}% of all responses are unfaithful</text>')
    parts.append("</svg>")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
