import re
import webpage


def undo(text):
    """What the page's ensurePanel does to the inert text before inserting it."""
    return text.replace("<\\/script", "</script").replace("<\\!--", "<!--")


def test_a_lazy_panel_round_trips_even_with_script_and_comment_markup_in_it():
    html = '<div>a</div><script>var x = "</script>";</script><!-- c --><script type="application/json">{"k":"<!--"}</script>'
    out = webpage.lazy_panel("patterns", html)
    assert out.startswith('<script type="text/plain" id="lazy-patterns">') and out.endswith("</script>")
    inner = out[len('<script type="text/plain" id="lazy-patterns">'):-len("</script>")]
    assert "</script" not in inner and "<!--" not in inner                                   # nothing in it can end the element or open a comment
    assert undo(inner) == html                                                                 # and it comes back exactly


def test_the_page_script_scopes_its_click_handlers_to_a_panel_and_loads_lazily():
    js = webpage.JS
    for fn in ("function bindPanel(R)", "function ensurePanel(k)", "function ensureStock(k)", "bindPanel(document)", "ensurePanel(b.dataset.t)"): assert fn in js, fn
    for cls in ("ptchip", "ptfbtn", "basetab", "h52tab", "h52cap", "urchip", "exswitchbtn", "exwd", "exrbtn", "subtab"):
        assert f"document.querySelectorAll('.{cls}')" not in js, cls                          # no handler for panel content is bound to the whole document any more
        assert f"R.querySelectorAll('.{cls}')" in js, cls
    assert "renderUpcoming();renderHeat()" not in js                                           # the calls panel is filled when it is first opened
    assert "last=m.last" in js and "[...S.c].reverse()" not in js                              # the watchlist does not need the price arrays
    assert js.count("ensureStock(cur)") == 2                                                   # both chart paths load the stock first
    assert "ALL.forEach(k=>{const S=D.stocks[k],n=S.c.length" not in js                       # no start-up pass over every stock's arrays


def test_unescape_in_the_page_matches_the_escape_in_the_server():
    m = re.search(r"p\.innerHTML=t\.textContent\.replace\((/.*?/g),'</script'\)\.replace\((/.*?/g),'<!--'\)", webpage.JS)
    assert m and m.group(1) == r"/<\\\/script/g" and m.group(2) == r"/<\\!--/g"             # the two patterns the browser uses to undo lazy_panel


def test_the_today_tab_is_first_and_links_through_to_its_sources():
    import inspect
    src = inspect.getsource(webpage.render)
    assert src.index('("today", "TODAY"') < src.index('("stocks", "STOCKS"')                 # the first tab is the one the page opens on
    assert "today-wl" in webpage.JS and "a[data-go]" in webpage.JS and "renderToday" in webpage.JS                              # the watchlist box is filled by the page; each card opens its full tab


def test_earlier_touches_get_a_whole_history_strip_only_when_some_fall_before_the_chart():
    ch = dict(full=[100.0 + (i % 7) for i in range(300)], full_first="01 Jan 24", off=150, dates=["01 Nov 26"] * 150)
    lines = [dict(a=[30, 105.0], b=[149, 105.0], role="support"), dict(a=[30, 120.0], b=[149, 108.0], role="resistance")]
    n, html = webpage.earlier_touches(ch, dict(lines=lines, touches=[[-100, 105.0], [-40, 105.0], [35, 105.0], [140, 106.0]]), start=20)
    assert n == 2 and "2 before it" in html and "4 touches in all" in html                 # two touches lie before the drawn part (negative = before the bars the chart carries)
    n, html = webpage.earlier_touches(ch, dict(lines=lines, touches=[[35, 105.0], [140, 106.0]]), start=20)
    assert n == 0 and html == ""
