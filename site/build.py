"""Assemble the self-contained demo page: template + browser bundle + presets.

    (cd ts && npm run bundle) && uv run python site/build.py   →  site/dist/hardfacts.html
"""

from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent

page = (HERE / "demo.template.html").read_text(encoding="utf-8")
bundle = (ROOT / "ts" / "dist" / "hardfacts.browser.js").read_text(encoding="utf-8")
presets = (HERE / "presets.json").read_text(encoding="utf-8")
page = page.replace("/*HARDFACTS_BUNDLE*/", bundle.replace("</script", "<\\/script")).replace("/*PRESETS*/", presets.strip())
(HERE / "dist").mkdir(exist_ok=True)
(HERE / "dist" / "hardfacts.html").write_text(page, encoding="utf-8")
print(f"site/dist/hardfacts.html ({len(page) // 1024} KB)")
