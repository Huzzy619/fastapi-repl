from __future__ import annotations

import pytest

from fastapi_repl.adapters.base import ModelInfo
from fastapi_repl.errors import CollisionError
from fastapi_repl.namespace import Namespace, is_excluded


def make_model(name: str, module: str, label: str = "") -> ModelInfo:
    cls = type(name, (), {"__module__": module})
    return ModelInfo.from_class(cls, "test", label=label)


def test_later_layers_override() -> None:
    ns = Namespace()
    ns.add("x", 1, group="pre_imports", source="a")
    ns.add("x", 2, group="imports", source="b")
    assert ns.to_dict() == {"x": 2}
    assert ns.entries["x"].group == "imports"


def test_prefix_collision() -> None:
    ns = Namespace(collision="prefix")
    a = make_model("Tag", "app.models.blog")
    b = make_model("Tag", "app.models.legacy")
    ns.add_model(a)
    ns.add_model(b)
    assert ns.to_dict() == {"Tag": a.cls, "legacy_Tag": b.cls}
    assert ns.notes


def test_prefix_uses_label() -> None:
    ns = Namespace(collision="prefix")
    ns.add_model(make_model("User", "a.models", label="auth"))
    ns.add_model(make_model("User", "b.models", label="crm"))
    assert set(ns.to_dict()) == {"User", "crm_User"}


def test_skip_collision() -> None:
    ns = Namespace(collision="skip")
    a = make_model("Tag", "x")
    ns.add_model(a)
    ns.add_model(make_model("Tag", "y"))
    assert ns.to_dict() == {"Tag": a.cls}


def test_override_collision() -> None:
    ns = Namespace(collision="override")
    ns.add_model(make_model("Tag", "x"))
    b = make_model("Tag", "y")
    ns.add_model(b)
    assert ns.to_dict() == {"Tag": b.cls}


def test_error_collision() -> None:
    ns = Namespace(collision="error")
    ns.add_model(make_model("Tag", "x"))
    with pytest.raises(CollisionError, match="model_aliases"):
        ns.add_model(make_model("Tag", "y"))


def test_aliases_by_name_and_path() -> None:
    ns = Namespace(model_aliases={"User": "AuthUser", "crm.models.Account": "CrmAccount"})
    ns.add_model(make_model("User", "auth.models"))
    ns.add_model(make_model("Account", "crm.models"))
    assert set(ns.to_dict()) == {"AuthUser", "CrmAccount"}


def test_same_class_twice_is_not_a_collision() -> None:
    ns = Namespace(collision="error")
    model = make_model("Tag", "x")
    ns.add_model(model)
    ns.add_model(model)
    assert list(ns.to_dict()) == ["Tag"]


def test_models_override_non_model_names() -> None:
    ns = Namespace(collision="error")
    ns.add("Tag", "something", group="pre_imports", source="x")
    model = make_model("Tag", "x")
    ns.add_model(model)
    assert ns.to_dict()["Tag"] is model.cls


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("AuditLog", True),
        ("app.models.audit.AuditLog", True),
        ("app.models.audit", True),
        ("app.models", True),
        ("app.mod", False),
        ("Audit*", True),
        ("*.audit.*", True),
        ("User", False),
        ("audit_app", True),
    ],
)
def test_dont_load_patterns(pattern: str, expected: bool) -> None:
    model = make_model("AuditLog", "app.models.audit", label="audit_app")
    assert is_excluded(model, [pattern]) is expected


def test_groups_are_ordered() -> None:
    ns = Namespace()
    ns.add("b", 1, group="imports", source="")
    ns.add("a", 1, group="models", source="")
    ns.add("c", 1, group="custom", source="")
    assert list(ns.by_group()) == ["models", "imports", "custom"]


def test_created_values() -> None:
    ns = Namespace()
    ns.add("a", 1, group="objects", source="", created=True)
    ns.add("b", 2, group="objects", source="")
    assert ns.created_values() == [1]
