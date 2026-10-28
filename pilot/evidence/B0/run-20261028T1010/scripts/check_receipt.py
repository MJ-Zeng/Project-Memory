"""Exit-code wrapper around ``verify_receipt`` for reproducible CLI evidence.

Exit 0 when the receipt is valid for the given repository, 3 when it is
rejected, 2 on usage errors.  This exists because there is no ``verify-receipt``
subcommand; the wrapper keeps AC-2 evidence in command/exit-code form.
"""
import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--code-root', required=True)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--receipt', required=True)
    args = parser.parse_args()
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    sys.path.insert(0, str(Path(args.code_root).resolve()))
    from project_memory.execution import verify_receipt

    checked = verify_receipt(Path(args.repo), args.receipt)
    receipt = checked.get('receipt') or {}
    print(json.dumps({
        'valid': checked['valid'],
        'problems': checked['problems'],
        'legacy_path_bound': checked.get('legacy_path_bound'),
        'identity': checked.get('identity'),
        'receipt': {
            'receipt_id': receipt.get('receipt_id'),
            'schema_version': receipt.get('schema_version'),
            'repo_id': receipt.get('repo_id'),
        },
    }, ensure_ascii=False, indent=2))
    return 0 if checked['valid'] else 3


if __name__ == '__main__':
    sys.exit(main())
