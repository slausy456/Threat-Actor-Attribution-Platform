from datetime import date, datetime

from dashboard.client import (
    TIER_COLORS,
    TIER_TEXT_COLOR,
    format_confidence,
    tier_badge_style,
    timeline_filter_bounds,
)


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(first: str, second: str) -> float:
    lighter, darker = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_tier_badges_have_words_and_high_contrast_distinct_colors():
    assert len(set(TIER_COLORS.values())) == 3
    for tier, background in TIER_COLORS.items():
        style = tier_badge_style(tier)
        assert f"background-color: {background}" in style
        assert "color: #ffffff" in style
        assert _contrast_ratio(TIER_TEXT_COLOR, background) >= 4.5


def test_dashboard_confidence_uses_three_decimals():
    assert format_confidence(0.7) == "0.700"


def test_single_date_selection_disables_timeline_filter():
    assert timeline_filter_bounds((date(2024, 10, 1),)) == (None, None)


def test_two_date_selection_creates_inclusive_timeline_bounds():
    since, until = timeline_filter_bounds((date(2024, 10, 1), date(2024, 10, 31)))
    assert since == datetime(2024, 10, 1, 0, 0)
    assert until == datetime(2024, 10, 31, 23, 59, 59)
