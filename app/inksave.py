"""Ink: PDFs keep their red heading row, everything else stays black on white.

Praveen's rule: the heading row of a table stays in the company red (a plain grey looked too flat),
but titles and lines are black - no red report names, no green or blue bands. Rather than repaint
every report by hand, styles are adjusted here as they are made:

  * a large red / coloured title (SITE PETTY CASH REGISTER ...)  -> near-black
  * a coloured light fill (green total row, blue band)           -> light grey (#F4F2EF)

Solid heading rows, the palest shades (a changed line on a certificate) and thin lines are kept.
Imported once by main.py; nothing else needs to change.
"""
from reportlab.lib import colors
from reportlab.platypus import tables as _t, paragraph as _p

HEAD = colors.HexColor("#F4F2EF")
INK = colors.HexColor("#1F2328")


def _rgb(c):
    try:
        c = colors.toColor(c)
        return c.red, c.green, c.blue
    except Exception:
        return None


def _lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def _sat(c):
    mx, mn = max(c), min(c)
    return (mx - mn) / mx if mx else 0.0


def strong(c):
    """A fill that prints as a block of ink."""
    v = _rgb(c)
    return bool(v) and (_lum(v) < 0.55 or (_sat(v) > 0.3 and _lum(v) < 0.8))


def tinted(c):
    """A coloured light fill (green total row, blue band) - grey instead; the palest shades stay."""
    v = _rgb(c)
    return bool(v) and _sat(v) > 0.12 and _lum(v) < 0.92


def pale(c):
    v = _rgb(c)
    return bool(v) and _lum(v) > 0.82 and _sat(v) < 0.25


def _fix(cmd):
    if not cmd:
        return cmd
    op = str(cmd[0]).upper()
    if op == "BACKGROUND" and len(cmd) >= 4 and not isinstance(cmd[3], (list, tuple)) and tinted(cmd[3]) and not strong(cmd[3]):
        return tuple(cmd[:3]) + (HEAD,) + tuple(cmd[4:])
    if op == "ROWBACKGROUNDS" and len(cmd) >= 4 and isinstance(cmd[3], (list, tuple)):
        return tuple(cmd[:3]) + ([HEAD if (tinted(x) and not strong(x)) else x for x in cmd[3]],) + tuple(cmd[4:])
    return cmd


_orig_add = _t.Table._addCommand


def _addCommand(self, cmd):
    return _orig_add(self, _fix(cmd))


_orig_para = _p.Paragraph.__init__


def _para_init(self, text, style=None, *a, **kw):
    try:
        if style is not None:
            tc = _rgb(getattr(style, "textColor", None))
            if tc and _sat(tc) > 0.45 and (getattr(style, "fontSize", 10) or 10) >= 12:
                style = style.clone(style.name + "_ink", textColor=INK)
    except Exception:
        pass
    _orig_para(self, text, style, *a, **kw)


if not getattr(_t.Table, "_inksave", False):
    _t.Table._addCommand = _addCommand
    _t.Table._inksave = True
    _p.Paragraph.__init__ = _para_init
