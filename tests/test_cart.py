# tests/test_cart.py — 測試購物車邏輯與驗證（v0.5：品名/數量/單價）
import pytest
from pos_core import POSCart

def test_cart_add_validation():
    cart = POSCart()
    # 新格式：文具 x1 @10, x2 @5000
    cart.add_item("文具", 1, 10)
    cart.add_item("文具", 2, 5000)
    assert cart.get_total() == 10 + 10000

    # 舊格式 add_item(amount) 相容
    cart2 = POSCart()
    cart2.add_item(100)
    assert cart2.get_total() == 100
    assert cart2.get_items()[0]["item_name"] == "文具"

    # 異常：單價範圍
    with pytest.raises(ValueError, match="單價超出範圍"):
        cart.add_item("文具", 1, 0)
    with pytest.raises(ValueError, match="單價超出範圍"):
        cart.add_item("文具", 1, 5001)
    # 異常：數量範圍
    with pytest.raises(ValueError, match="數量超出範圍"):
        cart.add_item("文具", 0, 100)
    with pytest.raises(ValueError, match="數量超出範圍"):
        cart.add_item("文具", 100, 100)

def test_cart_edit_delete():
    cart = POSCart()
    item1 = cart.add_item("文具", 1, 100)
    item2 = cart.add_item("文具", 2, 200)

    # 測試修改（數量/單價）
    cart.edit_item(item1["id"], qty=3, unit_price=150)
    assert cart.get_total() == 450 + 400

    # 舊格式修改相容
    cart.edit_item(item1["id"], new_amount=100)
    assert cart.get_total() == 100 + 400

    # 測試修改異常
    with pytest.raises(ValueError, match="單價超出範圍"):
        cart.edit_item(item1["id"], unit_price=6000)

    # 測試刪除
    cart.delete_item(item2["id"])
    assert len(cart.get_items()) == 1
    assert cart.get_total() == 100

    # 測試清空
    cart.clear()
    assert len(cart.get_items()) == 0
    assert cart.get_total() == 0

def test_cart_display_list():
    cart = POSCart()
    display = cart.get_display_list(20)
    assert len(display) == 20
    assert all(item["empty"] for item in display)

    for i in range(5):
        cart.add_item("文具", 1, 100)
    display = cart.get_display_list(20)
    assert len(display) == 20
    assert sum(1 for item in display if not item["empty"]) == 5
    assert display[0]["item_name"] == "文具"
    assert display[0]["qty"] == 1
    assert display[0]["amount"] == 100

    cart.clear()
    for i in range(25):
        cart.add_item("文具", 1, i + 1)
    display = cart.get_display_list(20)
    assert len(display) == 20
    assert all(not item["empty"] for item in display)
    assert display[0]["amount"] == 6
    assert display[-1]["amount"] == 25
