"""Tests für das Parsen der MaxLinear-GUI-Seiten."""

from __future__ import annotations

import pytest


def test_parse_status_full_page(parser, load_fixture):
    data = parser.parse_status(load_fixture("ghn.html"))

    assert data["mac"] == "aa:bb:cc:00:11:22"
    assert data["node_type"] == "DOMAIN_MASTER"
    assert data["domain"] == "HOMEDOMAIN"
    assert data["domain_id"] == "7"
    assert data["secured"] is True
    assert data["speed_mbps"] == 1024
    assert data["cpu_pct"] == 12


def test_peers_skip_null_and_own_mac(parser, load_fixture):
    """Index 0 ist immer die Null-MAC, Index 1 ist der Adapter selbst."""
    data = parser.parse_status(load_fixture("ghn.html"))

    assert data["peer_count"] == 2
    assert [p["mac"] for p in data["peers"]] == [
        "dd:ee:ff:00:11:33",
        "dd:ee:ff:00:11:44",
    ]


def test_rates_use_gui_formula(parser, load_fixture):
    """Mbit/s = floor(roh * 32 / 1000), wie im GUI-JavaScript."""
    data = parser.parse_status(load_fixture("ghn.html"))

    assert data["peers"][0] == {
        "mac": "dd:ee:ff:00:11:33",
        "tx_mbps": 160,
        "rx_mbps": 192,
    }
    assert data["peers"][1] == {
        "mac": "dd:ee:ff:00:11:44",
        "tx_mbps": 288,
        "rx_mbps": 96,
    }
    # Schwächste Richtung über alle Peers.
    assert data["min_rate_mbps"] == 96


def test_profile_resolved_via_mode_index(parser, load_fixture):
    """sPhyMode zeigt über das mode-Array in das parallele profiles-Array."""
    data = parser.parse_status(load_fixture("ghn.html"))

    assert data["profile"] == "MIMO 200 MHz"


def test_memory_percentage(parser, load_fixture):
    data = parser.parse_status(load_fixture("ghn.html"))

    assert data["mem_free_kb"] == 20000
    assert data["mem_total_kb"] == 65536
    assert data["mem_used_pct"] == 69


def test_memory_percentage_clamped_when_free_exceeds_total(parser):
    """Das Gerät meldet gelegentlich free > total."""
    page = (
        'var pcmastr = "00:00:00:00:00:00";'
        '<span id="system_stats_free_memory"> 70000 </span>'
        '<span id="system_stats_total_memory"> 65536 </span>'
    )

    assert parser.parse_status(page)["mem_used_pct"] == 0


def test_parse_status_tolerates_empty_page(parser):
    """Fehlende Werte werden None, der Aufruf darf nicht scheitern."""
    data = parser.parse_status("")

    assert data["mac"] == ""
    assert data["peers"] == []
    assert data["peer_count"] == 0
    assert data["min_rate_mbps"] is None
    assert data["mem_used_pct"] is None
    assert data["profile"] is None


def test_empty_js_array_is_not_a_single_empty_string(parser):
    """'new Array()' muss [] ergeben, nicht ['']."""
    page = (
        'var sPhyMode = "1";'
        "var mode = new Array();"
        "var profiles = new Array();"
    )

    assert parser.parse_status(page)["profile"] is None


def test_parse_device(parser, load_fixture):
    data = parser.parse_device(load_fixture("device.html"))

    assert data["fw_version"] == "v1.2.3"
    assert data["hw_version"] == "RevB"
    assert data["uptime_seconds"] == 135213


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1 days, 13h 33m 33s", 135213),
        ("2 days, 0h 0m 1s", 172801),
        ("0h 0m 42s", 42),
        ("12h 30m 0s", 45000),
        ("unbekannt", None),
        (None, None),
    ],
)
def test_parse_uptime_seconds(parser, text, expected):
    assert parser.parse_uptime_seconds(text) == expected


def test_login_page_detection(parser, load_fixture):
    assert parser.is_login_page(load_fixture("login.html")) is True
    assert parser.is_login_page(load_fixture("ghn.html")) is False
    assert parser.looks_like_status_page(load_fixture("ghn.html")) is True
    assert parser.looks_like_status_page(load_fixture("login.html")) is False


def test_csrf_token(parser, load_fixture):
    assert parser.parse_csrf_token(load_fixture("login.html")) == "tok-42"
    assert parser.parse_csrf_token("<html></html>") == ""
