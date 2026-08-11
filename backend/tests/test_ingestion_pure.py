"""
Unit tests for the pure helper functions in the ingestion service (no DB).
"""
from app.services.ingestion import _find_keyword, _severity_from_drop


def test_find_keyword_matches_lane_closed():
    assert _find_keyword("Lane closed near 3rd Ave for utility work") == "lane_closed"


def test_find_keyword_matches_road_closed():
    assert _find_keyword("ROAD CLOSED due to flooding") == "road_closed"


def test_find_keyword_matches_detour():
    assert _find_keyword("Detour in place due to event staging") == "detour"


def test_find_keyword_returns_none_when_no_match():
    assert _find_keyword("Routine street sweeping this week") is None


def test_severity_from_drop_thresholds():
    assert _severity_from_drop(0.10) == 1
    assert _severity_from_drop(0.25) == 2
    assert _severity_from_drop(0.40) == 3
    assert _severity_from_drop(0.55) == 4
    assert _severity_from_drop(0.70) == 5
    assert _severity_from_drop(0.99) == 5
