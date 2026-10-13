"""Evaluate buffalo_l using an isolated image dataset, never production rows.

Dataset layout:
    <root>/<MaNV>/gallery/*.jpg
    <root>/<MaNV>/probe/*.jpg
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from face_engine import face_engine
from face_evaluation import evaluate_scores
from face_matching import cosine_similarity, normalize_embedding


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def load_embeddings(folder, engine):
    vectors = []
    for image_path in sorted(folder.iterdir()):
        if image_path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        image = cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"Could not read image: {image_path}")
        _, embedding = engine.extract_embedding(image)
        vectors.append(normalize_embedding(embedding))
    return vectors


def evaluate_dataset(root, engine=face_engine):
    root = Path(root)
    if not root.is_dir():
        raise ValueError(f"Dataset directory does not exist: {root}")

    gallery = {}
    probes = {}
    for person_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        gallery_dir = person_dir / "gallery"
        probe_dir = person_dir / "probe"
        if not gallery_dir.is_dir() or not probe_dir.is_dir():
            continue
        gallery_vectors = load_embeddings(gallery_dir, engine)
        probe_vectors = load_embeddings(probe_dir, engine)
        if gallery_vectors and probe_vectors:
            gallery[person_dir.name] = normalize_embedding(np.mean(gallery_vectors, axis=0))
            probes[person_dir.name] = probe_vectors

    if len(gallery) < 2:
        raise ValueError("Dataset needs at least two identities with gallery and probe images.")

    genuine_scores = []
    impostor_scores = []
    for identity, identity_probes in probes.items():
        for probe in identity_probes:
            genuine_scores.append(cosine_similarity(probe, gallery[identity]))
            for other_id, other_gallery in gallery.items():
                if other_id != identity:
                    impostor_scores.append(cosine_similarity(probe, other_gallery))
    return evaluate_scores(genuine_scores, impostor_scores)


def main():
    parser = argparse.ArgumentParser(description="Calibrate buffalo_l face threshold on a separate test dataset.")
    parser.add_argument("dataset", help="Directory with <MaNV>/gallery and <MaNV>/probe subfolders")
    args = parser.parse_args()

    try:
        face_engine.initialize()
        metrics = evaluate_dataset(args.dataset)
    except Exception as exc:
        parser.error(str(exc))

    output = {key: value for key, value in metrics.items() if not key.endswith("_curve") and key != "thresholds"}
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
