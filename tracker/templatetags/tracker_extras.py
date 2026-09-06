import math

from django import template

register = template.Library()

# Matches the site theme's status colors (style.css --good/--warn/--bad) so
# gauges, pills, and buttons all read as one consistent palette.
GOOD = "#4F7A62"
WARNING = "#E6A65D"
CRITICAL = "#C1584A"

_CX, _CY, _R = 60, 58, 46
_VIEWBOX = "0 0 120 80"
_START_DEG, _END_DEG = 180, 0  # sweep left-to-top-to-right
_MARKER_INNER, _MARKER_OUTER = _R - 8, _R + 8
_NUMBER_Y = _CY + 16


def _point(angle_deg, radius=_R):
    angle_rad = math.radians(angle_deg)
    return _CX + radius * math.cos(angle_rad), _CY - radius * math.sin(angle_rad)


def _arc_path(start_deg, end_deg, radius=_R):
    """Arc from start_deg to end_deg (math convention: 180=left, 90=top, 0=right).

    Sweeping left->top->right is clockwise on-screen, which is SVG's
    sweep-flag=1 (SVG's y-axis points down, flipping the usual math sense).
    """
    x1, y1 = _point(start_deg, radius)
    x2, y2 = _point(end_deg, radius)
    large_arc = 1 if abs(start_deg - end_deg) > 180 else 0
    return f"M {x1:.2f} {y1:.2f} A {radius} {radius} 0 {large_arc} 1 {x2:.2f} {y2:.2f}"


def _band(value):
    if value >= 65:
        return GOOD, "Ahead of pace"
    if value >= 40:
        return WARNING, "On pace"
    return CRITICAL, "Behind pace"


@register.inclusion_tag("tracker/_gauge.html")
def gauge(value, expected=None, size="md", label=None):
    """Semicircle meter: value 0-100 fills the arc; an optional `expected`
    marker (0-100, e.g. time elapsed) shows where the value should be.
    """
    value = max(0, min(100, round(value or 0)))
    value_deg = _START_DEG - (_START_DEG - _END_DEG) * (value / 100)
    color, status_label = _band(value)

    marker = None
    if expected is not None:
        expected = max(0, min(100, round(expected)))
        marker_deg = _START_DEG - (_START_DEG - _END_DEG) * (expected / 100)
        mx1, my1 = _point(marker_deg, _MARKER_INNER)
        mx2, my2 = _point(marker_deg, _MARKER_OUTER)
        marker = {"x1": f"{mx1:.2f}", "y1": f"{my1:.2f}", "x2": f"{mx2:.2f}", "y2": f"{my2:.2f}"}

    return {
        "viewbox": _VIEWBOX,
        "cx": _CX, "cy": _CY, "r": _R, "number_y": _NUMBER_Y,
        "track_path": _arc_path(_START_DEG, _END_DEG),
        "value_path": _arc_path(_START_DEG, value_deg) if value > 0 else "",
        "marker": marker,
        "value": value,
        "color": color,
        "status_label": status_label,
        "size": size,
        "label": label,
    }


@register.filter
def status_label(status_value):
    return {
        "not_started": "Not Started",
        "in_progress": "In Progress",
        "completed": "Completed",
        "abandoned": "Abandoned",
    }.get(status_value, status_value)
