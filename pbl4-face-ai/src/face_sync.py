"""Transactional desktop face synchronization; never touches attendance history."""
import os
import re
from .runtime_config import load_environment


def employee_id(student_id):
    match = re.fullmatch(r"(?:SV|NV)?([0-9]+)", str(student_id), flags=re.IGNORECASE)
    if not match or not 0 < int(match.group(1)) <= 2147483647:
        raise ValueError("Use a positive numeric employee ID, SV001 or NV001")
    return int(match.group(1))


def connect():
    import pymysql
    load_environment()
    if not os.environ.get('MARIADB_USER') or 'MARIADB_PASSWORD' not in os.environ:
        raise RuntimeError('Configure database access in .env')
    return pymysql.connect(host=os.environ.get('MARIADB_HOST', '127.0.0.1'),
        port=int(os.environ.get('MARIADB_PORT', '3306')), user=os.environ['MARIADB_USER'],
        password=os.environ['MARIADB_PASSWORD'], database=os.environ.get('MARIADB_DATABASE', 'DoAn_ChamCong_AI_MariaDB'),
        charset='utf8mb4', autocommit=False, connect_timeout=3, read_timeout=10, write_timeout=10)


class SyncConflict(ValueError):
    pass


def _rows(cursor, identity):
    cursor.execute('SELECT MaEmbedding, VectorData, AnhKhuonMat FROM FaceEmbedding WHERE MaNV=%s ORDER BY MaEmbedding', (identity,))
    return cursor.fetchall()


def _revision(rows):
    import hashlib
    from .gallery_payload import gallery_revision
    return gallery_revision([(row[0], hashlib.sha256(row[1]).hexdigest()) for row in rows])


def _lock_employee(cursor, identity):
    cursor.execute('SELECT MaNV FROM NhanVien WHERE MaNV=%s FOR UPDATE', (identity,))
    if cursor.fetchone() is None:
        raise ValueError('Nhân viên chưa có trên Web. Hãy tạo hồ sơ trước.')


def replace_samples(student_id, name, samples, expected_revision=None):
    import base64
    from .enrollment_samples import prepare_samples
    identity = employee_id(student_id)
    prepared = prepare_samples(samples)
    connection = connect()
    try:
        with connection.cursor() as cursor:
            _lock_employee(cursor, identity)
            current = _rows(cursor, identity)
            # Lost DB ACK: recognize this exact batch without deleting/reinserting.
            matches = len(current) == 5 and all(row[1] == sample['vector'].tobytes() and row[2] == sample['image']
                                                for row, sample in zip(current, prepared))
            if not matches:
                if _revision(current) != expected_revision:
                    raise SyncConflict('Dữ liệu Web đã thay đổi. Làm mới danh sách và đăng ký lại; batch chờ được giữ nguyên.')
                cursor.execute('DELETE FROM FaceEmbedding WHERE MaNV=%s', (identity,))
                cursor.executemany('INSERT INTO FaceEmbedding (MaNV, VectorData, AnhKhuonMat, SoChieu) VALUES (%s,%s,%s,512)',
                    [(identity, sample['vector'].tobytes(), sample['image']) for sample in prepared])
                avatar = 'data:' + prepared[0]['mime'] + ';base64,' + base64.b64encode(prepared[0]['image']).decode('ascii')
                cursor.execute('UPDATE NhanVien SET AnhKhuonMat=%s WHERE MaNV=%s', (avatar, identity))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def delete_samples(student_id, expected_revision=None):
    identity = employee_id(student_id)
    connection = connect()
    try:
        with connection.cursor() as cursor:
            _lock_employee(cursor, identity)
            current = _rows(cursor, identity)
            if current and _revision(current) != expected_revision:
                raise SyncConflict('Dữ liệu Web đã thay đổi. Làm mới danh sách trước khi xóa.')
            cursor.execute('DELETE FROM FaceEmbedding WHERE MaNV=%s', (identity,))
            cursor.execute('UPDATE NhanVien SET AnhKhuonMat=NULL WHERE MaNV=%s', (identity,))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def refresh_gallery(path):
    from .gallery_payload import build_gallery
    from .gallery_store import replace_from_loader
    import base64
    import hashlib
    def fetch():
        connection = connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT fe.MaNV, fe.MaEmbedding, fe.SoChieu, fe.VectorData, nv.HoTen FROM FaceEmbedding fe JOIN NhanVien nv ON nv.MaNV=fe.MaNV ORDER BY fe.MaNV,fe.MaEmbedding')
                payload = [dict(ma_nv=row[0], ma_embedding=row[1], so_chieu=row[2],
                    vector=base64.b64encode(row[3]).decode('ascii'), sha256=hashlib.sha256(row[3]).hexdigest(), ho_ten=row[4] or '')
                    for row in cursor.fetchall()]
            return build_gallery({'success': True, 'embeddings': payload})
        finally:
            connection.close()
    return replace_from_loader(path, fetch)
