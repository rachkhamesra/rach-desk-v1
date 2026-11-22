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
