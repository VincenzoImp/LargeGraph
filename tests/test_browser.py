"""Real Chromium interaction with the portable report (optional browser group)."""

from pathlib import Path

import pytest

from largegraph_viz import AnalysisOptions, Resources, analyze

playwright = pytest.importorskip("playwright.sync_api")


@pytest.mark.browser
def test_report_links_views_drills_down_and_exports(tmp_path):
    assets = Path(__file__).parents[1] / "src/largegraph_viz/assets"
    analysis = analyze(
        assets / "demo_edges.csv",
        tmp_path / "run",
        options=AnalysisOptions(
            nodes_file=assets / "demo_nodes.csv", hierarchy_targets=(4, 16, 64)
        ),
        resources=Resources(memory="128MB", threads=1),
    )
    with playwright.sync_playwright() as runtime:
        try:
            browser = runtime.chromium.launch(headless=True)
        except playwright.Error as exc:
            pytest.skip(f"Install Chromium with playwright install chromium: {exc}")
        page = browser.new_page(viewport={"width": 1366, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(analysis.report.as_uri())
        page.wait_for_selector("#group-rows tr")
        assert page.locator("#level option").count() >= 2
        assert page.locator("#matrix-label").is_hidden()
        page.locator("#group-rows button").first.click()
        selected = page.locator("#group-title").inner_text()
        page.get_by_role("button", name="Matrix", exact=True).click()
        assert page.locator("#matrix-label").is_visible()
        assert page.locator("#group-title").inner_text() == selected
        page.locator("#matrix-mode").select_option("enrichment")
        page.get_by_role("button", name="Density", exact=True).click()
        assert page.locator("#group-title").inner_text() == selected
        page.locator("#drill").click()
        assert page.locator("#back").is_enabled()
        assert "Inside" in page.locator("#scope").inner_text()
        page.locator("#back").click()
        assert page.locator("#group-title").inner_text() == selected
        page.locator("#search").fill("no-such-group")
        assert page.locator("#group-rows tr").count() == 0
        page.locator("#reset").click()
        assert page.locator("#group-rows tr").count() > 0
        with page.expect_download() as event:
            page.locator("#save-png").click()
        assert event.value.suggested_filename.endswith(".png")
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(100)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert errors == []
        browser.close()
