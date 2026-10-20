"""Real sklearn fit/save/load tests on synthetic data in temporary directories."""
import argparse
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

parser=argparse.ArgumentParser()
parser.add_argument('--deps',type=Path)
args,remaining=parser.parse_known_args()
if args.deps:
    sys.path.insert(0,str(args.deps))
ROOT=Path(__file__).resolve().parents[1]/'pbl4-face-ai'
sys.path.insert(0,str(ROOT))
import joblib
import numpy as np
import sklearn
from src.status_dataset import SequenceCollector,StatusDataset,encode_dataset
from src.status_training import train
from src.status_model import load_status_model
from src.sequence_features import LABELS,FEATURE_NAMES
from src.predict_status import StatusPredictor,probabilities
from uuid import uuid4


def observation(ear=.3,pitch=180):
    return dict(ear=ear,mar=.1,pitch=pitch,yaw=0,roll=0)


def synthetic_rows(subjects=6):
    rows=[]
    for person in range(subjects):
        session=str(uuid4())
        for label,ear in zip(LABELS,(.32,.2,.1)):
            for repeat in range(4):
                collector=SequenceCollector(f'P{person:02}',session)
                collector.start(label)
                collector.observe(observation(ear,179),0,'2026-10-20T10:00:00+07:00')
                collector.observe(observation(ear+.001*repeat,180),.31)
                rows.append(collector.observe(observation(ear,-179),.62))
    return rows


class TrainingTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='pbl4-training-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.csv=self.root/'dataset.csv'
        self.model=self.root/'model.pkl'
        self.csv.write_bytes(encode_dataset(synthetic_rows()))

    def fit(self):
        return train(self.csv,self.model)

    def test_real_fit_artifact_provenance_disjoint_subjects_and_load(self):
        raw=self.csv.read_bytes()
        metadata=self.fit()
        model,saved=load_status_model(self.model)
        self.assertEqual(saved,metadata)
        self.assertEqual(saved['dataset_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(self.csv.read_bytes(),raw)
        self.assertEqual(saved['feature_names'],FEATURE_NAMES)
        self.assertFalse(set(saved['train_subjects'])&set(saved['test_subjects']))
        self.assertFalse(set(saved['train_sessions'])&set(saved['test_sessions']))
        self.assertEqual(set(saved['test_class_counts']),set(LABELS))
        self.assertEqual((saved['train_rows'],saved['test_rows']),(48,24))
        self.assertEqual(len(model.predict_proba([[.3,.3,.1,.1,2,0,0]])[0]),3)
        self.assertEqual(saved['versions']['sklearn'],sklearn.__version__)
        json.dumps(saved,allow_nan=False)

    def test_same_seed_is_reproducible_and_session_scope_is_explicit(self):
        first=self.fit()
        second=self.fit()
        self.assertEqual(first['test_subjects'],second['test_subjects'])
        self.assertEqual(first['confusion_matrix'],second['confusion_matrix'])
        rows=synthetic_rows(2)
        for row in rows:
            row['subject_id']='SamePerson'
        self.csv.write_bytes(encode_dataset(rows))
        before=self.model.read_bytes()
        with self.assertRaises(ValueError):
            self.fit()
        self.assertEqual(self.model.read_bytes(),before)
        metadata=train(self.csv,self.model,split='session')
        self.assertEqual(metadata['evaluation_scope'],'held_out_sessions_not_new_people')
        self.assertEqual(metadata['train_subjects'],metadata['test_subjects'])
        self.assertFalse(set(metadata['train_sessions'])&set(metadata['test_sessions']))

    def test_write_failure_and_invalid_csv_keep_previous_artifact(self):
        self.fit()
        before=self.model.read_bytes()
        with patch('src.status_training.atomic_write',side_effect=OSError('injected save failure')):
            with self.assertRaises(OSError):
                self.fit()
        self.assertEqual(self.model.read_bytes(),before)
        for invalid in (b'min_ear,label\n.3,Normal\n',encode_dataset(synthetic_rows(1))):
            self.csv.write_bytes(invalid)
            with self.assertRaises(ValueError):
                self.fit()
            self.assertEqual(self.model.read_bytes(),before)
        load_status_model(self.model)

    def test_legacy_and_incompatible_artifacts_are_rejected(self):
        self.fit()
        artifact=joblib.load(self.model)
        invalid=self.root/'invalid.pkl'
        joblib.dump(artifact['model'],invalid)
        with self.assertRaises(ValueError):
            load_status_model(invalid)
        for key,value in (('feature_names',list(reversed(FEATURE_NAMES))),('feature_schema','old'),
                          ('interval_ms',30),('classes',['Normal']),('versions',{'sklearn':'0.0'})):
            bad=dict(artifact,metadata=dict(artifact['metadata'],**{key:value}))
            joblib.dump(bad,invalid)
            with self.assertRaises(ValueError):
                load_status_model(invalid)

    def test_predictor_uses_validated_bundle_and_same_temporal_features(self):
        self.fit()
        closed=[]
        extractor=types.SimpleNamespace(extract_features=lambda frame:observation(),close=lambda:closed.append(True))
        now=[0]
        predictor=StatusPredictor(model_path=self.model,extractor=extractor,clock=lambda:now[0])
        try:
            self.assertTrue(predictor.predict_status_detailed([object()]*3)['is_valid'])
            self.assertFalse(predictor.predict_frame(object())['is_valid'])
            now[0]=.1
            self.assertFalse(predictor.predict_frame(object())['is_valid'])
            now[0]=.3
            self.assertFalse(predictor.predict_frame(object())['is_valid'])
            now[0]=.6
            result=predictor.predict_frame(object())
            self.assertTrue(result['is_valid'])
            self.assertIn(result['status'],LABELS)
            now[0]=2
            self.assertFalse(predictor.predict_frame(object())['is_valid'])
            self.assertEqual(len(predictor.feature_buffer),1)
            extractor.extract_features=lambda frame:None
            self.assertFalse(predictor.predict_frame(object())['is_valid'])
            self.assertFalse(predictor.feature_buffer)
        finally:
            predictor.close()
        self.assertEqual(closed,[True])

    def test_whole_probability_vector_must_be_valid(self):
        for values in ([.8,.4,-.2],[.6,.6,.6],[.5,float('nan'),.5],[.8,.2]):
            model=types.SimpleNamespace(predict_proba=lambda rows:[values])
            with self.assertRaises(ValueError):
                probabilities(model,[0]*7,list(LABELS))

    def test_cli_invalid_dataset_returns_nonzero_without_changing_model(self):
        self.fit()
        before=self.model.read_bytes()
        self.csv.write_bytes(b'min_ear,label\n.3,Normal\n')
        env=dict(os.environ,PYTHONPATH=str(args.deps)+os.pathsep+str(ROOT))
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        result=subprocess.run([sys.executable,'-B',str(ROOT/'src/train_rf.py'),'--data',str(self.csv),'--output',str(self.model)],
                              env=env,capture_output=True,timeout=20,creationflags=flags)
        self.assertEqual(result.returncode,1,result.stderr.decode(errors='replace'))
        self.assertIn(b'Train failed',result.stderr)
        self.assertEqual(self.model.read_bytes(),before)


class CollectorRuntimeTests(unittest.TestCase):
    def test_dashboard_does_not_train_after_cancelled_or_failed_collection(self):
        import gui
        for codes,expected in (([2],1),([1],1),([0,1],2),([0,0],2)):
            calls,messages=[],[]
            pending=list(codes)
            class Runner:
                def run(self,command,**kwargs):
                    calls.append(command)
                    return types.SimpleNamespace(returncode=pending.pop(0))
            owner=types.SimpleNamespace(train_busy=False,training_runner=Runner())
            owner.training_io=types.SimpleNamespace(submit=lambda work,success,failure:success(work()))
            with patch.object(gui.simpledialog,'askstring',return_value='P01'), patch.object(gui.messagebox,'askyesno',return_value=True), patch.object(gui.messagebox,'showinfo',side_effect=lambda *args:messages.append(args)), patch.object(gui.messagebox,'showerror'):
                gui.FaceAIDashboard.handle_train_status(owner)
            self.assertEqual(len(calls),expected)
            self.assertIn('--subject',calls[0])
            self.assertIn('P01',calls[0])
            self.assertFalse(owner.train_busy)
            self.assertEqual(len(messages),1)

    def run_fake(self,path,keys,*,fail=False):
        spec=importlib.util.spec_from_file_location('collector_under_test',ROOT/'scripts/collect_status.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        state=dict(released=False,closed=False,destroyed=False)
        class Camera:
            def read(self):
                return True,np.zeros((16,16,3),np.uint8)
            def release(self):
                state['released']=True
        class Extractor:
            def extract_features(self,frame):
                if fail:
                    raise RuntimeError('injected extractor failure')
                return observation()
            def close(self):
                state['closed']=True
        sequence=iter(keys)
        times=iter([i*.3 for i in range(30)])
        ui=types.SimpleNamespace(FONT_HERSHEY_SIMPLEX=1,putText=lambda *a:None,imshow=lambda *a:None,
             waitKey=lambda delay:next(sequence),destroyAllWindows=lambda:state.update(destroyed=True))
        try:
            return module.run_collection('P01',path,camera_factory=Camera,extractor_factory=Extractor,ui=ui,clock=lambda:next(times))
        finally:
            self.assertTrue(all(state.values()),state)

    def test_main_collection_saves_only_complete_sequences_and_releases(self):
        with tempfile.TemporaryDirectory(prefix='pbl4-collector-test-') as temporary:
            path=Path(temporary)/'dataset.csv'
            self.assertEqual(self.run_fake(path,[ord('1'),-1,-1,ord('q')])['saved'],1)
            self.assertEqual(len(StatusDataset(path).inspect()),1)
            before=path.read_bytes()
            self.assertEqual(self.run_fake(path,[ord('2'),ord('q')])['saved'],0)
            self.assertEqual(path.read_bytes(),before)

    def test_extractor_exception_releases_camera_and_does_not_write_partial(self):
        with tempfile.TemporaryDirectory(prefix='pbl4-collector-test-') as temporary:
            path=Path(temporary)/'dataset.csv'
            with self.assertRaises(RuntimeError):
                self.run_fake(path,[],fail=True)
            self.assertFalse(path.exists())

    def test_landmarks_reject_multiple_faces_and_degenerate_geometry(self):
        calls={}
        mesh=types.SimpleNamespace(process=lambda frame:types.SimpleNamespace(multi_face_landmarks=[object(),object()]),close=lambda:None)
        def build(**kwargs):
            calls.update(kwargs)
            return mesh
        mp=types.SimpleNamespace(solutions=types.SimpleNamespace(face_mesh=types.SimpleNamespace(FaceMesh=build)))
        cv=types.SimpleNamespace(cvtColor=lambda frame,flag:frame,COLOR_BGR2RGB=1,solvePnP=lambda *a:(False,None,None))
        spec=importlib.util.spec_from_file_location('features_under_test',ROOT/'src/status_features.py')
        module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,mediapipe=mp,cv2=cv):
            spec.loader.exec_module(module)
            extractor=module.StatusFeatureExtractor()
            self.assertIsNone(extractor.extract_features(np.zeros((16,16,3),np.uint8)))
            self.assertEqual(calls['max_num_faces'],2)
            points=np.zeros((478,2))
            self.assertTrue(math.isnan(extractor._calculate_ear(points)))
            self.assertTrue(math.isnan(extractor._calculate_mar(points)))
            self.assertTrue(all(math.isnan(value) for value in extractor._calculate_head_pose(points,640,480)))
            extractor.close()


if __name__=='__main__':
    print('Synthetic training test versions:',sklearn.__version__,np.__version__,joblib.__version__)
    unittest.main(argv=[sys.argv[0]]+remaining)
