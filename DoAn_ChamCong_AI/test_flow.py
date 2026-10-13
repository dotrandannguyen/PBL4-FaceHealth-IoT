import requests
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

base = 'http://127.0.0.1:5000'

print('=== Test POST /api/chamcong ===')
for i in range(3):
    r = requests.post(base + '/api/chamcong', json={'MaNV': 1, 'MaTB': 1}, timeout=5)
    j = r.json()
    print(f'  [{i+1}] action={j.get("action")} status={j.get("status")}')
    print(f'       msg={j.get("message")}')  

print()
print('=== Dashboard Summary ===')
r = requests.get(base + '/api/dashboard/attendance', timeout=5)
j = r.json()
s = j.get('Summary', {})
for k, v in s.items():
    print(f'  {k}: {v}')

print()
tong = s.get('TongNhanVien', 0)
da   = s.get('DaChamCong', 0)
lam  = s.get('DangLamViec', 0)
chua = s.get('ChuaChamCong', 0)

print('=== Logic check ===')
print(f'  DangLamViec({lam}) <= DaChamCong({da}): {lam <= da}')
print(f'  DaChamCong({da}) <= TongNhanVien({tong}): {da <= tong}')
print(f'  ChuaChamCong({chua}) == {tong}-{da}={tong-da}: {chua == tong - da}')
