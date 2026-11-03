"""Capture screenshots of each demo page (needs Playwright + a Chrome/Chromium install)."""
from pathlib import Path
from playwright.sync_api import sync_playwright
from common.report import OUTPUT, ROOT

PAGES = {"invoice_reader": OUTPUT / "invoice_reader" / "invoice_reader.html",
         "project_control": OUTPUT / "project_control.html", "plant_allocation": OUTPUT / "plant_allocation.html"}


def main() -> None:
    out = ROOT / "screenshots"
    out.mkdir(exist_ok=True)
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:
            browser = p.chromium.launch(executable_path="/usr/bin/google-chrome")
        pg = browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
        for name, path in PAGES.items():
            pg.goto(path.as_uri())
            pg.screenshot(path=str(out / f"{name}_full.png"), full_page=True)
            pg.screenshot(path=str(out / f"{name}_top.png"))
        browser.close()
    print("Screenshots written to", out)


if __name__ == "__main__":
    main()
