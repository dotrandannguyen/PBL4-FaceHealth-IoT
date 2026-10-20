"""Train a validated Random Forest artifact without modifying data or camera."""
import argparse
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from src.status_training import train


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=BASE/'data/status_dataset_v2.csv')
    parser.add_argument('--output', type=Path, default=BASE/'data/rf_status_model.pkl')
    parser.add_argument('--split', choices=['subject','session'], default='subject')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--test-size', type=float, default=.2)
    args = parser.parse_args(argv)
    try:
        metadata = train(args.data,args.output,split=args.split,seed=args.seed,test_size=args.test_size)
    except Exception as error:
        print('Train failed; model cũ được giữ nguyên:', str(error),file=sys.stderr)
        return 1
    print('Saved artifact:', args.output)
    print('Evaluation scope:',metadata['evaluation_scope'])
    print('Train/test rows:',metadata['train_rows'],metadata['test_rows'])
    print('Held-out accuracy:',round(metadata['accuracy'],4),'Macro F1:',round(metadata['macro_f1'],4))
    print('Metrics describe this dataset split; they do not establish medical or real-world accuracy.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
