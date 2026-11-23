"""Escritura de automatización Touch / Latch / Write con un motor y un reloj falsos."""
from allforone.automation_write import GLIDE, AutoWriter, value_at


class FakeEngine:
    def __init__(self):
        self.curves = {}

    def effect_info(self, eid):
        return {"track_id": 1}

    def effect_automation(self, eid, p):
        return self.curves.get(("fx", eid, p), [])

    def set_effect_automation(self, eid, p, pts):
        self.curves[("fx", eid, p)] = list(pts)
        return True

    def track_automation(self, tid, p):
        return self.curves.get(("track", tid, p), [])

    def set_track_automation(self, tid, p, pts):
        self.curves[("track", tid, p)] = list(pts)
        return True


def make():
    clock = {"t": 0.0}
    eng = FakeEngine()
    w = AutoWriter(eng, now=lambda: clock["t"], playing=lambda: True)
    return eng, w, clock


def test_read_no_escribe():
    eng, w, clock = make()
    assert not w.touch(("track", 1, "volume"), -3.0, "start")
    assert eng.curves == {}


def test_touch_vuelve_a_la_curva():
    eng, w, clock = make()
    tgt = ("track", 1, "volume")
    eng.curves[tgt] = [(0.0, -10.0), (10.0, -10.0)]
    w.set_mode(1, "touch")
    clock["t"] = 2.0
    assert w.touch(tgt, -4.0, "start")
    clock["t"] = 3.0
    w.touch(tgt, -2.0, "move")
    clock["t"] = 4.0
    w.touch(tgt, -2.0, "end")
    c = eng.curves[tgt]
    assert abs(value_at(c, 3.0, 0) + 2.0) < 1e-6
    assert abs(value_at(c, 4.0 + GLIDE + 0.1, 0) + 10.0) < 1e-6
    assert not w.writing


def test_latch_sigue_hasta_parar_y_write_pasa_a_touch():
    eng, w, clock = make()
    tgt = ("fx", 7, "gain")
    w.set_mode(1, "write")
    clock["t"] = 1.0
    w.touch(tgt, 0.5, "start")
    clock["t"] = 1.5
    w.touch(tgt, 0.8, "end")
    assert w.writing
    w.finish(stop_at=6.0)
    c = eng.curves[tgt]
    assert abs(value_at(c, 5.9, 0) - 0.8) < 1e-6
    assert w.mode(1) == "touch"
