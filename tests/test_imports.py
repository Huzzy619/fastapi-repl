from __future__ import annotations

import collections
import datetime
import json
import os.path

import pytest

from fastapi_repl.errors import ImportSpecError
from fastapi_repl.imports import import_spec, import_string, resolve_object


def names(spec: str) -> dict[str, object]:
    return {item.name: item.value for item in import_spec(spec)}


def test_import_module() -> None:
    assert names("import json") == {"json": json}


def test_import_dotted_binds_top_level_package() -> None:
    assert names("import os.path") == {"os": __import__("os")}


def test_import_as() -> None:
    assert names("import datetime as dt") == {"dt": datetime}


def test_from_import_multiple_and_alias() -> None:
    result = names("from collections import OrderedDict, deque as dq")
    assert result == {"OrderedDict": collections.OrderedDict, "dq": collections.deque}


def test_from_import_submodule() -> None:
    assert names("from os import path") == {"path": os.path}


def test_star_import_respects_all() -> None:
    result = names("from json import *")
    assert set(result) == set(json.__all__)


def test_multiple_statements() -> None:
    assert set(names("import json; import datetime as dt")) == {"json", "dt"}


def test_bare_module_name() -> None:
    assert names("json") == {"json": json}


def test_object_path() -> None:
    [item] = import_spec("os.path:join")
    assert item.name == "join"
    assert item.value is os.path.join
    assert item.created is False


def test_object_path_attribute_chain() -> None:
    [item] = import_spec("collections:OrderedDict.fromkeys")
    assert item.name == "fromkeys"


def test_factory_call() -> None:
    [item] = import_spec("collections:OrderedDict()")
    assert item.name == "OrderedDict"
    assert item.value == collections.OrderedDict()
    assert item.created is True


def test_relative_import_rejected() -> None:
    with pytest.raises(ImportSpecError, match="Relative imports"):
        import_spec("from . import x")


def test_non_import_statement_rejected() -> None:
    with pytest.raises(ImportSpecError):
        import_spec("x = 1")


def test_missing_module_message() -> None:
    with pytest.raises(ImportSpecError, match="No module named 'definitely_missing'"):
        import_spec("import definitely_missing")


def test_missing_attribute_message() -> None:
    with pytest.raises(ImportSpecError, match="has no attribute 'nope'"):
        import_string("json:nope")


def test_import_string_dotted_fallback() -> None:
    assert import_string("os.path.join") is os.path.join
    assert import_string("json") is json


def test_resolve_object_not_callable() -> None:
    with pytest.raises(ImportSpecError, match="not callable"):
        resolve_object("json:__name__()")


@pytest.mark.parametrize("bad", ["", "   ", "1abc", "a b c"])
def test_garbage_specs(bad: str) -> None:
    with pytest.raises(ImportSpecError):
        import_spec(bad)
