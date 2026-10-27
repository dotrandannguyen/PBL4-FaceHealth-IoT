"""Real login/session/CSRF and enrollment routes, disposable DB and fake AI HTTP."""
import base64
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import secrets
import struct
import subprocess
import threading
from urllib.parse import urlencode

from test_http_attendance import php_server

JPEG = base64.b64decode('/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAj/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFAEBAAAAAAAAAAAAAAAAAAAAAP/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AJ/AB//Z')

def run_enrollment_tests(php, root, env, directory):
    if env.get('PBL4_TEST_DATABASE') != 'isolated' or int(env['MARIADB_PORT']) == 3306:
        raise RuntimeError('Only use the disposable database runner')
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    fixture = root / 'DoAn_ChamCong_AI/tests/integration_enrollment.php'
    def cli(mode):
        result = subprocess.run([str(php), str(fixture), mode], env=env, check=True,
                                capture_output=True, timeout=30, creationflags=flags)
        return result.stdout.decode('utf-8')
    output = cli('')
    if 'PASS:' not in output:
        raise AssertionError('Enrollment DB test did not report success')
    print(output.strip())
    token = secrets.token_urlsafe(32)
    state = dict(mode='normal', ready=True, refresh=True, refresh_count=0, camera_mode='normal', camera_hits=0)

    class FakeAI(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def reply(self, status, payload, media='application/json'):
            raw = json.dumps(payload).encode() if media == 'application/json' else payload
            self.send_response(status)
            self.send_header('Content-Type', media)
            if status == 302:
                self.send_header('Location', '/internal/camera/frame')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            try:
                self.wfile.write(raw)
            except OSError:
                pass  # Bounded camera clients may close before an oversized body ends.
        def do_GET(self):
            if self.path == '/health':
                self.reply(200, dict(success=True, model_ready=state['ready']))
            elif self.headers.get('Authorization') != 'Bearer ' + token:
                self.reply(401, dict(success=False))
            else:
                state['camera_hits'] += 1
                mode = state['camera_mode']
                self.reply(500 if mode == 'error' else (302 if mode == 'redirect' else 200),
                    b'fake JPEG' if mode == 'invalid' else (JPEG + b'0' * (5*1024*1024) if mode == 'large' else JPEG), 'image/jpeg')
        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            if self.headers.get('Authorization') != 'Bearer ' + token:
                self.reply(401, dict(success=False))
                return
            if self.path.endswith('/gallery/refresh'):
                state['refresh_count'] += 1
                # A dishonest 503 body must never become gallery_updated=true.
                self.reply(200 if state['refresh'] else 503, dict(success=True))
                return
            payload = json.loads(raw)
            if base64.b64decode(payload['image']) != JPEG:
                self.reply(400, dict(success=False))
                return
            axis = 1 if state['mode'] == 'other_person' else 0
            vector = struct.pack('<512f', *[1.0 if i == axis else 0.0 for i in range(512)])
            result = dict(success=True, pose_ok=True, pose=payload['expected_pose'],
                vector=base64.b64encode(vector).decode(), image_jpeg=base64.b64encode(JPEG).decode(),
                image_sha256=hashlib.sha256(JPEG).hexdigest())
            if state['mode'] == 'pose':
                self.reply(409, dict(success=False, pose_ok=False, message='Wrong pose'))
            elif state['mode'] == 'bad_pose_field':
                self.reply(200, dict(result, pose='wrong'))
            elif state['mode'] == 'bad_hash':
                self.reply(200, dict(result, image_sha256='wrong'))
            elif state['mode'] == 'http_error':
                self.reply(500, result)
            else:
                self.reply(200, result)

    server = ThreadingHTTPServer(('127.0.0.1', 0), FakeAI)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    checks = 0
    cookie = ''
    try:
        server_env = dict(env, AI_SERVICE_URL='http://127.0.0.1:' + str(server.server_port),
                          CAMERA_FRAME_URL='http://127.0.0.1:' + str(server.server_port) + '/internal/camera/frame')
        with php_server(php, root, server_env, directory, token) as port:
            def request(method, path, fields=None):
                nonlocal cookie
                connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
                try:
                    connection.request(method, path, urlencode(fields) if fields is not None else None,
                        {'Cookie': cookie, 'Content-Type': 'application/x-www-form-urlencoded'})
                    response = connection.getresponse()
                    headers, raw = dict(response.getheaders()), response.read()
                    if 'Set-Cookie' in headers:
                        cookie = headers['Set-Cookie'].split(';', 1)[0]
                    return response.status, headers, raw
                finally:
                    connection.close()
            def expect(response, status):
                nonlocal checks
                actual, headers, raw = response
                if actual != status:
                    raise AssertionError(f'Enrollment expected {status}, received {actual}: {raw[:250]!r}')
                checks += 1
                return json.loads(raw) if headers.get('Content-Type', '').startswith('application/json') else raw
            def post(action, expected=200, csrf=None):
                return expect(request('POST', '/?action=' + action + '&id=21',
                                     {'_csrf_token': csrf if csrf is not None else csrf_token}), expected)
            expect(request('POST', '/?action=face_enrollment_start&id=21'), 302)
            login = expect(request('GET', '/?action=login'), 200)
            login_csrf = re.search(rb'name="_csrf_token" value="([a-f0-9]+)"', login).group(1).decode()
            expect(request('POST', '/?action=login', dict(_csrf_token=login_csrf,
                username='enrollment-test-admin', password='isolated-test-password')), 302)
            # Exercise the actual admin attendance page, including the default
            # single-day query that API/enrollment-only tests did not cover.
            for query in ('', '&from_date=2001-01-02&to_date=2001-01-02',
                          '&from_date=2001-01-02&to_date=2001-01-03',
                          '&employee_id=21&keyword=Enrollment&limit=10&page=1'):
                page = expect(request('GET', '/?action=attendance' + query), 200)
                if b'Attendance page read failed' in page or b'SQLSTATE' in page or b'notice--error' in page:
                    raise AssertionError('Attendance page returned a hidden read error')
            form = expect(request('GET', '/?action=edit&id=21'), 200)
            csrf_token = re.search(rb'name="_csrf_token" value="([a-f0-9]+)"', form).group(1).decode()
            if expect(request('GET', '/?action=face_camera_frame'), 200) != JPEG:
                raise AssertionError('Camera relay changed JPEG bytes')
            for mode in ('error', 'redirect', 'invalid', 'large'):
                state['camera_mode'] = mode
                before_hits = state['camera_hits']
                expect(request('GET', '/?action=face_camera_frame'), 503)
                if state['camera_hits'] != before_hits + 1:
                    raise AssertionError('Camera client followed a redirect')
            state['camera_mode'] = 'normal'
            expect(request('GET', '/?action=face_gallery_refresh&id=21'), 405)
            post('face_enrollment_start', 400, csrf='incorrect')
            state['ready'] = False
            post('face_enrollment_start', 503)
            state['ready'] = True
            post('face_enrollment_capture', 410)
            post('face_enrollment_start')
            post('face_enrollment_complete', 409)
            post('face_enrollment_capture')
            for mode, status in [('pose', 409), ('other_person', 409), ('bad_pose_field', 502),
                                 ('bad_hash', 502), ('http_error', 503)]:
                state['mode'] = mode
                post('face_enrollment_capture', status)
            state['mode'] = 'normal'
            for count in range(2, 6):
                if post('face_enrollment_capture')['captured'] != count:
                    raise AssertionError('Rejected sample changed batch progress')
            before = json.loads(cli('inspect'))
            cli('fail_avatar')
            post('face_enrollment_complete', 500)
            if json.loads(cli('inspect')) != before:
                raise AssertionError('Failed save changed DB')
            cli('clear_failure')
            state['refresh'] = False
            saved = post('face_enrollment_complete')
            if saved['saved'] != 5 or saved['gallery_updated']:
                raise AssertionError('DB save and refresh failure conflated')
            saved_db = json.loads(cli('inspect'))
            if len(saved_db['samples']) != 5 or not saved_db['avatar'].startswith('data:image/jpeg;base64,'):
                raise AssertionError('Saved samples/avatar missing')
            refresh_count = state['refresh_count']
            if post('face_enrollment_complete') != saved or json.loads(cli('inspect')) != saved_db:
                raise AssertionError('Lost response replay wrote another batch')
            if state['refresh_count'] != refresh_count:
                raise AssertionError('Replay unexpectedly called AI again')
            post('face_enrollment_capture', 409)
            post('face_enrollment_pose', 409)
            post('face_gallery_refresh', 503)
            state['refresh'] = True
            post('face_gallery_refresh')
            if json.loads(cli('inspect')) != saved_db:
                raise AssertionError('Gallery retry changed stored samples')
            image_id = saved_db['samples'][0]['MaEmbedding']
            if expect(request('GET', '/?action=face_image&id=' + str(image_id)), 200) != JPEG:
                raise AssertionError('Protected sample image differs')
            # Starting/cancelling a replacement must retain the completed batch.
            post('face_enrollment_start')
            post('face_enrollment_capture')
            post('face_enrollment_cancel')
            post('face_enrollment_complete', 410)
            if json.loads(cli('inspect')) != saved_db:
                raise AssertionError('Cancel changed previous enrollment')
            cli('fail_avatar')
            post('face_registration_delete', 500)
            if json.loads(cli('inspect')) != saved_db:
                raise AssertionError('Delete failure did not roll back')
            cli('clear_failure')
            state['refresh'] = False
            deleted = post('face_registration_delete')
            if deleted['deleted'] != 5 or deleted['gallery_updated']:
                raise AssertionError('Delete result did not expose refresh failure')
            db = json.loads(cli('inspect'))
            if db['samples'] or db['avatar'] is not None:
                raise AssertionError('Delete left samples/avatar behind')
            expect(request('GET', '/?action=face_image&id=' + str(image_id)), 404)
            state['refresh'] = True
            post('face_gallery_refresh')
            post('face_registration_delete')
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
    print(f'PASS: {checks} enrollment HTTP checks (real admin login/CSRF, capture, rollback, replay, retry, deletion)')
