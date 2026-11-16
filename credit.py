"""The Credit Desk tab: the Banks and NBFC sector dashboards, embedded as they were delivered.

Each dashboard in config/dashboards/ is a self-contained page (its own data, tabs and charts) that originally loaded Chart.js from a CDN.
To keep the site free of external requests the CDN tag is swapped for the vendored copy (vendor/chart.umd.min.js, Chart.js 4.4.1, MIT).
The site is always dark, so the dashboards' own dark palette is forced, and a small script reports the page height to the parent so the
frame grows to fit instead of scrolling inside itself. To update a dashboard, replace its file in config/dashboards/.
"""
import os, re

ROOT = os.path.dirname(os.path.abspath(__file__))
DASHBOARDS = [("banks", "BANKS", "Six mid-size private banks"), ("nbfc", "NBFCS", "Six NBFCs")]
CDN = re.compile(r'<script src="https://cdnjs\.cloudflare\.com/ajax/libs/Chart\.js/[^"]+"></script>')
DARK = ("<style>:root{--bg:#0a0a0a;--card:#141414;--ink:#ecebe4;--mute:#9a998f;--line:#2b2b27;--pos:#58c585;--neg:#ef7b6e;color-scheme:dark}"
        "body{background:var(--bg)}.wrap{padding-top:8px}.top>*,.two>*,.grid2>*,.trio>*,.row5>*{min-width:0}.card{min-width:0;max-width:100%}</style>")
REPORT = ("<script>(function(){var id=%s,last=0;function send(){var h=Math.ceil(document.documentElement.scrollHeight);if(h&&h!==last){last=h;parent.postMessage({creditFrame:id,height:h},'*')}}"
          "if(window.ResizeObserver)new ResizeObserver(send).observe(document.body);window.addEventListener('load',send);setInterval(send,1500)})()</script>")


def _read(path):
    try:
        with open(path, encoding="utf-8") as f: return f.read()
    except OSError:
        return None


def document(key):
    """The full HTML for one dashboard, ready to be an iframe's srcdoc, or None when the file is missing or no longer looks like a dashboard."""
    page = _read(os.path.join(ROOT, "config", "dashboards", f"{key}.html")); chart = _read(os.path.join(ROOT, "vendor", "chart.umd.min.js"))
    if not page or not chart or "</body>" not in page or not CDN.search(page): return None
    page = CDN.sub(lambda _: "<script>" + chart.replace("</script", "<\\/script") + "</script>", page, count=1)
    page = page.replace("</style></head>", "</style>" + DARK + "</head>", 1)
    return page.replace("</body>", REPORT % ('"%s"' % key) + "</body>", 1)
