from pricewatch.analyzer import analyze
from pricewatch.models import Item
from pricewatch.reporter import generate_report, template_summary, verify
from pricewatch.storage import Database


def make_db():
    db = Database(":memory:")
    def it(name, price):
        return Item("TiendaX", name, f"https://x.test/{name}", price, "USD")
    for day, a, b, c in [("2026-11-18", 1000, 500, 300), ("2026-11-19", 1000, 500, 300),
                         ("2026-11-20", 1000, 500, 300)]:
        db.save([it("A", a), it("B", b), it("C", c)], day)
    # hoy: A baja 20%, B sube 10%, C igual, D es nuevo
    db.save([it("A", 800), it("B", 550), it("C", 300), it("D", 700)], "2026-11-21")
    return db


def test_analyze_detects_drop_rise_new():
    f = analyze(make_db(), "2026-11-21")
    assert f["products_tracked"] == 4
    assert f["new_products"] == 1
    assert f["drops_total"] == 1 and f["rises_total"] == 1
    d = f["top_drops"][0]
    assert d["name"] == "A" and d["change_pct"] == -20.0 and d["saving_amount"] == 200.0
    assert d["lowest_in_window"] is True


def test_verify_accepts_supported_and_rejects_invented_numbers():
    f = analyze(make_db(), "2026-11-21")
    ok = "El producto A bajó de USD 1,000.00 a USD 800.00, un -20.0% (ahorro de 200.00)."
    assert verify(ok, f) == []
    bad = "El producto A bajó 20.0% y ahora cuesta USD 799.00."
    assert verify(bad, f) == [799.0]


class FakeClient:
    def __init__(self, texts):
        self.texts, self.calls = list(texts), 0
        self.messages = self

    def create(self, **kw):
        self.calls += 1
        txt = self.texts.pop(0)
        block = type("B", (), {"type": "text", "text": txt})()
        return type("M", (), {"content": [block]})()


def test_report_uses_llm_when_verified():
    f = analyze(make_db(), "2026-11-21")
    c = FakeClient(["Hoy bajó A de USD 1,000.00 a USD 800.00 (-20.0%)."])
    rep = generate_report(f, client=c)
    assert rep.source == "llm" and rep.rejected == 0


def test_report_rejects_hallucination_then_falls_back_to_template():
    f = analyze(make_db(), "2026-11-21")
    c = FakeClient(["A cuesta USD 777.00 hoy.", "A cuesta USD 888.00 hoy."])
    rep = generate_report(f, client=c)
    assert rep.source == "template" and rep.rejected == 2 and c.calls == 2
    assert "777" not in rep.markdown and "888" not in rep.markdown
    assert template_summary(f) in rep.markdown


def test_report_retries_once_and_accepts_second_attempt():
    f = analyze(make_db(), "2026-11-21")
    c = FakeClient(["A cuesta USD 777.00.", "A bajó a USD 800.00."])
    rep = generate_report(f, client=c)
    assert rep.source == "llm" and rep.rejected == 1


def test_no_api_key_uses_template(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rep = generate_report(analyze(make_db(), "2026-11-21"))
    assert rep.source == "template"
