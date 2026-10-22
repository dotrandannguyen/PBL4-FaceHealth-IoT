"""Durable paired batches; publish recognition data only from confirmed DB rows."""
import base64
import hashlib
import json
import re
from pathlib import Path
import time
from uuid import UUID, uuid4

from .atomic_storage import atomic_write
from .enrollment_samples import prepare_samples
from .face_sync import employee_id, replace_samples, delete_samples, refresh_gallery, list_employees, SyncConflict
from .gallery_payload import gallery_revision
from .gallery_store import GalleryCache, gallery_lock

BASE = Path(__file__).resolve().parents[1] / 'data'


class DesktopEnrollment:
    def __init__(self, directory=BASE / 'enrollment-outbox', gallery_path=BASE / 'embeddings.pkl'):
        self.directory, self.gallery_path = Path(directory), Path(gallery_path)

    def pending(self):
        jobs = []
        for path in sorted((self.directory / 'pending').glob('*.json')):
            job = json.loads(path.read_text(encoding='utf-8'))
            if (not isinstance(job, dict) or job.get('id') != path.stem
                    or job.get('action') not in ('replace', 'delete')
                    or type(job.get('db_saved')) is not bool
                    or type(job.get('employee_id')) is not int
                    or type(job.get('created_at')) is not int or job['created_at'] <= 0
                    or not isinstance(job.get('expected_revision'), str)
                    or not re.fullmatch('[a-f0-9]{64}', job['expected_revision'])
                    or UUID(job['id']).version != 4):
                raise ValueError('Batch chờ bị lỗi; giữ nguyên file để kiểm tra')
            employee_id(job['employee_id'])
            if job['action'] == 'replace' and (not isinstance(job.get('samples'), list) or len(job['samples']) != 5):
                raise ValueError('Batch chờ thiếu mẫu; giữ nguyên để kiểm tra')
            jobs.append((path, job))
        return sorted(jobs, key=lambda item: item[1]['created_at'])

    def revision(self, sid):
        identity = employee_id(sid)
        gallery = GalleryCache().load(self.gallery_path)
        entries = [entry for key, entry in gallery.items() if employee_id(key) == identity]
        if len(entries) > 1 or (entries and not entries[0].get('revision')):
            raise ValueError('Gallery cũ chưa có phiên bản DB. Làm mới từ Web trước khi đăng ký/xóa.')
        return entries[0]['revision'] if entries else gallery_revision([])

    def _stage(self, sid, action, samples=None, name='', expected_revision=None):
        identity = employee_id(sid)
        with gallery_lock(self.directory / 'queue'):
            if any(employee_id(job['employee_id']) == identity for _, job in self.pending()):
                raise ValueError('Nhân viên có batch chờ. Hãy đồng bộ trước hoặc kiểm tra batch xung đột.')
            revision = self.revision(identity) if expected_revision is None else expected_revision
            if not isinstance(revision, str) or not re.fullmatch('[a-f0-9]{64}', revision):
                raise ValueError('Invalid DB revision')
            job = dict(id=str(uuid4()), employee_id=identity, name=name, action=action,
                       created_at=time.time_ns(), db_saved=False,
                       expected_revision=revision)
            if samples is not None:
                job['samples'] = [dict(pose=sample['pose'], vector=base64.b64encode(sample['vector'].tobytes()).decode('ascii'),
                    image=base64.b64encode(sample['image']).decode('ascii'),
                    image_sha256=hashlib.sha256(sample['image']).hexdigest()) for sample in prepare_samples(samples)]
            path = self.directory / 'pending' / (job['id'] + '.json')
            atomic_write(path, json.dumps(job, ensure_ascii=False).encode('utf-8'))
            return job['id']

    def stage(self, sid, name, samples, expected_revision=None):
        return self._stage(sid, 'replace', samples, name, expected_revision)

    def stage_delete(self, sid, expected_revision=None):
        return self._stage(sid, 'delete', expected_revision=expected_revision)

    def archive(self, sid):
        """Explicit operator action: retain rejected/obsolete batches without replay."""
        identity, archived = employee_id(sid), 0
        with gallery_lock(self.directory / 'queue'):
            for path, job in self.pending():
                if employee_id(job['employee_id']) != identity:
                    continue
                if job['db_saved']:
                    raise ValueError('DB đã xác nhận batch này; hãy thử refresh trước khi lưu trữ')
                target = self.directory / 'archived' / path.name
                if not path.resolve().is_relative_to(self.directory.resolve()) or not target.resolve().is_relative_to(self.directory.resolve()):
                    raise ValueError('Invalid archive path')
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    raise ValueError('Archive already exists')
                path.rename(target)
                archived += 1
        return dict(completed=0, pending=len(self.pending()), errors=[],
                    message=f'Đã lưu trữ {archived} batch chờ của NV {identity}; giữ nguyên DB và bản batch trong archived.')

    def employees(self):
        return list_employees()

    def retry(self, job_id=None):
        """Retry one explicit registration, or the full queue for maintenance."""
        import numpy as np
        completed, errors = 0, []
        jobs = {}
        blocked = set()
        with gallery_lock(self.directory / 'queue'):
            for path, job in self.pending():
                if job_id is not None and job['id'] != job_id:
                    continue
                identity = employee_id(job['employee_id'])
                if identity in blocked:
                    continue
                try:
                    if not job['db_saved']:
                        if job['action'] == 'delete':
                            delete_samples(identity, job['expected_revision'])
                        else:
                            samples = []
                            for sample in job['samples']:
                                image = base64.b64decode(sample['image'], validate=True)
                                if hashlib.sha256(image).hexdigest() != sample['image_sha256']:
                                    raise ValueError('Corrupt enrollment image')
                                samples.append(dict(pose=sample['pose'], image=image,
                                    vector=np.frombuffer(base64.b64decode(sample['vector'], validate=True), dtype='<f4')))
                            replace_samples(identity, job['name'], samples, job['expected_revision'])
                        # If refresh fails, never replay this write over a later Web edit.
                        job['db_saved'] = True
                        atomic_write(path, json.dumps(job, ensure_ascii=False).encode('utf-8'))
                    refresh_gallery(self.gallery_path)
                    receipt = dict(id=job['id'], employee_id=identity, action=job['action'], db_saved=True)
                    atomic_write(self.directory / 'receipts' / (job['id'] + '.json'), json.dumps(receipt).encode('utf-8'))
                    path.unlink()
                    completed += 1
                    jobs[job['id']] = 'completed'
                except SyncConflict:
                    blocked.add(identity)
                    jobs[job['id']] = 'conflict'
                    errors.append(f'NV {identity}: dữ liệu Web đã đổi; giữ batch xung đột, không ghi đè. Làm mới và kiểm tra batch.')
                except Exception:
                    blocked.add(identity)
                    jobs[job['id']] = 'saved' if job['db_saved'] else 'pending'
                    errors.append(f'NV {identity}: chưa hoàn tất DB/gallery; batch chờ được giữ để thử lại.')
        return dict(completed=completed, pending=len(self.pending()), errors=errors, jobs=jobs)

    def refresh(self):
        return refresh_gallery(self.gallery_path)
