"""Exercise the real PHP router against a disposable DB owned by its runner."""
import base64
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import time
from uuid import uuid4
import zlib


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def request(port, method, path, payload=None, *, token=None, raw=None, media='application/json'):
    body = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
    headers = {'Content-Type': media}
    if token is not None:
        headers['Authorization'] = 'Bearer ' + token
    client = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    try:
        client.request(method, path, body=body, headers=headers)
        response = client.getresponse()
        content = response.read()
        return response.status, dict(response.getheaders()), content
    finally:
        client.close()


@contextmanager
def php_server(php, root, env, directory, token):
    port = free_port()
    session_dir = directory / ('sessions-' + str(port))
    session_dir.mkdir()
    server_env = dict(env, PBL4_INTERNAL_TOKEN=token)
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with (directory / ('http-' + str(port) + '.log')).open('wb') as log:
        process = subprocess.Popen([str(php), '-d', 'display_errors=0', '-d', 'log_errors=1',
            '-d', 'session.save_path=' + str(session_dir), '-d', 'post_max_size=16M',
            '-S', '127.0.0.1:' + str(port), '-t', str(root / 'DoAn_ChamCong_AI'),
            str(root / 'DoAn_ChamCong_AI/index.php')], env=server_env,
            stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
        try:
            deadline = time.monotonic() + 10
            while True:
                if process.poll() is not None:
                    raise RuntimeError('Temporary PHP server exited before startup')
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=.2):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Temporary PHP server did not start')
                    time.sleep(.05)
            yield port
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def png_pixel():
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\x00\x00\x00\x00')) + chunk(b'IEND', b''))


def run_http_tests(php, root, env, directory):
    if env.get('PBL4_TEST_DATABASE') != 'isolated' or int(env['MARIADB_PORT']) == 3306:
        raise RuntimeError('Only the disposable database runner may invoke these tests')
    fixture = root / 'DoAn_ChamCong_AI/tests/integration_attendance.php'
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

    def cli(mode):
        result = subprocess.run([str(php), str(fixture), mode], env=env, check=True,
                                capture_output=True, timeout=10, creationflags=flags)
        return result.stdout.decode('utf-8')

    if 'SEEDED' not in cli('http_seed'):
        raise RuntimeError('HTTP fixture was not seeded')
    checks = 0

    def expect(response, status):
        nonlocal checks
        actual, headers, body = response
        if actual != status:
            raise AssertionError(f'Expected HTTP {status}, received {actual}: {body[:180]!r}')
        if status in (401, 503) and 'no-store' not in headers.get('Cache-Control', ''):
            raise AssertionError('Sensitive error response may be cached')
        if status == 503 and any(marker in body for marker in (b'SQLSTATE', b'PDOException', b'Injected private')):
            raise AssertionError('HTTP response exposed private database details')
        checks += 1
        return json.loads(body) if headers.get('Content-Type', '').startswith('application/json') else body

    instant = (datetime.now(timezone(timedelta(hours=7))) - timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    image = png_pixel()
    payload = {'event_id': str(uuid4()), 'MaNV': 10, 'MaTB': 1, 'occurred_at': instant.isoformat(),
               'TrangThai': 'Normal', 'NhipTim': 80, 'SpO2': 98,
               'image': base64.b64encode(image).decode()}
    token = secrets.token_urlsafe(32)
    with php_server(php, root, env, directory, token) as port:
        before = json.loads(cli('http_inspect'))
        for bad_token in (None, 'incorrect-test-token'):
            expect(request(port, 'POST', '/api/chamcong', payload, token=bad_token), 401)
            expect(request(port, 'GET', '/?action=internal_face_gallery', token=bad_token), 401)
        response = request(port, 'GET', '/api/chamcong', token=token)
        expect(response, 405)
        if response[1].get('Allow') != 'POST':
            raise AssertionError('Missing Allow header')
        expect(request(port, 'GET', '/?action[]=chamcong', token=token), 400)
        gallery = expect(request(port, 'GET', '/?action=internal_face_gallery', token=token), 200)
        if gallery.get('success') is not True or not isinstance(gallery.get('embeddings'), list):
            raise AssertionError('Invalid gallery contract')
        expect(request(port, 'POST', '/api/chamcong', payload, token=token, media='text/plain'), 415)
        for raw in (b'{', b'[]', b'null', b'"text"'):
            expect(request(port, 'POST', '/api/chamcong', token=token, raw=raw), 400)
        invalid_values = [('MaNV', True), ('MaNV', []), ('MaNV', 1.5), ('MaTB', 0),
            ('event_id', '../escape'), ('TrangThai', 'unrecognized'), ('TrangThai', []),
            ('NhipTim', '80'), ('NhipTim', 80.5), ('NhipTim', -1), ('SpO2', True), ('SpO2', 101),
            ('occurred_at', '2026-02-31T08:00:00+07:00'),
            ('occurred_at', '2026-10-20T08:00:00'), ('image', 'not-base64'),
            ('image', base64.b64encode(b'not an image').decode()), ('image', [])]
        for key, value in invalid_values:
            expect(request(port, 'POST', '/api/chamcong', dict(payload, **{key: value}), token=token), 400)
        expect(request(port, 'POST', '/api/chamcong', token=token, raw=b' ' * (8 * 1024 * 1024 + 1)), 413)
        if json.loads(cli('http_inspect')) != before:
            raise AssertionError('Rejected HTTP requests changed the database')

        result = expect(request(port, 'POST', '/api/chamcong', payload, token=token), 200)
        replay = expect(request(port, 'POST', '/api/chamcong', payload, token=token), 200)
        if result.get('action') != 'checkin' or replay.get('action') != 'checkin' or replay.get('duplicate') is not True:
            raise AssertionError('HTTP replay changed the action')
        equivalent = dict(payload, occurred_at=instant.astimezone(timezone.utc).isoformat(), NhipTim=80.0, SpO2=98.0)
        normalized = expect(request(port, 'POST', '/api/chamcong', equivalent, token=token), 200)
        if normalized.get('action') != 'checkin' or normalized.get('duplicate') is not True:
            raise AssertionError('Equivalent timezone/integer-valued metrics changed the request hash')
        expect(request(port, 'POST', '/api/chamcong', dict(payload, NhipTim=81), token=token), 409)
        expect(request(port, 'POST', '/api/chamcong', dict(payload, event_id=str(uuid4()), MaNV=999), token=token), 409)
        expect(request(port, 'POST', '/api/chamcong', dict(payload, event_id=str(uuid4()), MaTB=999), token=token), 409)
        state = json.loads(cli('http_inspect'))
        if state['ChamCong'] != 1 or state['AttendanceEvent'] != 1 or state['LichSuSucKhoe'] != 1:
            raise AssertionError('HTTP replay/conflicts duplicated records')
        row = state['attendance'][0]
        if row['ImageHash'] != hashlib.sha256(image).hexdigest() or row['GioVao'] != instant.strftime('%Y-%m-%d %H:%M:%S.000'):
            raise AssertionError('Original event image/time was not preserved')

        checkout = dict(payload, event_id=str(uuid4()), occurred_at=(instant + timedelta(hours=1)).isoformat(), TrangThai='Unknown')
        out = expect(request(port, 'POST', '/api/chamcong', checkout, token=token), 200)
        if out.get('action') != 'checkout' or out.get('event_id') != checkout['event_id']:
            raise AssertionError('Invalid checkout contract')
        final = json.loads(cli('http_inspect'))
        if final['LichSuTrangThai'] != 1 or final['attendance'][0]['TheTrangRa'] != 'Chưa đánh giá':
            raise AssertionError('Unknown was stored as Normal')

        # Force a failure after the service has inserted its event/attendance.
        if 'FAILURE_ENABLED' not in cli('http_fail_health'):
            raise AssertionError('Failure injection was not enabled')
        failed = dict(payload, event_id=str(uuid4()), MaNV=11, TrangThai='Fatigue')
        try:
            expect(request(port, 'POST', '/api/chamcong', failed, token=token), 503)
            if json.loads(cli('http_inspect')) != final:
                raise AssertionError('HTTP storage failure left partial data')
        finally:
            cli('http_clear_health_failure')
        recovered = expect(request(port, 'POST', '/api/chamcong', failed, token=token), 200)
        if recovered.get('event_id') != failed['event_id'] or recovered.get('action') != 'checkin':
            raise AssertionError('Retry after rollback did not preserve event/action')

    # A missing token is a configuration error, not an open internal API.
    with php_server(php, root, env, directory, '') as port:
        expect(request(port, 'POST', '/api/chamcong', payload, token=token), 503)
        expect(request(port, 'GET', '/?action=internal_face_gallery', token=token), 503)

    # Bind but do not listen: this port cannot accidentally point to a real DB.
    with socket.socket() as unreachable:
        unreachable.bind(('127.0.0.1', 0))
        unavailable_env = dict(env, MARIADB_PORT=str(unreachable.getsockname()[1]))
        with php_server(php, root, unavailable_env, directory, token) as port:
            expect(request(port, 'POST', '/api/chamcong', payload, token=token), 503)
            expect(request(port, 'GET', '/?action=internal_face_gallery', token=token), 503)

    print(f'PASS: HTTP contract ({checks} checks): auth, routing, JSON, media/size limits, validation, replay, evidence, time, Unknown, rollback/recovery, DB unavailable; temporary DB only')
    return checks
