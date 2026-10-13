"""
test_api.py -- Script kiem thu API
"""

import requests
import time

BASE_URL = 'http://127.0.0.1:5000'

def check_server():
    try:
        r = requests.get(f'{BASE_URL}/', timeout=3)
        return True
    except requests.exceptions.ConnectionError:
        return False

def test_endpoints():
    print("=== Testing Authentication and Authorization ===")
    
    # 1. Chua login -> admin API = 401
    r = requests.get(f"{BASE_URL}/api/dashboard/attendance")
    print(f"Test 1: Chua login -> /api/dashboard/attendance = {r.status_code} (Expected 401)")
    if r.status_code == 401:
        print("  -> PASS")
    else:
        print("  -> FAIL")

    # 2. admin / 123456 -> dashboard = 200
    session_admin = requests.Session()
    r = session_admin.post(f"{BASE_URL}/api/login", json={"TenDangNhap": "admin", "MatKhau": "123456"})
    print(f"Test 2a: Login Admin -> {r.status_code}")
    
    r = session_admin.get(f"{BASE_URL}/api/dashboard/attendance")
    print(f"Test 2b: admin -> /api/dashboard/attendance = {r.status_code} (Expected 200)")
    if r.status_code == 200:
        print("  -> PASS")
    else:
        print("  -> FAIL")
        
    # 3. user01 / 123456 -> /api/me/profile = 200
    session_user = requests.Session()
    r = session_user.post(f"{BASE_URL}/api/login", json={"TenDangNhap": "user01", "MatKhau": "123456"})
    print(f"Test 3a: Login user01 -> {r.status_code}")
    
    r = session_user.get(f"{BASE_URL}/api/me/profile")
    print(f"Test 3b: user01 -> /api/me/profile = {r.status_code} (Expected 200)")
    if r.status_code == 200:
        print("  -> PASS")
    else:
        print("  -> FAIL")

    # 4. employee goi dashboard = 403
    r = session_user.get(f"{BASE_URL}/api/dashboard/attendance")
    print(f"Test 4: user01 -> /api/dashboard/attendance = {r.status_code} (Expected 403)")
    if r.status_code == 403:
        print("  -> PASS")
    else:
        print("  -> FAIL")

    # 5. employee goi /api/me/profile = 200
    r = session_user.get(f"{BASE_URL}/api/me/profile")
    print(f"Test 5: user01 -> /api/me/profile = {r.status_code} (Expected 200)")
    if r.status_code == 200:
        print("  -> PASS")
    else:
        print("  -> FAIL")

    # 6. logout -> /api/me/profile = 401
    r = session_user.post(f"{BASE_URL}/api/logout")
    r = session_user.get(f"{BASE_URL}/api/me/profile")
    print(f"Test 6: logout -> /api/me/profile = {r.status_code} (Expected 401)")
    if r.status_code == 401:
        print("  -> PASS")
    else:
        print("  -> FAIL")

if __name__ == '__main__':
    if not check_server():
        print("Server is not running. Start it first.")
    else:
        test_endpoints()