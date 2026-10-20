from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.sequence_features import calculate_sequence_features
from src.status_dataset import SequenceCollector, StatusDataset, encode_dataset, decode_dataset, validate_row
from src.status_training import split_rows
from src.process_runner import ProcessRunner

FEATURES=dict(ear=.3,mar=.1,pitch=180,yaw=0,roll=0)

def row(subject='P01',label='Normal',session=None):
    collector=SequenceCollector(subject,session)
    collector.start(label)
    collector.observe(FEATURES,0,'2026-10-20T08:00:00+07:00')
    collector.observe(FEATURES,.3)
    return collector.observe(FEATURES,.6)

def rows(subjects=4):
    result=[]
    for person in range(subjects):
        session=str(uuid4())
        for label in ('Normal','Fatigue','Exhausted'):
            for _ in range(3):
                result.append(row('P'+str(person),label,session))
    return result


class CollectionTests(unittest.TestCase):
    def test_three_timed_observations_and_metadata(self):
        collector=SequenceCollector('P01')
        collector.start('Fatigue')
        for now in (0,.01,.1,.299,.3,.31):
            self.assertIsNone(collector.observe(FEATURES,now))
        result=collector.observe(FEATURES,.6)
        self.assertEqual(result['label'],'Fatigue')
        self.assertEqual(result['label_source'],'operator_manual')
        self.assertEqual((result['gap_1_ms'],result['gap_2_ms']),(300,300))
        self.assertEqual(result['mean_pitch'],0)
        self.assertIsNone(collector.label)

    def test_gap_invalid_pose_and_missing_face_cancel_without_padding(self):
        for features,now in ((None,.3),(dict(FEATURES,ear=float('nan')),.3),
                             (dict(FEATURES,yaw=60),.3),(FEATURES,.7),(FEATURES,-1)):
            collector=SequenceCollector('P01')
            collector.start('Normal')
            collector.observe(FEATURES,0)
            self.assertIsNone(collector.observe(features,now))
            self.assertIsNone(collector.label)
            self.assertIsNone(collector.observe(FEATURES,1))

    def test_label_restart_and_cancel_discard_partial_sequence(self):
        collector=SequenceCollector('P01')
        collector.start('Normal')
        collector.observe(FEATURES,0)
        collector.start('Exhausted')
        collector.observe(FEATURES,.3)
        collector.observe(FEATURES,.6)
        self.assertEqual(collector.observe(FEATURES,.9)['label'],'Exhausted')
        collector.start('Normal')
        collector.observe(FEATURES,1)
        collector.cancel()
        self.assertIsNone(collector.observe(FEATURES,1.3))

    def test_pitch_and_roll_wrap_do_not_invent_large_motion(self):
        features=[dict(FEATURES,pitch=pitch,roll=roll) for pitch,roll in ((179,179),(-179,-179),(180,180))]
        vector=calculate_sequence_features(features)
        self.assertEqual(vector[4:],[2,2,0])

    def test_finite_inputs_that_overflow_do_not_form_a_sequence(self):
        features=dict(FEATURES,ear=1e308)
        self.assertIsNone(calculate_sequence_features([features]*3))
        collector=SequenceCollector('P01')
        collector.start('Normal')
        collector.observe(features,0)
        collector.observe(features,.3)
        self.assertIsNone(collector.observe(features,.6))
        self.assertIsNone(collector.label)

    def test_invalid_subject_and_metadata_rejected(self):
        for subject in ('anonymous','legacy','UNKNOWN','','x y','../P01'):
            with self.assertRaises(ValueError):
                SequenceCollector(subject)
        valid=row()
        for key,value in (('interval_ms',10),('gap_2_ms',1000),('mean_ear',float('nan')),
                          ('feature_schema','legacy'),('captured_at','2026-10-20T08:00:00'),('label','Other')):
            with self.assertRaises(ValueError):
                validate_row(dict(valid,**{key:value}))


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='pbl4-status-dataset-')
        self.addCleanup(self.temporary.cleanup)
        self.store=StatusDataset(Path(self.temporary.name)/'dataset.csv')

    def test_replay_is_idempotent_conflict_preserves_file(self):
        observation=row()
        self.store.record(observation)
        before=self.store.path.read_bytes()
        self.store.record(observation)
        self.assertEqual(self.store.path.read_bytes(),before)
        with self.assertRaises(ValueError):
            self.store.record(dict(observation,label='Fatigue'))
        self.assertEqual(self.store.path.read_bytes(),before)
        self.assertEqual(len(list(self.store.pending.glob('*.json'))),1)

    def test_merge_failure_recovers_after_restart_without_losing_rows(self):
        observation=row()
        with patch.object(self.store,'_merge',side_effect=OSError('injected write failure')):
            with self.assertRaises(OSError):
                self.store.record(observation)
        self.assertFalse(self.store.path.exists())
        recovered=StatusDataset(self.store.path)
        self.assertEqual(recovered.recover(),1)
        self.assertEqual(len(recovered.inspect()),1)
        self.assertEqual(recovered.recover(),0)

    def test_legacy_csv_not_rewritten_or_given_fake_metadata(self):
        self.store.path.write_bytes(b'min_ear,label\n0.3,Normal\n')
        before=self.store.path.read_bytes()
        with self.assertRaises(ValueError):
            self.store.record(row())
        self.assertEqual(self.store.path.read_bytes(),before)

    def test_duplicate_sequence_and_cross_subject_session_rejected(self):
        first=row()
        with self.assertRaises(ValueError):
            decode_dataset(encode_dataset([first,first]))
        second=row('P02',session=first['session_id'])
        with self.assertRaises(ValueError):
            decode_dataset(encode_dataset([first,second]))

    def test_concurrent_writers_do_not_drop_sequences(self):
        code=('import sys; from src.status_dataset import SequenceCollector,StatusDataset; '
              "c=SequenceCollector(sys.argv[2]); c.start('Normal'); "
              "f=dict(ear=.3,mar=.1,pitch=180,yaw=0,roll=0); "
              'c.observe(f,0); c.observe(f,.3); StatusDataset(sys.argv[1]).record(c.observe(f,.6))')
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        processes=[subprocess.Popen([sys.executable,'-B','-c',code,str(self.store.path),'P'+str(i)],
            env=dict(os.environ,PYTHONPATH=str(ROOT)),stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=flags) for i in range(6)]
        try:
            for process in processes:
                _,error=process.communicate(timeout=10)
                self.assertEqual(process.returncode,0,error.decode(errors='replace'))
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.communicate()
        self.assertEqual(len(self.store.inspect()),6)


class SplitTests(unittest.TestCase):
    def test_subject_split_is_disjoint_reproducible_and_complete(self):
        data=rows()
        train,test=split_rows(data)
        self.assertEqual((train,test),split_rows(data))
        self.assertFalse({data[i]['subject_id'] for i in train}&{data[i]['subject_id'] for i in test})
        self.assertFalse({data[i]['session_id'] for i in train}&{data[i]['session_id'] for i in test})
        self.assertEqual(set(train)|set(test),set(range(len(data))))

    def test_session_split_requires_explicit_mode_and_does_not_claim_new_people(self):
        data=rows(2)
        for observation in data:
            observation['subject_id']='P01'
        with self.assertRaises(ValueError):
            split_rows(data)
        train,test=split_rows(data,mode='session')
        self.assertFalse({data[i]['session_id'] for i in train}&{data[i]['session_id'] for i in test})

    def test_split_without_test_class_coverage_is_rejected(self):
        data=rows()
        for i,observation in enumerate(data):
            observation['subject_id']=observation['label']
        with self.assertRaises(ValueError):
            split_rows(data)
        with self.assertRaises(ValueError):
            split_rows(rows()[:3])


class ProcessTests(unittest.TestCase):
    def test_owned_child_is_reaped_and_cannot_restart_after_close(self):
        runner=ProcessRunner()
        result=[]
        thread=threading.Thread(target=lambda:result.append(runner.run([sys.executable,'-B','-c','import time; time.sleep(30)'])))
        thread.start()
        try:
            deadline=time.monotonic()+3
            while not runner.active and time.monotonic()<deadline:
                time.sleep(.01)
            self.assertTrue(runner.active)
            runner.close()
            thread.join(3)
            self.assertFalse(thread.is_alive())
            self.assertFalse(runner.active)
            self.assertNotEqual(result[0].returncode,0)
            with self.assertRaises(RuntimeError):
                runner.run([sys.executable,'-c','pass'])
        finally:
            runner.close()
            thread.join(3)


if __name__=='__main__':
    unittest.main()
