"""F1: registro único de órdenes (menús, clic derecho y paleta Ctrl+K salen de aquí)."""
from allforone import actions


def test_registro_de_ordenes():
    acts = actions.actions()
    ids = [a["id"] for a in acts]
    assert len(ids) == len(set(ids)), "ids repetidos"
    assert {a["menu"] for a in acts} == set(actions.MENUS)
    for a in acts:
        assert a["label"] and a["tip"], a["id"]
        assert a["id"].split(".")[0] in ("file", "edit", "track", "clip", "mix", "view", "script"), a["id"]
    # un atajo no se repite entre órdenes distintas (salvo la misma orden en Editar y en Clip)
    seen = {}
    for a in acts:
        if a["keys"]:
            seen.setdefault(a["keys"], set()).add(a["label"])
    assert all(len(v) == 1 for v in seen.values()), seen
    # el clic derecho y la marca IA solo nombran órdenes que existen
    assert set(actions.CTX_CLIP) | set(actions.CTX_TRACK) | actions.AI | set(actions.CONFIRM) <= set(ids)
    assert all(a["ai"] for a in acts if a["id"] in ("clip.repaint", "clip.cover", "mix.auto"))
    # lo que borra pide confirmación en el sitio
    assert {"track.remove", "clip.delete"} <= set(actions.CONFIRM)


def test_puente_devuelve_el_registro():
    import json
    import pytest
    pytest.importorskip("PySide6")
    from allforone.bridge import Bridge
    r = json.loads(Bridge.actionList(Bridge.__new__(Bridge)))
    assert r["ok"] and r["menus"] == list(actions.MENUS) and len(r["actions"]) == len(actions.actions())
