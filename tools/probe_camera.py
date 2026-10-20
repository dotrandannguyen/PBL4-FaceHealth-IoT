"""Probe local webcams in short-lived workers; never save or transmit frames."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

parser=argparse.ArgumentParser()
parser.add_argument('--one',type=int)
parser.add_argument('--backend',choices=['dshow','msmf'],default='dshow')
args=parser.parse_args()
if args.one is not None:
    import cv2
    camera=cv2.VideoCapture(args.one,cv2.CAP_DSHOW if args.backend=='dshow' else cv2.CAP_MSMF)
    try:
        opened=camera.isOpened()
        ok,frame=camera.read() if opened else (False,None)
        print(json.dumps(dict(index=args.one,backend=args.backend,opened=opened,frame_ok=bool(ok and frame is not None))))
    finally:
        camera.release()
else:
    for index in range(3):
        for backend in ('dshow','msmf'):
            try:
                result=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--one',str(index),'--backend',backend],
                                      capture_output=True,text=True,timeout=8)
                state=json.loads(result.stdout.strip().splitlines()[-1])
                print(json.dumps(state),flush=True)
                if state['frame_ok']:
                    raise SystemExit(0)
            except (subprocess.TimeoutExpired,ValueError,IndexError):
                print(json.dumps(dict(index=index,backend=backend,frame_ok=False,probe_error=True)),flush=True)
    raise SystemExit(2)
