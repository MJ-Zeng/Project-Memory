"""Documents, ADR metadata and deterministic audit checks."""
from __future__ import annotations
import datetime as dt
import re
from pathlib import Path
from .common import PMError, frontmatter, md_header, today, relpath, validate_identifier, write_new, safe_json, sha256_file

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

DEFAULT_CONFIG = {
    'schema_version': '1.1',
    'doc_roots': ['docs'],
    'mirror_roots': [],
    'legacy_roots': [],
    'adr_dir': 'docs/decisions',
    'task_source': 'github_issues',
    'repo_kind': 'git',
    'mirror_policy': 'active',
    'entry_doc': None,
    'max_verified_age_days': 90,
}
MIRROR_POLICIES = {'active', 'frozen'}


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
    for key in ('doc_roots', 'mirror_roots', 'legacy_roots'):
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
            rel = relpath(repo, path)
            if rel not in seen:
                seen.add(rel)
                docs.append(path)
    return docs


def _under(rel: str, roots: list[str]) -> bool:
    return any(rel == root.rstrip('/') or rel.startswith(root.rstrip('/') + '/') for root in roots)


def authority_of(rel: str, cfg: dict) -> str:
    parts = rel.split('/')
    if any(part in LEGACY_SEGMENTS for part in parts):
        return 'legacy'
    if _under(rel, cfg['legacy_roots']):
        return 'legacy'
    if _under(rel, cfg['mirror_roots']):
        return 'mirror'
    if _under(rel, cfg['doc_roots']):
        return 'canonical'
    return 'other'


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


def audit(repo: Path, config: dict | None = None, allow_empty: bool = False, scope: str = 'all') -> dict:
    cfg = config or load_config(repo)
    if scope not in AUDIT_SCOPES:
        raise PMError('audit scope 必须是以下之一：' + '、'.join(sorted(AUDIT_SCOPES)))
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
    for rec in loaded:
        if rec['rel'] == entry_rel or rec['status'] not in CURRENT_STATUSES:
            continue
        declared = rec['meta'].get('last_verified_at')
        if declared is None:
            continue
        verified = _iso_date(declared)
        if verified is None or (verified - today_date).days > 1:
            add('medium', 'invalid_last_verified_at', rec['rel'],
                'last_verified_at 必须是 YYYY-MM-DD 格式的日期，且不能晚于今天')
        elif (today_date - verified).days > max_verified_age:
            add('low', 'stale_current_document', rec['rel'],
                f'当前文档已 {(today_date - verified).days} 天未核对（上限 {max_verified_age} 天）')
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
    authorities = {a: sum(r['authority'] == a for r in loaded) for a in ('canonical', 'mirror', 'legacy', 'other')}
    statuses = {}
    for rec in loaded:
        statuses[rec['status']] = statuses.get(rec['status'], 0) + 1
    return {
        'schema_version': '1.1',
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
        'mirror_policy': cfg.get('mirror_policy'),
        'entry_doc': cfg.get('entry_doc'),
        'max_verified_age_days': max_verified_age,
        'note': ('这些是结构和启发式检查，不能证明语义正确。'
                 'scope=current 覆盖规范根目录中 current/draft/in-flight/未分类的文档和全部 ADR；'
                 'mirror、legacy、evidence 和历史文档不在范围内。' if scope == 'current' else
                 '这些是结构和启发式检查，不能证明语义正确。'),
    }
