"""Simple integration test script for order endpoints.

Run this while the server is running (uvicorn main:app --reload --port 8080).
Set `BASE_URL` if your server is at a different host/port.
"""
import requests
import time

BASE_URL = "http://localhost:8080"


def create_order_example():
    payload = {
        "userId": 1,
        "productId": "sku_test",
        "currencyPrice": 100
    }
    r = requests.post(f"{BASE_URL}/api/order/create", json=payload, timeout=5)
    print("create", r.status_code, r.text)
    return r.json().get("data")


def get_by_order_no(order_no):
    r = requests.get(f"{BASE_URL}/api/order/{order_no}", timeout=5)
    print("get order", r.status_code, r.text)


def list_by_user(user_id):
    r = requests.get(f"{BASE_URL}/api/orders/user/{user_id}", timeout=5)
    print("list user orders", r.status_code, r.text)


if __name__ == "__main__":
    data = create_order_example()
    if data:
        order_no = data.get("orderNo")
        time.sleep(0.5)
        get_by_order_no(order_no)
        list_by_user(1)
