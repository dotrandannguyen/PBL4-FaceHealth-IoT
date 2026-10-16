
from flask import Flask, request, jsonify
from pathlib import Path
from datetime import datetime

app = Flask(__name__)

# Thu muc luu anh
UPLOAD_FOLDER = Path("received_images")
UPLOAD_FOLDER.mkdir(exist_ok=True)

@app.route("/", methods=["GET"])
def home():
    return "ESP32-CAM image server is running!"

# Tao dia chi de esp32-cam gui den
@app.route("/upload", methods=["POST"])
def upload_image():
    # Get du lieu anh JPEG tu ESP32-CAM
    image_data = request.get_data()

    if not image_data:
        return jsonify({
            "success": False,
            "message": "Khong nhan duoc du lieu anh"
        }), 400

    # Tao ten file theo thoi gian
    filename = datetime.now().strftime(
        "photo_%Y%m%d_%H%M%S_%f.jpg"
    )

    file_path = UPLOAD_FOLDER / filename
    file_path.write_bytes(image_data) # luu data thanh file anh tren may tinh

    print(f"Da nhan anh: {file_path}")
    print(f"Kich thuoc: {len(image_data)} bytes")

    return jsonify({
        "success": True,
        "message": "Da nhan anh",
        "filename": filename,
        "size": len(image_data)
    }), 200

# host="0.0.0.0": cho phép thiết bị khác trong mạng truy cập server, thay vì chỉ máy tính tự truy cập.
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False) 

