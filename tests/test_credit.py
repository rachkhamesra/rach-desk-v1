import json, re
import credit, webpage


def test_documents_are_self_contained_and_dark():
    for key, _, _ in credit.DASHBOARDS:
        d = credit.document(key)
        assert d and "cdnjs.cloudflare.com" not in d
        assert "color-scheme:dark" in d and "creditFrame:id" in d and "new Chart" in d
        assert d.count("<script") == d.count("</script>")                      # the vendored library did not break the markup


def test_no_external_requests_remain():
    for key, _, _ in credit.DASHBOARDS:
        d = credit.document(key)
        assert not re.search(r'<script[^>]+src=|<link[^>]+href=|@import', d)


def test_tab_holds_one_lazy_frame_per_dashboard_and_the_json_round_trips():
    html = webpage.tab_credit({})
    assert html.count('<iframe class="creditframe"') == 2 and 'sandbox="allow-scripts"' in html and "srcdoc" not in html       # filled in by script on first view
    for key, _, _ in credit.DASHBOARDS:
        raw = re.search(rf'<script type="application/json" id="credit-doc-{key}">(.*?)</script>', html, re.S).group(1)
        assert json.loads(raw.replace("<\\/", "</")) == credit.document(key)           # what the browser's JSON.parse will see
    assert "static snapshots" in html and "BANKS" in html and "NBFCS" in html


def test_missing_or_changed_dashboard_files_do_not_break_the_page(tmp_path, monkeypatch):
    monkeypatch.setattr(credit, "ROOT", str(tmp_path))
    assert credit.document("banks") is None
    assert "not available in this build" in webpage.tab_credit({})
    (tmp_path / "config" / "dashboards").mkdir(parents=True); (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "chart.umd.min.js").write_text("window.Chart=function(){}")
    (tmp_path / "config" / "dashboards" / "banks.html").write_text("<html><body>no cdn tag here</body></html>")
    assert credit.document("banks") is None                                    # a file that no longer looks like the delivered dashboard is left out
