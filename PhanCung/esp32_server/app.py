"""Authenticated, bounded JPEG receiver. Images do not create attendance events."""
from datetime import datetime, timezone
import hashlib
import hmac
import io
import os
from pathlib import Path
import sys
from uuid import uuid4
from flask import Flask,request,jsonify
from PIL import Image
from werkzeug.exceptions import RequestEntityTooLarge

AI_ROOT=Path(__file__).resolve().parents[2]/'pbl4-face-ai'
sys.path.insert(0,str(AI_ROOT))
from src.runtime_config import load_environment
from src.atomic_storage import atomic_write
from src.gallery_store import gallery_lock


def create_app(config=None):
    app=Flask(__name__)
    load_environment()
    app.config.update(MAX_CONTENT_LENGTH=5*1024*1024,
        UPLOAD_FOLDER=Path(__file__).resolve().parent/'received_images',
        UPLOAD_TOKEN=os.environ.get('PBL4_UPLOAD_TOKEN',''),
        MAX_STORED_BYTES=256*1024*1024,MAX_STORED_IMAGES=1000)
    if config:
        app.config.update(config)

    @app.after_request
    def no_store(response):
        response.headers['Cache-Control']='private, no-store'
        return response

    @app.errorhandler(RequestEntityTooLarge)
    def oversized(error):
        return jsonify(success=False,message='JPEG exceeds upload limit'),413

    @app.route('/',methods=['GET'])
    def health():
        return jsonify(success=True,service='PBL4 JPEG receiver')

    @app.route('/upload',methods=['POST'])
    def upload():
        token=app.config['UPLOAD_TOKEN']
        if not token:
            return jsonify(success=False,message='Upload API is not configured'),503
        supplied=request.headers.get('Authorization','').encode('utf-8')
        if not hmac.compare_digest(supplied,('Bearer '+token).encode('utf-8')):
            return jsonify(success=False,message='Unauthorized'),401
        if request.mimetype!='image/jpeg':
            return jsonify(success=False,message='Content-Type image/jpeg required'),415
        raw=request.get_data()
        if not raw:
            return jsonify(success=False,message='Empty JPEG'),400
        try:
            with Image.open(io.BytesIO(raw)) as image:
                if image.format!='JPEG' or image.width*image.height>16000000:
                    raise ValueError('Invalid JPEG dimensions')
                image.load()
        except Exception:
            return jsonify(success=False,message='Invalid JPEG'),400
        try:
            folder=Path(app.config['UPLOAD_FOLDER']).resolve()
            with gallery_lock(folder/'upload-quota'):
                files=list(folder.glob('*.jpg'))
                if len(files)>=app.config['MAX_STORED_IMAGES'] or sum(path.stat().st_size for path in files)+len(raw)>app.config['MAX_STORED_BYTES']:
                    return jsonify(success=False,message='Image storage quota reached'),507
                filename=uuid4().hex+'.jpg'
                atomic_write(folder/filename,raw)
            return jsonify(success=True,filename=filename,size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
                           received_at=datetime.now(timezone.utc).isoformat())
        except Exception:
            app.logger.exception('JPEG storage failed')
            return jsonify(success=False,message='Image storage unavailable'),503
    return app


app=create_app()

if __name__=='__main__':
    app.run(host=os.environ.get('PBL4_UPLOAD_BIND_HOST','127.0.0.1'),
            port=int(os.environ.get('PBL4_UPLOAD_PORT','5000')),debug=False)
