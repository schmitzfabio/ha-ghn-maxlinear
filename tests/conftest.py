"""Lädt parser.py direkt als Modul.

custom_components/ghn_maxlinear/__init__.py importiert Home Assistant; über
den Paketpfad wäre der Parser also nur mit kompletter HA-Installation
testbar. parser.py hat bewusst keine Abhängigkeiten ausser der Stdlib und
lässt sich deshalb einzeln laden.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PARSER_PATH = _ROOT / "custom_components" / "ghn_maxlinear" / "parser.py"
_FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"


def _load_parser():
    spec = importlib.util.spec_from_file_location("ghn_parser", _PARSER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["ghn_parser"] = module
    spec.loader.exec_module(module)
    return module


parser = _load_parser()


@pytest.fixture(name="parser")
def parser_fixture():
    return parser


@pytest.fixture(name="load_fixture")
def load_fixture_fixture():
    def _load(name: str) -> str:
        return (_FIXTURES / name).read_text(encoding="utf-8")

    return _load
