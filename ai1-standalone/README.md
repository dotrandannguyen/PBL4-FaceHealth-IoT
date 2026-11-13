# AI1 Standalone

Desktop AI1 demo, isolated from the team's legacy pbl4-face-ai code and the PHP application. This folder reuses the latest standalone implementation from DoAn_ChamCong_AI; it does not connect to the production MariaDB or write attendance data.

## Requirements

Python 3.12 on Windows is recommended. Tkinter is included with the standard Windows Python installer.

    cd /d C:\PBL4-FaceHealth-IoT\ai1-standalone
    py -3.12 -m venv .venv
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\python.exe -m pip install -r requirements-ai1.txt
    .venv\Scripts\python.exe ai1_gui.py

InsightFace downloads its pretrained model files on first use. Model files and employee data are not part of this repository.

## Implemented flow

- Face detection and 512D ArcFace embeddings use InsightFace buffalo_l and SCRFD.
- The standalone gallery stores five separate L2-normalized embeddings and enrollment images per employee in ai1_standalone_data/.
- AUTO guided enrollment calibrates a frontal reference, estimates relative pose with solvePnP, SO(3) rotation averaging and geodesic stability checks, and selects one sharp, quality-valid sample for each of frontal, left, right, up and down. AUTO collects five fresh candidates in a bounded 12-second window per pose and allows up to 60 seconds for that pose; it does not silently switch to manual mode.
- Manual enrollment remains available. Both modes check capture quality, valid 512D embeddings and same-person consistency before saving the five-sample batch.
- Recognition takes three fresh snapshots, checks temporal consistency, selects the sharpest frame, then matches its embedding with cosine MAX across the five samples per employee. The configured threshold is 0.45. It does not average embeddings.
- Webcam and ESP32-CAM MJPEG sources share the same GUI camera pipeline.

Local standalone records and images are stored only under ai1_standalone_data/, which is ignored by Git.

## Tests

Run from this folder:

    .venv\Scripts\python.exe -m py_compile ai1_gui.py ai1_standalone.py face_engine.py face_matching.py camera_source.py
    .venv\Scripts\python.exe -m compileall -q ai1_gui_core ai1_standalone_core
    .venv\Scripts\python.exe -m unittest discover -s ai1_gui_core\tests -v
    .venv\Scripts\python.exe -m unittest discover -s ai1_standalone_core\tests -v

These tests use simulated frames and mocks; they do not verify a physical webcam or ESP32-CAM.
