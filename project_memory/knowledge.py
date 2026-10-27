"""Documents, ADR metadata and deterministic audit checks."""
from __future__ import annotations
import datetime as dt
import fnmatch
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse
from .common import (PMError, frontmatter, md_header, today, relpath, validate_identifier,
                     write_new, safe_json, sha256_file, git_sha_optional)

ADR_ID = re.compile(r'\bADR-0*(\d+)\b', re.IGNORECASE)
DOC_LINK = re.compile(r'(?<![\w/])docs?/[A-Za-z0-9_./\-\u3400-\u9fff]+\.md')
MD_LINK = re.compile(r'\[[^\]]*\]\(<?([^)\s>]+)>?(?:\s+"[^"]*")?\)')
ISSUE_REF = re.compile(r'(?<![\w])#(\d+)\b')
STATUS = {'proposed', 'under-review', 'accepted', 'rejected', 'superseded'}
DOC_STATUS = {'current', 'draft', 'in_flight', 'historical', 'superseded', 'archived', 'evidence', 'unclassified', 'mirror'}
DOC_DRAFT_KINDS = {'canonical', 'evidence'}
DOC_DRAFT_STATUSES = {'canonical': {'draft', 'in_flight'}, 'evidence': {'evidence'}}
AUDIT_SCOPES = {'all', 'current'}
CURRENT_STATUSES = {'current', 'draft', 'in_flight', 'unclassified'}
LEGACY_SEGMENTS = {'90_原始档案', '_legacy_2026-10-23', '_legacy', '_archive', 'archive', 'archived'}
FENCE_START = re.compile(r'^[ \t]{0,3}(`{3,}|~{3,})')
LOG_SUFFIXES = {'.log', '.txt', '.json', '.xml', '.out', '.tap', '.csv'}
REF_EXT = {'.py', '.ipynb', '.yaml', '.yml', '.json', '.csv', '.tsv', '.sh', '.toml',
           '.log', '.parquet', '.out'}
CODE_REF = re.compile(r'`([^`\n]+?\.(?:py|ipynb|ya?ml|json|csv|tsv|sh|toml|log|parquet|out)(?::\d+(?:-\d+)?|#L\d+)?)`', re.IGNORECASE)
REF_PLACEHOLDER = re.compile(r'[<>*?{}\[\]|]|\.\.\.|…')
ARTIFACT_SUFFIXES = {'.csv', '.tsv', '.json', '.log', '.out', '.xml', '.parquet'}
DYNAMIC_SEGMENTS = {'results', 'result', 'outputs', 'output', 'logs', 'log',
                    'checkpoints', 'wandb', 'runs', 'artifacts', 'artefacts', 'cache'}
REGION_ORDER = {'canonical': 0, 'code': 1, 'evidence': 2, 'mirror': 3, 'legacy': 4, 'frozen': 5, 'other': 6}
REFERENCE_STATUSES = ('resolved', 'resolved_case_mismatch', 'relocated_reference',
                      'ambiguous_reference', 'broken_reference', 'dynamic_artifact',
                      'out_of_scope', 'external', 'unsupported', 'outside', 'unknown',
                      'authority_mismatch', 'shadow_present', 'shadow_missing')



def valid_http_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc)


def log_problem(repo: Path, ref: str | None, config: dict | None = None) -> str | None:
    """Return why a claimed test log is not usable evidence, or None when it is.

    One implementation is shared by the legacy finish gate, run handoffs and
    independent verification so a report cannot pass one gate with a file the
    others would reject.
    """
    if not ref:
        return '缺少测试日志路径'
    if valid_http_url(ref):
        return '测试日志必须是本地文件，不能是 URL'
    path = Path(ref)
    if not path.is_absolute():
        path = repo / path
    if not path.is_file():
        return f'测试日志不存在：{ref}'
    if path.stat().st_size == 0:
        return f'测试日志为空：{ref}'
    if path.suffix.lower() not in LOG_SUFFIXES:
        return f'测试日志必须是证据类文件（{"、".join(sorted(LOG_SUFFIXES))}）：{ref}'
    cfg = config or load_config(repo)
    try:
        relative = path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        # R-1 Fix: Reject logs outside the repository boundary
        return f'测试日志必须在仓库内（{ref} 在仓库外）'
    if not relative:
        return f'测试日志路径解析异常：{ref}'
    if any(relative.startswith(root.rstrip('/') + '/') for root in cfg['doc_roots']):
        return f'测试日志不能是 canonical 文档：{ref}'
    return None

DEFAULT_CONFIG = {
    'schema_version': '1.1',
    'doc_roots': ['docs'],
    'mirror_roots': [],
    'legacy_roots': [],
    'frozen_roots': [],
    'evidence_roots': [],
    'adr_dir': 'docs/decisions',
    'task_source': 'github_issues',
    'repo_kind': 'git',
    'mirror_policy': 'active',
    'entry_doc': None,
    'max_verified_age_days': 90,
}
MIRROR_POLICIES = {'active', 'frozen'}
REQUIRED_CURRENT_METADATA = ('id', 'kind', 'title', 'status', 'owner', 'last_verified_at')
RECOMMENDED_CURRENT_METADATA = ('evidence', 'verified_commit', 'related_decisions', 'superseded_by')


def load_config(repo: Path) -> dict:
    """Read .project-memory/config.json; missing config keeps the docs/ default."""
    cfg = {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULT_CONFIG.items()}
    path = repo / '.project-memory/config.json'
    if path.exists():
        data = safe_json(path)
        if not isinstance(data, dict):
            raise PMError(f'配置必须是 JSON 对象：{path}')
        for key in DEFAULT_CONFIG:
            if key in data:
                cfg[key] = data[key]
        if 'doc_roots' not in data and 'canonical_root' in data:
            cfg['doc_roots'] = [str(data['canonical_root'])]
        if 'adr_dir' not in data:
            cfg['adr_dir'] = str(cfg['doc_roots'][0]) + '/decisions'
    for key in ('doc_roots', 'mirror_roots', 'legacy_roots', 'frozen_roots', 'evidence_roots'):
        value = cfg.get(key)
        if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
            raise PMError(f'配置项 {key} 必须是相对路径数组')
    if not cfg.get('adr_dir') or not isinstance(cfg['adr_dir'], str):
        raise PMError('配置项 adr_dir 必须是相对路径')
    if cfg.get('mirror_policy') not in MIRROR_POLICIES:
        raise PMError('配置项 mirror_policy 必须是以下之一：' + '、'.join(sorted(MIRROR_POLICIES)))
    entry = cfg.get('entry_doc')
    if entry is not None:
        if not isinstance(entry, str) or not entry.strip():
            raise PMError('配置项 entry_doc 必须是相对 .md 路径或 null')
        entry = entry.strip().replace('\\', '/')
        if (entry.startswith('/') or re.match(r'^[A-Za-z]:', entry) or not entry.endswith('.md')
                or any(part in ('', '.', '..') for part in entry.split('/'))):
            raise PMError('配置项 entry_doc 必须是规范化的相对 .md 路径')
        cfg['entry_doc'] = entry
    age = cfg.get('max_verified_age_days')
    if not isinstance(age, int) or isinstance(age, bool) or age < 1:
        raise PMError('配置项 max_verified_age_days 必须是正整数')
    return cfg


def iter_docs(repo: Path, roots: list[str] | None = None):
    cfg = load_config(repo)
    selected = roots if roots is not None else cfg['doc_roots'] + cfg['mirror_roots'] + cfg['legacy_roots']
    seen, docs = set(), []
    for root in selected:
        base = repo / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob('*.md')):
            if not path.is_file():
                continue
            try:
                rel = relpath(repo, path)
            except PMError:
                # T-06: junction or symlink pointing outside the repo; skip instead of crashing.
                continue
            if rel not in seen:
                seen.add(rel)
                docs.append(path)
    return docs


def _under(rel: str, roots: list[str]) -> bool:
    return any(rel == root.rstrip('/') or rel.startswith(root.rstrip('/') + '/') for root in roots)


def authority_of(rel: str, cfg: dict) -> str:
    parts = rel.split('/')
    if _under(rel, cfg.get('frozen_roots', [])):
        return 'frozen'
    if any(part in LEGACY_SEGMENTS for part in parts):
        return 'legacy'
    if _under(rel, cfg['legacy_roots']):
        return 'legacy'
    if _under(rel, cfg['mirror_roots']):
        return 'mirror'
    if _under(rel, cfg['doc_roots']):
        return 'canonical'
    return 'other'


def reference_region(rel: str, cfg: dict) -> str:
    """Governance region for a referenced path, not a truth claim about its content."""
    rel = rel.replace('\\', '/')
    while rel.startswith('./'):
        rel = rel[2:]
    if not rel or rel.startswith('../'):
        return 'outside'
    if _under(rel, cfg.get('frozen_roots', [])):
        return 'frozen'
    if any(part in LEGACY_SEGMENTS for part in rel.split('/')) or _under(rel, cfg['legacy_roots']):
        return 'legacy'
    if _under(rel, cfg['mirror_roots']):
        return 'mirror'
    if _under(rel, cfg.get('evidence_roots', [])):
        return 'evidence'
    if any(part in ('06_evidence', 'evidence', 'evidence_snapshot') for part in rel.split('/')):
        return 'evidence'
    if _under(rel, cfg['doc_roots']) or _under(rel, [cfg['adr_dir']]):
        return 'canonical'
    return 'code'


def infer_status(meta: dict, rel: str, authority: str) -> str:
    declared = str(meta.get('status') or '')
    if declared:
        return declared
    if authority in ('legacy', 'mirror'):
        return 'archived' if authority == 'legacy' else 'mirror'
    parts = rel.split('/')
    if '05_in_flight' in parts or '_inbox' in parts:
        return 'in_flight'
    if '06_evidence' in parts:
        return 'evidence'
    return 'unclassified'


def load_doc(path: Path) -> tuple[dict, str]:
    try:
        return frontmatter(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError) as e:
        raise PMError(f'读取文档失败：{path}：{e}') from None


def body_line_offset(path: Path, body: str) -> int:
    """Line offset of the parsed body inside the file, for real source line numbers."""
    try:
        full = path.read_text(encoding='utf-8')
    except (OSError, UnicodeError):
        return 0
    if not body or not full.endswith(body):
        return 0
    return full[:len(full) - len(body)].count('\n')


def links(text: str):
    return set('ADR-' + str(int(n)).zfill(4) for n in ADR_ID.findall(text)), set(int(n) for n in ISSUE_REF.findall(text)), set(DOC_LINK.findall(text))


def strip_fenced_code(text: str) -> str:
    """Drop fenced code blocks; paths inside examples are not document links."""
    out, fence = [], None
    for line in text.splitlines():
        if fence is None:
            match = FENCE_START.match(line)
            if match:
                fence = match.group(1)
                continue
            out.append(line)
        else:
            match = FENCE_START.match(line)
            if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence) and line.strip() == match.group(1):
                fence = None
    return '\n'.join(out)


def markdown_targets(text: str) -> set[str]:
    visible = strip_fenced_code(text)
    targets = set(MD_LINK.findall(visible)) | set(DOC_LINK.findall(visible))
    clean = set()
    for raw in targets:
        target = raw.strip().strip('<>')
        if '://' in target or target.startswith(('mailto:', '#')):
            continue
        target = target.split('#', 1)[0]
        if target.endswith('.md'):
            clean.add(target)
    return clean


def strip_fenced_code_lines(text: str) -> list[str]:
    """Blank fenced lines without changing line numbers."""
    out, fence = [], None
    for line in text.splitlines():
        if fence is None:
            match = FENCE_START.match(line)
            if match:
                fence = match.group(1)
                out.append('')
            else:
                out.append(line)
        else:
            match = FENCE_START.match(line)
            if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence) and line.strip() == match.group(1):
                fence = None
            out.append('')
    return out


def _clean_reference(raw: str) -> tuple[str | None, str | None]:
    """Return (normalized relative target, category) where category may mark a non-path."""
    target = raw.strip().strip('"\'')
    target = re.sub(r':\d+(?:-\d+)?$', '', target)
    if not target:
        return None, 'unsupported'
    if '://' in target or target.startswith(('mailto:', '#', '~')):
        return target, 'external'
    if target.startswith('/') or re.match(r'^[A-Za-z]:', target):
        return target, 'external'
    if REF_PLACEHOLDER.search(target) or any(ch.isspace() for ch in target):
        return target, 'unsupported'
    target = target.split('#', 1)[0].split('?', 1)[0]
    if re.search(r'%[0-9A-Fa-f]{2}', target):
        target = unquote(target)
    target = target.replace('\\', '/')
    while target.startswith('./'):
        target = target[2:]
    if Path(target).suffix.lower() not in REF_EXT:
        return None, 'unsupported'
    return target, None


def reference_occurrences(text: str) -> list[dict]:
    """Code/artifact references with line numbers; fenced code is ignored."""
    found = []
    seen = set()
    for number, line in enumerate(strip_fenced_code_lines(text), 1):
        raw_items = [match.group(1) for match in CODE_REF.finditer(line)]
        for match in MD_LINK.finditer(line):
            raw = match.group(1).strip().strip('<>').split('#', 1)[0]
            if Path(raw).suffix.lower() in REF_EXT:
                raw_items.append(raw)
        for raw in raw_items:
            target, category = _clean_reference(raw)
            if target is None:
                continue
            key = (number, target)
            if key in seen:
                continue
            seen.add(key)
            found.append({'raw': raw.strip(), 'target': target, 'line': number,
                          'ref_type': 'external' if category == 'external' else 'path',
                          'category': category})
    return found


def reference_targets(text: str) -> set[str]:
    """Backward-compatible set of normalized in-repository reference targets."""
    return {item['target'] for item in reference_occurrences(text)
            if item['category'] is None}


def _glob_match(rel: str, patterns: list[str]) -> bool:
    rel = rel.replace('\\', '/')
    for pattern in patterns or []:
        if fnmatch.fnmatch(rel, pattern) or (pattern.startswith('**/') and fnmatch.fnmatch(rel, pattern[3:])):
            return True
    return False


class ReferenceIndex:
    """Path metadata only. Never reads file contents."""

    def __init__(self, paths: list[str], source: str, *, manifest: dict | None = None):
        self.source = source
        self.manifest = manifest or {}
        self.paths = sorted({p.replace('\\', '/') for p in paths if p})
        self.path_set = set(self.paths)
        self.casefold_paths: dict[str, str] = {}
        self.by_name: dict[str, list[str]] = {}
        for rel in self.paths:
            self.casefold_paths.setdefault(rel.casefold(), rel)
            self.by_name.setdefault(Path(rel).name.casefold(), []).append(rel)
        self.denied = list(self.manifest.get('denied_patterns') or [])
        self.excluded = [x.rstrip('/') for x in (self.manifest.get('excluded_roots') or [])]
        self.symlinks = set(self.manifest.get('symlinks') or [])
        self.scopes = [x.replace('\\', '/').rstrip('/') for x in (self.manifest.get('scopes') or []) if x]

    def covered(self, rel: str) -> bool:
        if not self.scopes:
            return True
        rel = rel.replace('\\', '/')
        return any(rel == scope or rel.startswith(scope + '/') for scope in self.scopes)

    @classmethod
    def from_filesystem(cls, repo: Path) -> 'ReferenceIndex':
        paths = []
        skip = {'.git', '__pycache__', '.pytest_cache', 'node_modules'}
        for path in repo.rglob('*'):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                rel = relpath(repo, path)
            except PMError:
                continue
            if any(part in skip for part in Path(rel).parts):
                continue
            paths.append(rel)
        return cls(paths, 'filesystem')

    @classmethod
    def from_manifest(cls, manifest: dict, source: str = 'manifest') -> 'ReferenceIndex':
        files = manifest.get('files') or []
        paths = []
        for item in files:
            rel = item.get('path') if isinstance(item, dict) else item
            if not isinstance(rel, str) or not rel:
                continue
            rel = rel.replace('\\', '/')
            if rel.startswith('/') or '..' in Path(rel).parts:
                continue
            paths.append(rel)
        return cls(paths, source, manifest=manifest)

    def out_of_scope(self, rel: str) -> str | None:
        rel = rel.replace('\\', '/')
        if rel in self.symlinks:
            return '符号链接未纳入清单（避免路径逃逸）'
        for root in self.excluded:
            if rel == root or rel.startswith(root + '/'):
                return f'目录 {root} 未纳入清单'
        if _glob_match(rel, self.denied):
            return '路径命中 deny 规则'
        return None

    def exact(self, rel: str) -> str | None:
        return rel if rel in self.path_set else None

    def casefold(self, rel: str) -> tuple[str | None, bool]:
        actual = self.casefold_paths.get(rel.casefold())
        return actual, bool(actual and actual != rel)


def load_reference_manifest(value, repo: Path | None = None) -> dict:
    """Validate a read-only path manifest before any reference is classified."""
    if isinstance(value, dict):
        data = value
    else:
        data = safe_json(Path(value))
    if not isinstance(data, dict) or data.get('kind') != 'repo_manifest':
        raise PMError('仓库清单必须是 kind=repo_manifest 的 JSON 对象')
    files = data.get('files')
    if not isinstance(files, list):
        raise PMError('仓库清单必须包含 files 数组')
    if repo is not None and data.get('root'):
        try:
            if Path(data['root']).resolve() != repo.resolve():
                raise PMError('仓库清单的 root 与 --repo 不一致；拒绝把其他仓库的清单当证据')
        except OSError:
            raise PMError('仓库清单的 root 无法解析') from None
    return data


def repo_reference_index(repo: Path) -> dict[str, list[str]]:
    """Backward-compatible basename index; contents are never read."""
    return ReferenceIndex.from_filesystem(repo).by_name


def classify_relocation(index: dict[str, list[str]] | ReferenceIndex, target: str) -> tuple[str, list[str]]:
    """Relocated only when the candidate shares a directory segment with the reference."""
    by_name = index.by_name if isinstance(index, ReferenceIndex) else index
    matches = by_name.get(Path(target).name.casefold(), [])
    if not matches:
        return 'missing', []
    wanted_dirs = {part.casefold() for part in target.replace('\\', '/').split('/')[:-1] if part not in ('', '.')}
    related = [item for item in matches
               if wanted_dirs & {part.casefold() for part in Path(item).parts[:-1]}]
    if related:
        return 'relocated', related[:5]
    return 'ambiguous', matches[:5]


def _repo_roots(doc_path: Path, repo: Path, target: str) -> list[str]:
    try:
        doc_dir = doc_path.parent.resolve().relative_to(repo.resolve()).as_posix()
    except (OSError, ValueError):
        doc_dir = '.'
    bases = []
    for base in (doc_dir, '.'):
        rel = (Path(base) / target).as_posix() if base != '.' else target
        while rel.startswith('./'):
            rel = rel[2:]
        parts = []
        for part in rel.split('/'):
            if part in ('', '.'):
                continue
            if part == '..':
                if not parts:
                    parts = ['..']
                    break
                parts.pop()
            else:
                parts.append(part)
        rel = '/'.join(parts)
        if rel not in bases:
            bases.append(rel)
    return bases


def _artifact_like(target: str) -> bool:
    suffix = Path(target).suffix.lower()
    if suffix not in ARTIFACT_SUFFIXES:
        return False
    return any(part.lower() in DYNAMIC_SEGMENTS for part in Path(target).parts[:-1])


def resolve_reference_detail(index: ReferenceIndex, repo: Path, doc_path: Path, target: str,
                             cfg: dict, *, shadow: bool = False) -> dict:
    """Classify one reference without claiming that a path is semantically correct."""
    if target.startswith(('http://', 'https://', '/', '~')) or re.match(r'^[A-Za-z]:', target):
        return {'status': 'external', 'resolved_path': None, 'candidates': [],
                'basis': None, 'case_mismatch': False, 'out_of_scope_reason': None}
    candidates_seen: list[str] = []
    scope_reason = None
    for rel in _repo_roots(doc_path, repo, target):
        if rel.startswith('../') or rel == '..':
            return {'status': 'outside', 'resolved_path': None, 'candidates': [],
                    'basis': None, 'case_mismatch': False, 'out_of_scope_reason': None}
        reason = index.out_of_scope(rel)
        if reason:
            scope_reason = reason
            continue
        actual = index.exact(rel)
        if actual:
            status = 'resolved'
            return {'status': status, 'resolved_path': actual, 'candidates': [],
                    'basis': rel, 'case_mismatch': False, 'out_of_scope_reason': None}
        actual, mismatch = index.casefold(rel)
        if actual:
            return {'status': 'resolved_case_mismatch', 'resolved_path': actual,
                    'candidates': [], 'basis': rel, 'case_mismatch': mismatch,
                    'out_of_scope_reason': None}
    if scope_reason:
        return {'status': 'out_of_scope', 'resolved_path': None, 'candidates': [],
                'basis': None, 'case_mismatch': False, 'out_of_scope_reason': scope_reason}
    if not index.covered(target):
        return {'status': 'out_of_scope', 'resolved_path': None, 'candidates': [],
                'basis': None, 'case_mismatch': False,
                'out_of_scope_reason': '清单声明的 scope 未覆盖该路径根；不能据此判定缺失'}
    manifest_complete = index.manifest.get('complete', True) if index.manifest else True
    if manifest_complete:
        kind, matches = classify_relocation(index, target)
        candidates_seen = matches
    else:
        candidates_seen = index.by_name.get(Path(target).name.casefold(), [])[:5]
        kind = 'ambiguous' if candidates_seen else 'unknown'
    if candidates_seen:
        # Prefer the most authoritative region so a frozen clone cannot turn a
        # single live-code candidate into a false ambiguity.
        ranked = sorted({reference_region(item, cfg) for item in candidates_seen},
                        key=lambda region: REGION_ORDER.get(region, 9))
        best = ranked[0] if ranked else 'other'
        candidates_seen = [item for item in candidates_seen
                           if reference_region(item, cfg) == best][:5]
    if kind == 'missing' and _artifact_like(target):
        kind = 'dynamic_artifact'
    kind = {'relocated': 'relocated_reference', 'ambiguous': 'ambiguous_reference',
            'missing': 'broken_reference'}.get(kind, kind)
    authority_mismatch = False
    if candidates_seen:
        doc_region = None
        try:
            doc_region = reference_region(relpath(repo, doc_path), cfg)
        except PMError:
            doc_region = 'other'
        regions = [reference_region(item, cfg) for item in candidates_seen]
        if doc_region == 'canonical' and any(region in ('frozen', 'legacy', 'mirror', 'evidence') for region in regions):
            authority_mismatch = True
    return {'status': kind, 'resolved_path': None, 'candidates': candidates_seen,
            'basis': None, 'case_mismatch': False, 'out_of_scope_reason': None,
            'authority_mismatch': authority_mismatch}


def resolve_reference(repo: Path, doc_path: Path, target: str) -> tuple[str, str | None]:
    """Backward-compatible filesystem resolver used by older callers."""
    index = ReferenceIndex.from_filesystem(repo)
    detail = resolve_reference_detail(index, repo, doc_path, target, DEFAULT_CONFIG)
    status = detail['status']
    if status == 'resolved':
        return 'exists', detail['resolved_path']
    if status == 'outside':
        return 'outside', None
    return 'missing', None


def create_adr(repo: Path, title: str, topic: str, issue: int, options: str, rationale: str, owner: str, supersedes: str = '') -> str:
    if not title.strip() or not rationale.strip() or not owner.strip() or not topic.strip():
        raise PMError('ADR 的标题、topic、owner 和理由不能为空')
    if issue <= 0:
        raise PMError('Issue 编号必须为正数')
    cfg = load_config(repo)
    root = repo / cfg['adr_dir']
    root.mkdir(parents=True, exist_ok=True)
    prior = sorted(set('ADR-' + str(int(n)).zfill(4) for n in ADR_ID.findall(supersedes)))
    number = max([int(n) for p in root.glob('*.md') for n in ADR_ID.findall(p.name)] or [0]) + 1
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:45] or 'decision'
    for n in range(number, number + 1000):
        ident = f'ADR-{n:04d}'
        path = root / f'{ident}-{slug}.md'
        header = md_header(dict(id=ident, kind='adr', title=title, topic=topic, status='proposed', owner=owner, updated_at=today(), related_issues=[issue], supersedes=prior))
        body = (f'# {title}\n\n## 背景\n\n关联：#{issue}\n\n'
                f'## 备选方案\n\n{options or "待评估。"}\n\n'
                f'## 提议与理由\n\n{rationale}\n\n'
                '## 影响与风险\n\n待审查。\n\n'
                '## 证据与批准\n\n等待人工明确批准和 PR 审查。\n')
        if write_new(path, header + body):
            return relpath(repo, path)
    raise PMError('无法分配 ADR 编号：冲突过多')


def create_document(repo: Path, ident: str, title: str, kind: str, status: str, owner: str,
                    path: str, issue: int | None = None, config: dict | None = None) -> dict:
    """Scaffold one document with fixed frontmatter; never overwrite or promote."""
    ident = validate_identifier(ident, 'document id')
    title, owner = title.strip(), owner.strip()
    if not title or not owner:
        raise PMError('文档标题和 owner 不能为空')
    if any(ch in title for ch in ('\n', '\r')) or any(ch in owner for ch in ('\n', '\r')):
        raise PMError('文档标题和 owner 必须是单行')
    if kind not in DOC_DRAFT_KINDS:
        raise PMError('文档 kind 必须是以下之一：' + '、'.join(sorted(DOC_DRAFT_KINDS)))
    if status not in DOC_DRAFT_STATUSES[kind]:
        raise PMError(f'新建 {kind} 文档的 status 必须是以下之一：' + '、'.join(sorted(DOC_DRAFT_STATUSES[kind])))
    if issue is not None and issue <= 0:
        raise PMError('Issue 编号必须为正数')
    cfg = config or load_config(repo)
    rel = path.strip().replace('\\', '/')
    parts = rel.split('/')
    if not rel or rel.startswith('/') or re.match(r'^[A-Za-z]:', rel):
        raise PMError('文档路径必须相对于仓库')
    if any(part in ('', '.', '..') for part in parts) or not rel.endswith('.md'):
        raise PMError('文档路径必须是规范化的 .md 路径，不能包含空段、. 或 ..')
    if _under(rel, cfg['mirror_roots']) or _under(rel, cfg['legacy_roots']):
        raise PMError('拒绝写入 mirror 或 legacy 根目录')
    if not _under(rel, cfg['doc_roots']):
        raise PMError('文档路径必须位于已配置的文档根目录之下：' + '、'.join(cfg['doc_roots']))
    if _under(rel, [cfg['adr_dir']]):
        raise PMError('ADR 文件必须通过 decision 命令创建')
    for existing in iter_docs(repo, cfg['doc_roots']):
        meta, _ = load_doc(existing)
        if str(meta.get('id') or '') == ident:
            raise PMError(f'文档 ID {ident} 已存在于 {relpath(repo, existing)}')

    meta = {'id': ident, 'kind': kind, 'title': title, 'status': status, 'owner': owner, 'updated_at': today()}
    if issue is not None:
        meta['related_issues'] = [issue]
    if kind == 'evidence':
        body = (f'# {title}\n\n## 记录\n\n<!-- 记录了什么；未确认内容不要写成结论。 -->\n\n'
                '## 来源与采集方式\n\n<!-- 命令、时间、环境、commit。 -->\n\n'
                '## 可复现性\n\n<!-- 复现步骤与已知限制。 -->\n\n'
                f'## 变更记录\n\n- {today()}：初始记录。\n')
    else:
        body = (f'# {title}\n\n## 结论\n\n<!-- 一句话结论；未确认内容不要写在这里。 -->\n\n'
                '## 证据\n\n<!-- 按 L/S/D 标注，附文件、提交、日志或命令输出。 -->\n\n'
                '## 适用范围与未决\n\n<!-- 边界、限制、仍需确认的问题。 -->\n\n'
                f'## 变更记录\n\n- {today()}：初始草稿。\n')
    target = repo / rel
    if not write_new(target, md_header(meta) + body):
        raise PMError(f'拒绝覆盖已有文件：{rel}')
    return {
        'schema_version': '1.1',
        'kind': 'document_draft',
        'path': relpath(repo, target),
        'id': ident,
        'doc_kind': kind,
        'status': status,
        'promotion_required': kind == 'canonical',
    }


def _resolve_link(source: Path, repo: Path, target: str, cfg: dict) -> Path:
    if target.startswith('/'):
        return repo / target.lstrip('/')
    roots = cfg['doc_roots'] + cfg['mirror_roots'] + cfg['legacy_roots']
    candidates = [source.parent / target]
    if _under(target, roots) or target.startswith(('docs/', 'doc/')):
        candidates.append(repo / target)
    # Links are often written from the project directory that contains the docs root,
    # not from the Git/workspace root (common in nested workspaces).
    for root in roots:
        candidates.append((repo / root).parent / target)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def _in_current_scope(rel: str, authority: str, status: str, cfg: dict) -> bool:
    """Current scope: canonical live docs plus every ADR (status checks still matter)."""
    if authority != 'canonical':
        return False
    if rel.startswith(cfg['adr_dir'].rstrip('/') + '/'):
        return True
    return status in CURRENT_STATUSES


def _iso_date(value) -> dt.date | None:
    if not isinstance(value, str):
        return None
    try:
        return dt.date.fromisoformat(value.strip())
    except ValueError:
        return None


def audit(repo: Path, config: dict | None = None, allow_empty: bool = False, scope: str = 'all',
          manifest: dict | None = None, path_source: str | None = None) -> dict:
    cfg = config or load_config(repo)
    if scope not in AUDIT_SCOPES:
        raise PMError('audit scope 必须是以下之一：' + '、'.join(sorted(AUDIT_SCOPES)))
    if manifest is not None:
        manifest = load_reference_manifest(manifest, repo)
    source = path_source or (manifest.get('source', 'manifest') if manifest else 'filesystem')
    shadow = source == 'shadow'
    index = (ReferenceIndex.from_manifest(manifest, source=source) if manifest
             else ReferenceIndex.from_filesystem(repo))
    manifest_complete = bool(manifest.get('complete', True)) if manifest else True
    version = (manifest.get('git_head') if manifest else git_sha_optional(repo)) or None
    findings = []
    adrs, docs_by_id, by_rel = {}, {}, {}

    def add(sev, code, location, message):
        findings.append({'severity': sev, 'code': code, 'location': location, 'message': message})

    loaded = []
    roots = cfg['doc_roots'] if scope == 'current' else cfg['doc_roots'] + cfg['mirror_roots'] + cfg['legacy_roots']
    paths = iter_docs(repo, roots)
    scanned_total = len(paths)
    for path in paths:
        name = relpath(repo, path)
        authority = authority_of(name, cfg)
        try:
            meta, text = load_doc(path)
        except PMError as e:
            add('high', 'invalid_frontmatter', name, str(e))
            continue
        status = infer_status(meta, name, authority)
        if scope == 'current' and not _in_current_scope(name, authority, status, cfg):
            continue
        rec = {
            'rel': name,
            'path': path,
            'meta': meta,
            'text': text,
            'authority': authority,
            'status': status,
            'sha256': sha256_file(path),
            'line_offset': body_line_offset(path, text),
        }
        loaded.append(rec)
        by_rel[name] = rec
        if name.startswith(cfg['adr_dir'].rstrip('/') + '/') and path.name != 'README.md':
            ident = str(meta.get('id', ''))
            if not re.fullmatch(r'ADR-\d{4,}', ident):
                add('high', 'adr_invalid_id', name, 'ADR 需要 id: ADR-0001 格式')
            elif ident in adrs:
                add('high', 'adr_duplicate_id', name, f'已在 {adrs[ident][0]} 定义')
            else:
                adrs[ident] = (name, meta)
            if meta.get('status') not in STATUS:
                add('high', 'adr_invalid_status', name, 'ADR 状态未知')
            if not meta.get('owner') or not isinstance(meta.get('related_issues'), list):
                add('medium', 'adr_missing_provenance', name, 'ADR 必须包含 owner 和 related_issues 数组')
            if meta.get('status') == 'accepted' and not meta.get('approved_by'):
                add('high', 'accepted_adr_unverified', name, 'accepted 的 ADR 必须提供 approved_by，指向可审计的人工批准证据')
            if meta.get('status') == 'superseded' and not meta.get('superseded_by'):
                add('medium', 'superseded_missing_successor', name, '被替代的 ADR 应标明替代者')
        if meta.get('id'):
            ident = str(meta['id'])
            if ident in docs_by_id:
                add('high', 'duplicate_document_id', name, f'已在 {docs_by_id[ident]} 使用')
            docs_by_id[ident] = name

    canonical = [r for r in loaded if r['authority'] == 'canonical']
    if not canonical and not allow_empty:
        add('high', 'no_documents_found', ', '.join(cfg['doc_roots']),
            ('未找到 current/draft/in-flight 的规范文档；scope=current 不能空过。'
             '请检查文档状态，或改用 --scope all。' if scope == 'current' else
             '配置的规范根目录下没有 Markdown；审计不能空过。'
             '请在 .project-memory/config.json 设置 doc_roots，或传入 --docs-root。'))

    max_verified_age = cfg.get('max_verified_age_days', 90)
    today_date = dt.date.fromisoformat(today())
    entry_rel = cfg.get('entry_doc')
    head = version if version else git_sha_optional(repo)
    commit_cache: dict[str, str] = {}

    def commit_state(sha: str) -> str:
        """exists | current | ancestor | diverged | unknown"""
        if sha in commit_cache:
            return commit_cache[sha]
        if not re.fullmatch(r'[0-9a-f]{40}', sha):
            commit_cache[sha] = 'invalid'
            return 'invalid'
        env = {'PATH': os.environ.get('PATH', '')}
        proc = subprocess.run(['git', '-C', str(repo), 'cat-file', '-e', sha + '^{commit}'],
                              capture_output=True, text=True, env=env)
        if proc.returncode != 0:
            commit_cache[sha] = 'missing'
            return 'missing'
        if not head:
            commit_cache[sha] = 'unknown'
            return 'unknown'
        if sha == head:
            commit_cache[sha] = 'current'
            return 'current'
        proc = subprocess.run(['git', '-C', str(repo), 'merge-base', '--is-ancestor', sha, head],
                              capture_output=True, text=True, env=env)
        result = 'ancestor' if proc.returncode == 0 else 'diverged'
        commit_cache[sha] = result
        return result

    metadata_docs = []
    legacy_gaps: dict[str, int] = {}
    for rec in loaded:
        meta = rec['meta']
        declared = meta.get('status')
        required_present = [key for key in REQUIRED_CURRENT_METADATA if meta.get(key) not in (None, '', [])]
        required_missing = [key for key in REQUIRED_CURRENT_METADATA if key not in required_present]
        recommended_present = [key for key in RECOMMENDED_CURRENT_METADATA if meta.get(key) not in (None, '', [])]
        recommended_missing = [key for key in RECOMMENDED_CURRENT_METADATA if key not in recommended_present]
        warnings = []
        is_index = rec['path'].name.lower() == 'readme.md'
        if rec['authority'] == 'canonical' and not is_index:
            if not declared:
                warnings.append('unknown_document_status')
                add('low', 'unknown_document_status', rec['rel'],
                    '文档没有声明 status，审计按推断状态处理；这本身不证明内容错误')
            if declared == 'current' and not meta.get('owner'):
                warnings.append('current_document_missing_owner')
                add('medium', 'current_document_missing_owner', rec['rel'],
                    'status=current 的规范文档缺少 owner；读者无法找到负责核验的人')
            if declared == 'current':
                missing_core = [key for key in ('id', 'kind', 'title') if not meta.get(key)]
                if missing_core:
                    warnings.append('missing_required_metadata')
                    add('low', 'missing_required_metadata', rec['rel'],
                        'status=current 的规范文档缺少：' + '、'.join(missing_core))
            if declared == 'superseded' and not meta.get('superseded_by'):
                warnings.append('superseded_missing_successor')
                add('medium', 'superseded_missing_successor', rec['rel'],
                    '文档标记为 superseded，但没有 superseded_by；读者不知道当前有效版本')
            related = meta.get('related_decisions')
            if related is not None:
                if not isinstance(related, list) or not all(isinstance(x, str) for x in related):
                    warnings.append('invalid_related_decisions')
                    add('medium', 'invalid_related_decisions', rec['rel'],
                        'related_decisions 必须是 ADR 编号字符串数组')
                else:
                    for adr in related:
                        if adr not in adrs:
                            warnings.append('unknown_related_decision')
                            add('low', 'unknown_related_decision', rec['rel'],
                                f'related_decisions 引用了不存在的 {adr}')
            commit = meta.get('verified_commit')
            if commit:
                state = commit_state(str(commit))
                if state == 'invalid':
                    warnings.append('invalid_verified_commit')
                    add('medium', 'invalid_verified_commit', rec['rel'],
                        'verified_commit 必须是完整的 40 位提交 SHA')
                elif state == 'missing':
                    warnings.append('verified_commit_missing')
                    add('medium', 'verified_commit_missing', rec['rel'],
                        f'verified_commit 指向的提交不存在：{commit}')
                elif state == 'diverged':
                    warnings.append('verified_source_diverged')
                    add('medium', 'verified_source_diverged', rec['rel'],
                        f'verified_commit {str(commit)[:12]} 不在当前 HEAD 历史中；验证基线已分叉')
                elif state == 'ancestor':
                    warnings.append('verified_source_changed')
                    add('low', 'verified_source_changed', rec['rel'],
                        f'代码已在 verified_commit {str(commit)[:12]} 之后前进；请复核结论是否仍适用')
        elif rec['authority'] != 'canonical':
            if declared == 'current':
                warnings.append('authority_status_conflict')
                add('medium', 'authority_status_conflict', rec['rel'],
                    f'{rec["authority"]} 区域的文档声明 status=current；不能据此把历史或镜像材料当作当前知识')
            if rec['authority'] in ('legacy', 'mirror') and 'last_verified_at' not in meta:
                root = next((r for r in (cfg['legacy_roots'] + cfg['mirror_roots']) if _under(rec['rel'], [r])),
                            rec['authority'])
                legacy_gaps[root] = legacy_gaps.get(root, 0) + 1
        metadata_docs.append({
            'document': rec['rel'],
            'authority': rec['authority'],
            'status': rec['status'],
            'declared_status': declared,
            'required_present': required_present,
            'required_missing': required_missing,
            'recommended_present': recommended_present,
            'recommended_missing': recommended_missing,
            'warnings': warnings,
        })

    for root, count in sorted(legacy_gaps.items()):
        add('low', 'legacy_metadata_warning', root,
            f'{count} 个 legacy/mirror 文档没有 last_verified_at；这是提示，不自动判定旧文档错误')

    for rec in loaded:
        if rec['rel'] == entry_rel or rec['status'] not in CURRENT_STATUSES:
            continue
        declared = rec['meta'].get('last_verified_at')
        if declared is None:
            if rec['status'] == 'current':
                add('low', 'current_document_unverified', rec['rel'],
                    '当前文档没有 last_verified_at；读者无法判断结论有多旧')
            continue
        verified = _iso_date(declared)
        if verified is None or (verified - today_date).days > 1:
            add('medium', 'invalid_last_verified_at', rec['rel'],
                'last_verified_at 必须是 YYYY-MM-DD 格式的日期，且不能晚于今天')
        elif (today_date - verified).days > max_verified_age:
            add('low', 'stale_current_document', rec['rel'],
                f'当前文档已 {(today_date - verified).days} 天未核对（上限 {max_verified_age} 天）；需要重新核验，不代表内容一定错误')
    if entry_rel:
        rec = by_rel.get(entry_rel)
        if rec is None:
            add('high', 'entry_doc_missing', entry_rel,
                '配置的 entry_doc 在扫描范围内找不到；请修正路径或创建入口文档')
        else:
            if rec['authority'] != 'canonical':
                add('high', 'entry_doc_not_canonical', entry_rel,
                    f'入口文档的 authority 是 {rec["authority"]}；读者必须从 canonical 文档开始')
            if rec['meta'].get('status') != 'current':
                add('high', 'entry_doc_not_current', entry_rel,
                    '入口文档必须声明 status: "current"；draft、evidence 或推断状态不能作为入口')
            declared = rec['meta'].get('last_verified_at')
            if declared is None:
                add('low', 'entry_doc_unverified', entry_rel,
                    '入口文档没有 last_verified_at；读者无法判断结论有多旧')
            else:
                verified = _iso_date(declared)
                if verified is None or (verified - today_date).days > 1:
                    add('medium', 'invalid_last_verified_at', entry_rel,
                        'last_verified_at 必须是 YYYY-MM-DD 格式的日期，且不能晚于今天')
                elif (today_date - verified).days > max_verified_age:
                    add('medium', 'entry_doc_stale', entry_rel,
                        f'入口文档上次核对是 {(today_date - verified).days} 天前（上限 {max_verified_age} 天）；信任之前请重新核对')

    by_topic = {}
    for ident, (name, meta) in adrs.items():
        if meta.get('status') == 'accepted' and meta.get('topic'):
            by_topic.setdefault(meta['topic'], []).append(name)
        for pred in meta.get('supersedes', []):
            if pred not in adrs:
                add('medium', 'unknown_superseded_adr', name, f'{pred} 不存在')
            elif meta.get('status') == 'accepted' and adrs[pred][1].get('status') == 'accepted':
                add('medium', 'supersession_not_reconciled', name, f'{pred} 仍是 accepted 状态')
    for topic, names in by_topic.items():
        if len(names) > 1:
            add('medium', 'possibly_conflicting_decisions', ', '.join(names), f'多个 accepted ADR 共用 topic {topic}；需要人工确认是否冲突')

    for rec in loaded:
        adr_refs, _, _ = links(rec['text'])
        for adr in adr_refs:
            if adr not in adrs and adr != rec['meta'].get('id'):
                add('low', 'broken_adr_reference', rec['rel'], f'{adr} 没有对应的 ADR 文件')
            elif adr in adrs and adrs[adr][1].get('status') == 'superseded' and adr != rec['meta'].get('id'):
                add('medium', 'references_superseded_adr', rec['rel'], f'{adr} 已被替代；请确认引用是否仍然有意保留')
        for target in sorted(markdown_targets(rec['text'])):
            if '...' in target or '…' in target:
                # Abbreviated references written for humans (e.g. doc/x/...name.md), not real links.
                continue
            resolved = _resolve_link(rec['path'], repo, target, cfg)
            try:
                resolved.resolve().relative_to(repo.resolve())
            except ValueError:
                add('medium', 'reference_outside_repository', rec['rel'], f'链接指向仓库之外：{target}')
                continue
            if not resolved.is_file():
                add('medium', 'broken_document_reference', rec['rel'], f'缺失：{target}')

    reference_entries = []
    reference_summary = {'by_status': {}, 'by_region': {}, 'authority_mismatch': 0,
                         'confirmed': 0, 'unconfirmed': 0}
    for rec in loaded:
        doc_region = reference_region(rec['rel'], cfg)
        for occ in reference_occurrences(rec['text']):
            target = occ['target']
            detail = {'status': 'external' if occ['category'] == 'external' else 'unsupported',
                      'resolved_path': None, 'candidates': [], 'basis': None,
                      'case_mismatch': False, 'out_of_scope_reason': None,
                      'authority_mismatch': False}
            if occ['category'] is None:
                detail = resolve_reference_detail(index, repo, rec['path'], target, cfg, shadow=shadow)
                if shadow:
                    base = detail['status']
                    if base in ('resolved', 'resolved_case_mismatch'):
                        detail['status'] = 'shadow_present'
                    elif base in ('relocated_reference', 'ambiguous_reference',
                                  'broken_reference', 'dynamic_artifact'):
                        detail['status'] = 'shadow_missing'
            status = detail['status']
            resolved_path = detail.get('resolved_path')
            candidates = detail.get('candidates') or []
            regions = [reference_region(item, cfg) for item in candidates]
            if resolved_path:
                regions = [reference_region(resolved_path, cfg)]
            elif candidates:
                regions = [reference_region(item, cfg) for item in candidates]
            mismatch = bool(detail.get('authority_mismatch'))
            if not mismatch and doc_region == 'canonical' and any(r in ('frozen', 'legacy') for r in regions):
                mismatch = True
            if mismatch:
                detail['base_status'] = status
                detail['status'] = 'authority_mismatch'
                status = 'authority_mismatch'
            confirmed = (not shadow) and manifest_complete and occ['category'] is None
            line = occ['line'] + rec.get('line_offset', 0)
            entry = {
                'document': rec['rel'],
                'line': line,
                'raw': occ['raw'],
                'target': target,
                'ref_type': occ['ref_type'],
                'status': status,
                'base_status': detail.get('base_status'),
                'resolved_path': resolved_path,
                'candidates': candidates,
                'candidate_regions': regions,
                'region': regions[0] if regions else None,
                'doc_authority': rec['authority'],
                'repository_version': version,
                'data_source': source,
                'manifest_complete': manifest_complete,
                'confirmed': confirmed,
                'case_mismatch': detail.get('case_mismatch', False),
                'authority_mismatch': mismatch,
                'out_of_scope_reason': detail.get('out_of_scope_reason'),
                'uncertainty_reason': _uncertainty(status, detail),
                'suggested_action': _suggested_action(status),
            }
            reference_entries.append(entry)
            reference_summary['by_status'][status] = reference_summary['by_status'].get(status, 0) + 1
            if entry['region']:
                reference_summary['by_region'][entry['region']] = reference_summary['by_region'].get(entry['region'], 0) + 1
            reference_summary['authority_mismatch'] += int(mismatch)
            reference_summary['confirmed' if confirmed else 'unconfirmed'] += 1

            if shadow:
                continue
            if status == 'resolved':
                continue
            if status == 'external' or status == 'unsupported':
                continue
            if status == 'resolved_case_mismatch':
                add('low', 'reference_case_mismatch', rec['rel'],
                    f'第 {line} 行的大小写与清单不一致：{target} -> {resolved_path}')
            elif status == 'authority_mismatch':
                severity = 'medium' if candidates else 'low'
                add(severity, 'reference_authority_mismatch', rec['rel'],
                    f'第 {line} 行的引用落在 {", ".join(sorted(set(regions)))}；不能自动当作当前知识：{target}')
            elif status == 'relocated_reference':
                add('low', 'relocated_reference', rec['rel'],
                    f'第 {line} 行路径不存在：{target}；同名且目录相关的候选：{", ".join(candidates)}')
            elif status == 'ambiguous_reference':
                add('low', 'ambiguous_reference', rec['rel'],
                    f'第 {line} 行路径不存在：{target}；仅有同名文件，目录不对应：{", ".join(candidates)}')
            elif status == 'dynamic_artifact':
                add('low', 'dynamic_artifact_reference', rec['rel'],
                    f'第 {line} 行引用了动态产物：{target}；应记录生成命令与本地产物位置，而不是把它当作规范知识')
            elif status == 'out_of_scope':
                add('low', 'reference_out_of_scope', rec['rel'],
                    f'第 {line} 行的路径未纳入授权清单（{detail.get("out_of_scope_reason")}）：{target}；不能判定为缺失')
            elif status == 'unknown':
                add('low', 'reference_unknown', rec['rel'],
                    f'第 {line} 行的路径无法在清单中确认（清单不完整）：{target}')
            elif status == 'outside':
                add('medium', 'reference_outside_repository', rec['rel'],
                    f'第 {line} 行引用指向仓库之外：{target}')
            else:
                suffix = Path(target).suffix.lower()
                severity = 'low' if suffix in {'.csv', '.json', '.tsv', '.parquet'} else 'medium'
                add(severity, 'broken_reference', rec['rel'],
                    f'第 {line} 行缺失：{target}' + ('' if manifest_complete else '（清单不完整，不能确认）'))

    link_graph = {}
    for rec in loaded:
        linked = set()
        for target in markdown_targets(rec['text']):
            resolved = _resolve_link(rec['path'], repo, target, cfg)
            try:
                linked.add(relpath(repo, resolved))
            except PMError:
                continue
        link_graph[rec['rel']] = linked

    navigation = {'entry_doc': entry_rel, 'entry_links': 0, 'reachable': [], 'unreachable': []}
    if entry_rel and entry_rel in by_rel:
        seen, queue = {entry_rel}, [entry_rel]
        while queue:
            current = queue.pop(0)
            for nxt in sorted(link_graph.get(current, set())):
                if nxt in by_rel and nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        navigation['entry_links'] = len([x for x in link_graph.get(entry_rel, set()) if x in by_rel])
        adr_prefix = cfg['adr_dir'].rstrip('/') + '/'
        candidates_nav = [r for r in loaded
                          if r['authority'] == 'canonical' and r['status'] in CURRENT_STATUSES
                          and r['rel'] != entry_rel and not r['rel'].startswith(adr_prefix)]
        reachable = sorted(r['rel'] for r in candidates_nav if r['rel'] in seen)
        unreachable = sorted(r['rel'] for r in candidates_nav if r['rel'] not in seen)
        navigation.update({'reachable': reachable, 'unreachable': unreachable})
        if navigation['entry_links'] == 0 and candidates_nav:
            add('low', 'navigation_no_links_from_entry', entry_rel,
                '入口文档没有指向规范文档的 Markdown 链接；读者无法从入口到达主题知识')
        if len(unreachable) > 10:
            add('low', 'navigation_unreachable_documents', entry_rel,
                f'{len(unreachable)} 个当前文档无法从入口经链接到达；示例：{", ".join(unreachable[:5])}')
        else:
            for rel in unreachable:
                add('low', 'unreachable_current_document', rel,
                    '该当前文档无法从 entry_doc 经 Markdown 链接到达')

    by_hash = {}
    for rec in loaded:
        by_hash.setdefault(rec['sha256'], []).append(rec)
    for digest, recs in sorted(by_hash.items()):
        if len(recs) < 2:
            continue
        # An identical mirror copy of a canonical document is expected, not a duplicate.
        comparable = []
        for rec in recs:
            if rec['authority'] == 'mirror':
                suffix = next((rec['rel'][len(r.rstrip('/')) + 1:] for r in cfg['mirror_roots']
                               if _under(rec['rel'], [r])), None)
                if suffix and any(by_rel.get(root.rstrip('/') + '/' + suffix) for root in cfg['doc_roots']):
                    continue
            comparable.append(rec)
        if len(comparable) < 2:
            continue
        non_legacy = [r for r in comparable if r['authority'] != 'legacy']
        severity = 'medium' if len(non_legacy) >= 2 else 'low'
        shown = ', '.join(r['rel'] for r in comparable[:4])
        if len(comparable) > 4:
            shown += f' (+{len(comparable) - 4})'
        add(severity, 'duplicate_document_content', comparable[0]['rel'],
            f'{len(comparable)} 个文件 SHA256 相同（{digest[:12]}）：{shown}')

    for mirror_root in cfg['mirror_roots']:
        frozen = cfg.get('mirror_policy') == 'frozen'
        extra = []
        for rec in loaded:
            if not _under(rec['rel'], [mirror_root]):
                continue
            suffix = rec['rel'][len(mirror_root.rstrip('/')) + 1:]
            counterparts = [by_rel.get(root.rstrip('/') + '/' + suffix) for root in cfg['doc_roots']]
            counterpart = next((c for c in counterparts if c), None)
            if counterpart is None:
                extra.append(rec['rel'])
            elif counterpart['sha256'] != rec['sha256']:
                add('medium' if frozen else 'high', 'mirror_divergence', rec['rel'],
                    f'镜像与规范文档 {counterpart["rel"]} 在同名路径上不一致'
                    + ('；镜像为 frozen，分歧已记录且不得回灌规范' if frozen else ''))
        if extra:
            shown = ', '.join(extra[:5]) + (f' (+{len(extra) - 5})' if len(extra) > 5 else '')
            add('medium', 'mirror_extra_files', mirror_root, f'{len(extra)} 个镜像文件没有对应的规范文件：{shown}')

    for path in sorted((repo / '.project-memory/prs').glob('*.json')):
        name = relpath(repo, path)
        try:
            pr = safe_json(path)
        except PMError as e:
            add('high', 'invalid_pr_snapshot', name, str(e))
            continue
        body = str(pr.get('title') or '') + '\n' + str(pr.get('body') or '')
        _, issues, _ = links(body)
        if pr.get('merged_at') and not issues:
            add('medium', 'merged_pr_without_issue_link', name, '已合并的 PR 快照没有显式引用 Issue；请检查可追溯性')
        files = pr.get('changed_files_list') or []
        if pr.get('merged_at') and any(str(f).startswith(('src/', 'app/', 'lib/')) for f in files) and not any(str(f).startswith(('docs/', 'doc/')) for f in files):
            add('low', 'code_change_without_docs_candidate', name, '已合并的代码改动在快照中没有文档文件；请核实是否评估过文档影响')

    counts = {s: sum(f['severity'] == s for f in findings) for s in ('high', 'medium', 'low')}
    authorities = {}
    for rec in loaded:
        authorities[rec['authority']] = authorities.get(rec['authority'], 0) + 1
    statuses = {}
    for rec in loaded:
        statuses[rec['status']] = statuses.get(rec['status'], 0) + 1
    return {
        'schema_version': '1.2',
        'kind': 'knowledge_audit',
        'scope': scope,
        'findings': findings,
        'counts': counts,
        'docs_scanned': len(loaded),
        'docs_scanned_total': scanned_total,
        'docs_excluded': scanned_total - len(loaded),
        'canonical_docs_scanned': len(canonical),
        'authorities': authorities,
        'statuses': statuses,
        'doc_roots': cfg['doc_roots'],
        'mirror_roots': cfg['mirror_roots'],
        'legacy_roots': cfg['legacy_roots'],
        'frozen_roots': cfg.get('frozen_roots', []),
        'evidence_roots': cfg.get('evidence_roots', []),
        'mirror_policy': cfg.get('mirror_policy'),
        'entry_doc': entry_rel,
        'max_verified_age_days': max_verified_age,
        'path_source': source,
        'repository_version': version,
        'manifest': None if not manifest else {
            'project': manifest.get('project'),
            'root': manifest.get('root'),
            'manifest_id': manifest.get('manifest_id'),
            'generated_at': manifest.get('generated_at'),
            'git_head': manifest.get('git_head'),
            'complete': manifest.get('complete'),
            'file_count': manifest.get('file_count'),
            'source': manifest.get('source'),
        },
        'reference_audit': {
            'source': source,
            'manifest_complete': manifest_complete,
            'entries': reference_entries,
            'summary': reference_summary,
        },
        'metadata_contract': {
            'required': list(REQUIRED_CURRENT_METADATA),
            'recommended': list(RECOMMENDED_CURRENT_METADATA),
            'documents': metadata_docs,
        },
        'navigation': navigation,
        'note': ('这些是结构和启发式检查，不能证明语义正确。'
                 'scope=current 覆盖规范根目录中 current/draft/in-flight/未分类的文档和全部 ADR；'
                 'mirror、legacy、evidence 和历史文档不在范围内。' if scope == 'current' else
                 '这些是结构和启发式检查，不能证明语义正确。')
        + (' 路径来自只读清单，未读取文件内容。' if manifest else '')
        + (' 影子清单仅用于模拟，不能作为真实文件证据。' if shadow else ''),
    }


def _uncertainty(status: str, detail: dict) -> str | None:
    if status == 'resolved':
        return None
    if status == 'resolved_case_mismatch':
        return '大小写与清单不一致'
    if status == 'relocated_reference':
        return '仅路径相似，不能确认是同一文件'
    if status == 'ambiguous_reference':
        return '同名文件不唯一，缺少目录对应关系'
    if status == 'dynamic_artifact':
        return '动态产物通常不纳入版本清单'
    if status == 'out_of_scope':
        return detail.get('out_of_scope_reason') or '路径不在授权清单内'
    if status == 'unknown':
        return '清单不完整，无法确认存在或缺失'
    if status == 'outside':
        return '引用指向仓库之外'
    if status == 'authority_mismatch':
        return '候选或目标位于 frozen/legacy/mirror/evidence，不能自动提升为当前知识'
    if status in ('shadow_present', 'shadow_missing'):
        return '影子清单只有占位文件，不是真实证据'
    if status == 'broken_reference':
        return '完整清单中找不到该路径'
    if status == 'unsupported':
        return '占位符、空白或非常规引用，无法作为路径验证'
    if status == 'external':
        return '外部引用不在本地清单内'
    return None


def _suggested_action(status: str) -> str:
    return {
        'resolved': '无需操作；仍需人工确认引用语义是否正确',
        'resolved_case_mismatch': '修正大小写以匹配实际路径',
        'relocated_reference': '人工确认候选是否为同一文件；不要仅凭同名自动改写',
        'ambiguous_reference': '人工确认唯一目标；不要仅凭同名自动改写',
        'broken_reference': '确认引用应指向的路径；若文件应存在，修复引用或恢复文件',
        'dynamic_artifact': '改为记录生成命令、输入版本和证据位置',
        'out_of_scope': '在授权范围内人工核实；不能判定为缺失',
        'unknown': '补全清单后重新审计，或人工核实',
        'outside': '改为仓库内可审计的路径',
        'external': '检查是否需要把外部证据归档到仓库内',
        'unsupported': '人工确认该引用是否应写为明确路径',
        'authority_mismatch': '标记为历史/镜像/冻结材料；不得自动提升为 Current',
        'shadow_present': '影子清单结果不能作为真实文件证据',
        'shadow_missing': '影子清单结果不能作为缺失证据；用真实只读清单复核',
    }.get(status, '人工复核')
