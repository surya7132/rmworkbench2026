"""One shared Jinja environment plus the small helpers templates need."""
import jinja2
from fastapi.templating import Jinja2Templates

from . import clock, config

# Shared pages (base.html, _macros.html) live in app/templates. Each feature keeps its own pages next to its code,
# so a page is named by its feature folder, for example "alerts/index.html".
templates = Jinja2Templates(directory=str(config.ROOT / "app" / "templates"))
templates.env.loader = jinja2.FileSystemLoader([str(config.ROOT / "app" / "templates"), str(config.ROOT / "app" / "features")])


def cr(x):
    if x is None:
        return "–"
    return f"₹{x:,.0f} cr" if x >= 100 else f"₹{x:,.1f} cr"


def ddmmm(s):
    d = clock.parse(s)
    return d.strftime("%d %b %Y") if d else "–"


templates.env.filters["cr"] = cr
templates.env.filters["ddmmm"] = ddmmm
templates.env.globals["demo_now"] = lambda: clock.now().strftime("%a %d %b %Y, %H:%M")
