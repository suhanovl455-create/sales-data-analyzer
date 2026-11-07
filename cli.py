import argparse
from pathlib import Path
import json
from analyzer import validate_csv, analyze, report_zip

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Validate a sales CSV and export metrics.')
    parser.add_argument('csv', type=Path)
    parser.add_argument('--output', type=Path, default=Path('output/sales_analysis.zip'))
    args = parser.parse_args()
    validation = validate_csv(args.csv.read_bytes())
    result = analyze(validation.clean)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(report_zip(validation, result))
    print(f'Rows: {validation.total_rows}; accepted: {len(validation.clean)}; excluded: {len(validation.issues)}')
    print(json.dumps(result['metrics'], ensure_ascii=False, indent=2))
    print('Saved:', args.output)
