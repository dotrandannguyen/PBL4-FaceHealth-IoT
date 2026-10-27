"""Validate Web gallery samples before replacing the active recognition gallery."""
import base64
import hashlib
import json


def gallery_revision(samples):
    pairs = sorted((int(sample_id), digest) for sample_id, digest in samples)
    return hashlib.sha256(json.dumps(pairs, separators=(',', ':')).encode('ascii')).hexdigest()


def build_gallery(payload):
    import numpy as np
    if not isinstance(payload, dict) or payload.get('success') is not True or not isinstance(payload.get('embeddings'), list):
        raise ValueError('Invalid gallery response')
    people = {}
    sample_ids = set()
    for sample in payload['embeddings']:
        if not isinstance(sample, dict):
            raise ValueError('Invalid gallery sample')
        employee, sample_id = sample.get('ma_nv'), sample.get('ma_embedding')
        if (type(employee) is not int or not 0 < employee <= 2147483647
                or type(sample_id) is not int or sample_id <= 0 or sample_id in sample_ids
                or sample.get('so_chieu') != 512):
            raise ValueError('Invalid gallery sample identity/dimensions')
        raw = base64.b64decode(sample['vector'], validate=True)
        if len(raw) != 2048 or sample.get('sha256') != hashlib.sha256(raw).hexdigest():
            raise ValueError('Invalid gallery sample integrity')
        vector = np.frombuffer(raw, dtype='<f4')
        norm = float(np.linalg.norm(vector))
        if not np.isfinite(vector).all() or not np.isfinite(norm) or norm <= 0:
            raise ValueError('Invalid gallery vector')
        name = sample.get('ho_ten')
        if not isinstance(name, str):
            raise ValueError('Invalid employee name')
        person = people.setdefault(employee, {'name': name, 'vectors': [], 'revisions': []})
        if person['name'] != name:
            raise ValueError('Inconsistent gallery identity')
        person['vectors'].append(vector / norm)
        person['revisions'].append((sample_id, sample['sha256']))
        sample_ids.add(sample_id)
    gallery = {}
    for employee, person in people.items():
        mean = np.mean(person['vectors'], axis=0)
        norm = float(np.linalg.norm(mean))
        if not np.isfinite(norm) or norm <= 0:
            raise ValueError('Invalid mean embedding')
        gallery[f'SV{employee:03d}'] = {'name': person['name'], 'embedding': mean / norm,
                                     'n_images': len(person['vectors']),
                                     'revision': gallery_revision(person['revisions'])}
    return gallery
