"""Compare _repo_matches results for one package (prev vs candidate)."""
import json
import sys
from pathlib import Path

package, repo = sys.argv[1], sys.argv[2]
declared = sys.argv[3:]
sys.path.insert(0, str(Path(package).resolve()))
from project_memory.coordination import _repo_matches  # noqa: E402

print(json.dumps({
    'package': str(Path(package).resolve()),
    'repo': repo,
    'results': {value: bool(_repo_matches(Path(repo), value))
                for value in declared},
}, ensure_ascii=False, indent=2))
