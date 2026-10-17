import storepulse as sp


def test_explains_planted_drop():
    e = sp.explain(sp.load_orders(sp.make_sample()))
    assert e["delta"] < 0
    assert e["products"].index[0] == "Alpha Mug"
    assert abs(e["orders_effect"] + e["aov_effect"] - e["delta"]) < 1e-6
    text = sp.write_email(e, "Demo")
    assert "Alpha Mug" in text and "down" in text


def test_rejects_wrong_file():
    import pandas as pd, pytest
    with pytest.raises(ValueError):
        sp.load_orders(pd.DataFrame({"a": [1]}))


def test_short_history_rejected():
    import pytest
    df = sp.load_orders(sp.make_sample())
    with pytest.raises(ValueError):
        sp.explain(df[df.date < df.date.min() + __import__("pandas").Timedelta(days=5)])


def test_app_runs_with_demo():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file("app.py").run(timeout=60)
    at.checkbox[0].check().run(timeout=60)
    assert not at.exception
    assert any("Alpha Mug" in c.value for c in at.code)


def test_timezone_offset_does_not_shift_days():
    df = sp.make_sample()
    plain = sp.explain(sp.load_orders(df))
    d2 = df.copy()
    d2["Created at"] = d2["Created at"].dt.strftime("%Y-%m-%d %H:%M:%S -0400")
    with_tz = sp.explain(sp.load_orders(d2))
    assert abs(plain["delta"] - with_tz["delta"]) < 1e-6
