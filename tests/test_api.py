# tests/test_api.py — Flask API 整合測試
import os
import pytest
import app as appmod
import database as db

@pytest.fixture()
def client():
    if os.path.exists(db.DB_PATH):
        try:
            os.remove(db.DB_PATH)
        except OSError:
            pass
    db.init_db()
    db.set_invoice_seq("TT", 1, 1, 100)
    appmod.cart.clear()
    appmod.app.config["TESTING"] = True
    with appmod.app.test_client() as c:
        yield c

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"

def test_index_title_uses_shop_name(client):
    import database as db
    db.set_shop_config("11112222", "大華文具", "TT", "台北市 test 路 3 號", "02-11112222")
    r = client.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "大華文具 POS 系統" in html

def test_cart_flow(client):
    r = client.post("/api/cart/add", json={"amount": 100})
    assert r.status_code == 201
    r = client.post("/api/cart/add", json={"amount": 6000})
    assert r.status_code == 400
    r = client.get("/api/cart")
    assert r.get_json()["total"] == 100

def test_checkout_auto_invoice(client):
    client.post("/api/cart/add", json={"amount": 50})
    r = client.post("/api/checkout", json={})
    assert r.status_code == 201
    assert r.get_json()["invoice_no"] == "TT00000001"
    assert r.get_json()["total"] == 50
    assert r.get_json()["tendered"] == 50
    assert r.get_json()["change"] == 0
    r = client.get("/api/cart")
    assert r.get_json()["total"] == 0

def test_checkout_tendered_api(client):
    import database as db
    db.set_shop_config("11112222", "大華文具", "TT", "台北市 test 路 3 號", "02-11112222")
    client.post("/api/cart/add", json={"item_name": "文具", "qty": 1, "unit_price": 100})
    r = client.post("/api/checkout", json={"tendered": 50})
    assert r.status_code == 400
    r = client.post("/api/checkout", json={"tendered": 1000})
    assert r.status_code == 201
    no = r.get_json()["invoice_no"]
    assert r.get_json()["change"] == 900
    r = client.get(f"/api/invoice/{no}")
    assert r.status_code == 200
    assert r.get_json()["lines"] == [
        {"item_name": "文具", "qty": 1, "unit_price": 100, "amount": 100}]
    assert "shop_name" in r.get_json()["shop"]

def test_checkout_bad_invoice(client):
    client.post("/api/cart/add", json={"amount": 50})
    r = client.post("/api/checkout", json={"invoice_no": "bad"})
    assert r.status_code == 400

def test_report_and_csv(client):
    client.post("/api/cart/add", json={"amount": 80})
    client.post("/api/checkout", json={})
    r = client.get("/api/report/daily")
    assert r.status_code == 200
    assert r.get_json()["total_amount"] == 80
    r = client.get("/api/report/export_csv")
    assert r.status_code == 200
    assert "TT00000001" in r.get_data(as_text=True)

def test_void_api(client):
    client.post("/api/cart/add", json={"amount": 80})
    no = client.post("/api/checkout", json={}).get_json()["invoice_no"]
    r = client.post(f"/api/invoice/{no}/void")
    assert r.status_code == 200
    r = client.get("/api/report/daily")
    assert r.get_json()["void_count"] == 1
    assert r.get_json()["total_amount"] == 0

def test_cart_three_fields(client):
    r = client.post("/api/cart/add", json={"item_name": "文具", "qty": 2, "unit_price": 50})
    assert r.status_code == 201
    assert r.get_json()["item"]["amount"] == 100
    r = client.post("/api/cart/add", json={"item_name": "文具", "qty": 0, "unit_price": 50})
    assert r.status_code == 400
    r = client.post("/api/cart/add", json={"item_name": "文具", "qty": 1, "unit_price": 6000})
    assert r.status_code == 400

def test_shop_and_monthly_api(client):
    r = client.get("/api/shop/config")
    assert r.status_code == 200
    assert r.get_json() == {}
    r = client.post("/api/shop/config", json={"tax_id": "123", "shop_name": "X", "invoice_prefix": "XY"})
    assert r.status_code == 400
    r = client.post("/api/shop/config", json={
        "tax_id": "87654321", "shop_name": "測試店", "invoice_prefix": "TT",
        "address": "台北市 test 路 2 號", "phone": "02-87654321"})
    assert r.status_code == 200
    assert r.get_json()["phone"] == "02-87654321"
    client.post("/api/cart/add", json={"item_name": "文具", "qty": 1, "unit_price": 105})
    client.post("/api/checkout", json={})
    import datetime
    ym = datetime.datetime.now().strftime("%Y-%m")
    r = client.get(f"/api/report/monthly?month={ym}")
    assert r.status_code == 200
    j = r.get_json()
    assert j["total_amount"] == 105
    assert j["sales_amount"] == 100
    assert j["tax_amount"] == 5
    # 報表字軌必須跟實際字軌（TT）一致，不跟商店設定的 EF 跑
    assert j["shop"]["invoice_prefix"] == "TT"
    r = client.get("/api/report/monthly?month=bad")
    assert r.status_code == 400
