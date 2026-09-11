import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.optimization.tuning import tuning_gate


def main():
    parser = argparse.ArgumentParser(description="Compare measured tuning runs; never rewrites production settings")
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    args = parser.parse_args()
    result = tuning_gate(json.loads(args.baseline.read_text()), json.loads(args.candidate.read_text()))
    print(json.dumps(result, indent=2))
    return 0 if result["eligible_for_review"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
