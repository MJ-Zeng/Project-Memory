"""Goal-driven coordination records: goals, agent runs, verification, defects, reconciliation."""
from __future__ import annotations

import copy
import base64
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from .common import PMError, atomic_replace, git_sha_optional, json_text, relpath, safe_json, utc_now, validate_identifier, write_new
from .knowledge import (audit, iter_docs, load_config, load_doc, log_problem,
                        valid_http_url)
from .workflows import handoff as write_handoff
from .workflows import task_id_of
from . import authority
from .authority import (canonical_bytes, canonical_digest,
                        signed_record_authority, untrusted_envelope,
                        verification_authority)
from .execution import (repo_identity, verify_execution_provenance,
                        verify_receipt)
from .gh import GitHubReader

GOAL_STATUSES = {'proposed', 'approved', 'active', 'evaluating', 'achieved', 'cancelled', 'blocked'}
GOAL_TRANSITIONS = {
    'proposed': {'approved', 'cancelled'},
    'approved': {'active', 'blocked', 'cancelled'},
    'active': {'evaluating', 'blocked', 'cancelled'},
    'evaluating': {'achieved', 'active', 'blocked', 'cancelled'},
    'blocked': {'active', 'cancelled'},
    'achieved': set(),
    'cancelled': set(),
}
RUN_STATUSES = {'queued', 'running', 'paused', 'submitted', 'verified', 'failed', 'cancelled', 'superseded'}
RUN_TRANSITIONS = {
    'queued': {'running', 'cancelled'},
    'running': {'paused', 'submitted', 'failed', 'cancelled'},
    'paused': {'running', 'submitted', 'failed', 'cancelled'},
    'submitted': {'verified', 'failed', 'superseded', 'cancelled'},
    'verified': {'failed', 'superseded'},
    'failed': {'running', 'verified', 'cancelled', 'superseded'},
    'cancelled': set(),
    'superseded': set(),
}
DEFECT_STATUSES = {'open', 'fixed', 'verified', 'wontfix', 'closed'}
DEFECT_TRANSITIONS = {
    'open': {'fixed', 'wontfix', 'closed'},
    'fixed': {'open', 'wontfix'},
    'verified': {'open'},
    'wontfix': {'open'},
    'closed': {'open'},
}
EVIDENCE_LEVELS = {'agent_claimed', 'locally_observed', 'externally_verified', 'human_approved'}
EVIDENCE_TRUST = {'agent_claimed': 0, 'locally_observed': 1, 'externally_verified': 2, 'human_approved': 3}
CRITERION_SOURCES = {'test', 'check', 'command', 'ci', 'review'}
EXECUTION_STATUSES = {'passed', 'failed', 'error', 'not_run', 'unknown'}
COVERAGE_REVIEW_STATUSES = {'confirmed', 'human_confirmed', 'unconfirmed', 'rejected', 'not_reviewed'}
MAPPING_STATUSES = {'complete', 'review_required', 'partial', 'missing', 'invalid'}
VERIFY_STATUSES = {'VERIFIED', 'MANUAL_REVIEW_REQUIRED', 'INSUFFICIENT_EVIDENCE',
                   'PARTIAL_COVERAGE', 'BLOCKED_BY_DEFECT', 'FAILED', 'INCONCLUSIVE'}
SEVERITIES = ('high', 'medium', 'low')
ACTIVE_RUN_STATUSES = {'queued', 'running', 'paused'}
RUN_ROLES = {'executor', 'verifier'}
GIT_SHA = re.compile(r'[0-9a-f]{40}')
APPROVAL_REF = re.compile(r'(?:https?://\S+|#\d+|(?:PR|pr|Issue|issue|Review|review)\s*#?\d+|[0-9a-f]{40})')
# R-1 Fix: Patterns that indicate agent self-approval, not human identity
AGENT_SELF_PATTERNS = {'agent-self', 'agent', 'auto', 'system', 'self', 'bot', 'ai', 'automated'}
# R-1 Fix: approved_by must look like a verifiable human identity (email or known reviewer)
HUMAN_IDENTITY_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

# B4: execution audit ledger + signed checkpoint.  See ADR-0007.
AUDIT_SCHEMA = '1.3'
AUDIT_GENESIS = '0' * 64
AUDIT_FILE = 'verification_attempts.jsonl'
AUDIT_CHECKPOINT_FILE = 'head.json'
AUDIT_REQUEST_FILE = 'head.request.json'
AUDIT_MIGRATION_FILE = 'migration.json'
AUDIT_BACKUP_FILE = 'verification_attempts.pre-chain.jsonl'
# Statuses whose transition must be anchored by a signed checkpoint.
AUDITED_GOAL_STATUSES = {'achieved'}


def _safe_key(value: str, label: str) -> str:
    value = str(value).strip()
    if not value or value in ('.', '..'):
        raise PMError(f'{label} 不能为空或是 . / ..')
    key = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value)
    if key in ('.', '..'):
        raise PMError(f'{label} 不合法')
    return key[:120]


def _task_key(task: str) -> str:
    return _safe_key(task_id_of({'id': task}), 'task')


def _root(repo: Path, name: str) -> Path:
    return repo / '.project-memory' / name


def _tracked_diff_sha256(repo: Path) -> str | None:
    """Hash the tracked worktree diff (content, not just status letters)."""
    result = subprocess.run(
        ['git', '-C', str(repo), 'diff', '--binary', '--no-color', 'HEAD', '--'],
        capture_output=True)
    if result.returncode != 0:
        return None
    return hashlib.sha256(result.stdout).hexdigest()


def _record_verified(repo: Path, record: dict) -> bool:
    """A record counts only when it claims verified *and* a trust anchor signs it."""
    return bool(record.get('verified')
                and verification_authority(repo, record).get('trusted'))


def _goal_path(repo: Path, goal_id: str) -> Path:
    return _root(repo, 'goals') / (goal_id + '.json')


def _run_path(repo: Path, task: str, run_id: str) -> Path:
    return _root(repo, 'runs') / _task_key(task) / (run_id + '.json')


def _checkpoint_dir(repo: Path, task: str, run_id: str) -> Path:
    return _root(repo, 'runs') / _task_key(task) / (run_id + '.checkpoints')


def _verification_path(repo: Path, task: str, verification_id: str) -> Path:
    return _root(repo, 'verifications') / _task_key(task) / (verification_id + '.json')


def _defect_path(repo: Path, task: str, defect_id: str) -> Path:
    return _root(repo, 'defects') / _task_key(task) / (defect_id + '.json')


def _json_files(path: Path):
    if not path.is_dir():
        return []
    return sorted(p for p in path.rglob('*.json') if p.is_file())


def _is_checkpoint_path(path: Path) -> bool:
    return any(part.endswith('.checkpoints') for part in path.parts)


def _load(path: Path):
    if not path.is_file():
        raise PMError(f'记录不存在：{path}')
    value = safe_json(path)
    if not isinstance(value, dict):
        raise PMError(f'记录必须是 JSON 对象：{path}')
    return value


def _write(path: Path, record: dict) -> bool:
    return write_new(path, json_text(record))


def _diff(existing: dict, record: dict, keys) -> bool:
    return any(existing.get(k) != record.get(k) for k in keys)


def _mutate(path: Path, mutator) -> dict:
    """Optimistic update with a revision check; never silently overwrite a newer record."""
    for _ in range(3):
        current = _load(path)
        candidate = mutator(copy.deepcopy(current))
        latest = _load(path)
        if latest.get('revision', 1) != current.get('revision', 1):
            continue
        candidate['revision'] = int(current.get('revision', 1)) + 1
        candidate['updated_at'] = utc_now()
        atomic_replace(path, json_text(candidate))
        return candidate
    raise PMError(f'记录在更新期间发生变化，请重试：{path}')


def _git(repo: Path, *args):
    p = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True)
    return p.returncode, p.stdout.strip()


def _branch(repo: Path) -> str | None:
    code, out = _git(repo, 'rev-parse', '--abbrev-ref', 'HEAD')
    return out if code == 0 else None


def _is_ancestor(repo: Path, sha: str, head: str | None) -> bool | None:
    if not head:
        return None
    code, _ = _git(repo, 'merge-base', '--is-ancestor', sha, head)
    return code == 0


def _commit_exists(repo: Path, sha: str) -> bool:
    code, _ = _git(repo, 'cat-file', '-e', sha + '^{commit}')
    return code == 0


def _single_line(value: str, label: str, required: bool = True) -> str:
    value = (value or '').strip()
    if required and not value:
        raise PMError(f'{label} 不能为空')
    if any(ch in value for ch in ('\n', '\r')):
        raise PMError(f'{label} 必须是单行')
    return value


def _list_of_strings(values, label: str) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list) or not all(isinstance(x, str) and x.strip() for x in values):
        raise PMError(f'{label} 必须是字符串数组')
    return [x.strip() for x in values]


def _criteria(values) -> list[dict]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise PMError('success_criteria 必须是数组')
    out, seen = [], set()
    for index, item in enumerate(values, 1):
        if isinstance(item, str):
            item = {'id': f'C{index}', 'statement': item, 'required': True, 'evidence': []}
        if not isinstance(item, dict):
            raise PMError('success_criteria 的每一项必须是字符串或对象')
        cid = _single_line(str(item.get('id') or f'C{index}'), 'criterion id')
        if cid in seen:
            raise PMError(f'criterion id 重复：{cid}')
        seen.add(cid)
        statement = _single_line(str(item.get('statement') or ''), 'criterion statement')
        required = item.get('required', True)
        if not isinstance(required, bool):
            raise PMError('criterion required 必须是布尔值')
        evidence = item.get('evidence', [])
        if not isinstance(evidence, list):
            raise PMError('criterion evidence 必须是数组')
        out.append({'id': cid, 'statement': statement, 'required': required, 'evidence': evidence})
    return out


def _criteria_definition(criteria) -> list[dict]:
    """The immutable part of a criterion; evidence is deliberately excluded."""
    return [{'id': c.get('id'), 'statement': c.get('statement'),
             'required': c.get('required', True)} for c in criteria]


def _criteria_definition_digest(criteria) -> str:
    return canonical_digest(_criteria_definition(criteria))


def _criteria_digest_matches(recorded: str, criteria) -> bool:
    """Accept a stable digest or either legacy full-criteria digest.

    Legacy records signed before this ADR stored a digest over the whole
    ``success_criteria`` list.  They remain current when that list is unchanged,
    or when only evidence was appended after a signature over ``evidence=[]``.
    """
    if not recorded:
        return False
    try:
        if recorded == _criteria_definition_digest(criteria):
            return True
        if recorded == canonical_digest(criteria):
            return True
        return recorded == canonical_digest(
            [{**criterion, 'evidence': []} for criterion in criteria])
    except (AttributeError, TypeError):
        # Malformed goal edits must fail closed, not abort the evaluation.
        return False


def _now_id(prefix: str, *parts) -> str:
    digest = hashlib.sha256('\x1f'.join(str(p) for p in parts).encode('utf-8')).hexdigest()[:12]
    return f'{prefix}-{digest}'


# ---------------------------------------------------------------- goals

def create_goal(repo: Path, goal_id: str, title: str, background: str, outcome: str, owner: str,
                criteria, issues=None, adrs=None, prs=None, constraints=None,
                status: str = 'proposed', approved_by: str | None = None, dry_run: bool = False) -> dict:
    goal_id = validate_identifier(goal_id, 'goal id')
    title = _single_line(title, 'goal title')
    background = _single_line(background, 'goal background', required=False)
    outcome = _single_line(outcome, 'goal outcome')
    owner = _single_line(owner, 'goal owner')
    if status not in GOAL_STATUSES:
        raise PMError('goal status 必须是以下之一：' + '、'.join(sorted(GOAL_STATUSES)))
    if status != 'proposed' and not approved_by:
        raise PMError('除 proposed 外，创建 Goal 必须提供 --approved-by')
    # R-1 Fix: Validate approved_by for goal creation is a verifiable human identity
    if approved_by:
        approval_id_problem = _approved_by_problem(approved_by)
        if approval_id_problem:
            raise PMError(f'Goal 批准人身份无效：{approval_id_problem}')
    issue_list = [int(x) for x in (issues or [])]
    pr_list = [int(x) for x in (prs or [])]
    if any(x <= 0 for x in issue_list + pr_list):
        raise PMError('Issue 和 PR 编号必须是正整数')
    adr_list = []
    for value in adrs or []:
        value = str(value).strip()
        if not re.fullmatch(r'ADR-\d{4,}', value):
            raise PMError(f'ADR 引用格式应为 ADR-0001：{value!r}')
        adr_list.append(value)
    criteria_list = _criteria(criteria)
    if not criteria_list or not any(c.get('required', True) for c in criteria_list):
        raise PMError('Goal 至少需要一个必达的成功标准；否则无法评估是否达成')
    record = {
        'schema_version': '1.2',
        'kind': 'goal',
        'id': goal_id,
        'title': title,
        'background': background,
        'outcome': outcome,
        'owner': owner,
        'constraints': _list_of_strings(constraints, 'constraints'),
        'success_criteria': criteria_list,
        'issues': issue_list,
        'adrs': adr_list,
        'prs': pr_list,
        'status': status,
        'approved_by': approved_by,
        'created_at': utc_now(),
        'updated_at': utc_now(),
        'revision': 1,
        'history': [{'at': utc_now(), 'from': None, 'to': status, 'by': approved_by or owner, 'reason': 'created'}],
    }
    path = _goal_path(repo, goal_id)
    result = {'schema_version': '1.2', 'kind': 'goal_create_result', 'goal': record,
              'path': relpath(repo, path), 'created': True, 'dry_run': dry_run}
    identity = ('id', 'title', 'background', 'outcome', 'owner', 'constraints',
                'success_criteria', 'issues', 'adrs', 'prs', 'status')
    if dry_run:
        if path.is_file():
            existing = _load(path)
            if _diff(existing, record, identity):
                raise PMError(f'Goal {goal_id} 已存在且内容不同：{path}')
            result.update({'goal': existing, 'created': False})
        return result
    if not _write(path, record):
        existing = _load(path)
        if _diff(existing, record, identity):
            raise PMError(f'Goal {goal_id} 已存在且内容不同：{path}')
        return {'schema_version': '1.2', 'kind': 'goal_create_result', 'goal': existing,
                'path': relpath(repo, path), 'created': False, 'dry_run': False}
    return result


def iter_goals(repo: Path):
    return [safe_json(p) for p in _json_files(_root(repo, 'goals'))]


def load_goal(repo: Path, goal_id: str) -> dict:
    validate_identifier(goal_id, 'goal id')
    return _load(_goal_path(repo, goal_id))


def _valid_http_url(value: str | None) -> bool:
    return valid_http_url(value)


def _log_problem(repo: Path, ref: str | None) -> str | None:
    return log_problem(repo, ref)


def _audit_dir(repo: Path) -> Path:
    return _root(repo, 'audit')


def _audit_path(repo: Path) -> Path:
    return _audit_dir(repo) / AUDIT_FILE


def _audit_checkpoint_path(repo: Path) -> Path:
    return _audit_dir(repo) / AUDIT_CHECKPOINT_FILE


def _audit_request_path(repo: Path) -> Path:
    return _audit_dir(repo) / AUDIT_REQUEST_FILE


def _audit_migration_path(repo: Path) -> Path:
    return _audit_dir(repo) / AUDIT_MIGRATION_FILE


def _audit_entry_hash(entry: dict) -> str:
    """Hash of one audit entry, excluding its own ``entry_hash`` field."""
    return canonical_digest({key: value for key, value in entry.items()
                             if key != 'entry_hash'})


def _is_chained(entry: dict) -> bool:
    return (isinstance(entry.get('seq'), int)
            and isinstance(entry.get('prev_hash'), str)
            and isinstance(entry.get('entry_hash'), str))


def _read_audit_entries(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    entries = []
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError as exc:
            raise ValueError(f'第 {number} 行不是合法 JSON：{exc}') from exc
        if not isinstance(entry, dict):
            raise ValueError(f'第 {number} 行不是 JSON 对象')
        entries.append(entry)
    return entries


def _migration_summary(repo: Path) -> dict | None:
    path = _audit_migration_path(repo)
    if not path.is_file():
        return None
    try:
        value = safe_json(path)
    except PMError as exc:
        return {'invalid': str(exc)}
    return value if isinstance(value, dict) else {'invalid': 'migration 不是 JSON 对象'}


def _migration_sha256(repo: Path) -> str | None:
    info = _migration_summary(repo)
    if not isinstance(info, dict) or info.get('invalid'):
        return None
    value = info.get('source_sha256')
    return value if isinstance(value, str) and value else None


def _audit_chain(repo: Path) -> dict:
    """Recompute the audit hash chain from genesis; never trust the stored head."""
    result = {'exists': False, 'entries': [], 'head': None, 'length': 0,
              'problems': [], 'legacy': False,
              'migration': _migration_summary(repo),
              'migration_sha256': _migration_sha256(repo)}
    path = _audit_path(repo)
    if not path.is_file():
        result['problems'].append('audit_missing')
        return result
    result['exists'] = True
    try:
        entries = _read_audit_entries(path)
    except (OSError, ValueError) as exc:
        result['problems'].append(f'audit_unparsable: {exc}')
        return result
    if not entries:
        result['problems'].append('audit_empty')
        return result
    if any(not _is_chained(entry) for entry in entries):
        result['legacy'] = True
        result['problems'].append('legacy_entries_without_chain')
        return result
    previous = AUDIT_GENESIS
    for index, entry in enumerate(entries, 1):
        if entry.get('seq') != index:
            result['problems'].append(f'seq_mismatch_at:{index}')
            break
        if entry.get('prev_hash') != previous:
            result['problems'].append(f'prev_hash_mismatch_at:{index}')
            break
        try:
            digest = _audit_entry_hash(entry)
        except (TypeError, ValueError) as exc:
            result['problems'].append(f'entry_hash_uncomputable_at:{index}: {exc}')
            break
        if entry.get('entry_hash') != digest:
            result['problems'].append(f'entry_hash_mismatch_at:{index}')
            break
        previous = digest
    result['entries'] = entries
    result['length'] = len(entries)
    if not result['problems']:
        result['head'] = previous
    return result


def _load_checkpoint(repo: Path) -> dict | None:
    path = _audit_checkpoint_path(repo)
    if not path.is_file():
        return None
    try:
        value = safe_json(path)
    except PMError:
        return None
    return value if isinstance(value, dict) else None


def _checkpoint_summary(repo: Path, chain: dict) -> dict:
    summary = {'present': False, 'trusted': False, 'matches': False,
               'path': relpath(repo, _audit_checkpoint_path(repo)),
               'reason': 'checkpoint_missing'}
    record = _load_checkpoint(repo)
    if record is None:
        return summary
    summary['present'] = True
    authority = signed_record_authority(repo, record, '审计 checkpoint')
    summary['trusted'] = bool(authority.get('trusted'))
    summary['authority_status'] = authority.get('status')
    summary['reason'] = authority.get('reason')
    for key in ('checkpoint_id', 'goal_id', 'status', 'chain_head', 'chain_length',
                'at', 'approved_by', 'evidence_sha256', 'migration_sha256'):
        summary[key] = record.get(key)
    length = record.get('chain_length')
    anchored = None
    if isinstance(length, int) and 0 < length <= chain['length'] and chain['head']:
        anchored = chain['entries'][length - 1].get('entry_hash')
    summary['anchored_head'] = anchored
    summary['matches'] = bool(
        anchored and anchored == record.get('chain_head')
        and record.get('migration_sha256') == chain['migration_sha256'])
    return summary


def audit_verify(repo: Path) -> dict:
    """Verify the execution audit ledger from genesis and check the checkpoint."""
    chain = _audit_chain(repo)
    checkpoint = _checkpoint_summary(repo, chain)
    problems = list(chain['problems'])
    valid = authoritative = False
    status = 'invalid'
    if not problems:
        if checkpoint['present']:
            if checkpoint['trusted'] and checkpoint['matches']:
                valid = authoritative = True
                status = 'valid'
            else:
                if not checkpoint['trusted']:
                    problems.append('checkpoint_untrusted')
                if not checkpoint['matches']:
                    problems.append('checkpoint_chain_mismatch')
        else:
            valid = True
            status = 'valid_unanchored'
    return {'schema_version': AUDIT_SCHEMA, 'kind': 'audit_chain_verification',
            'status': status, 'valid': valid, 'authoritative': authoritative,
            'entries': chain['length'], 'head': chain['head'],
            'chain_problems': list(chain['problems']),
            'migration': chain['migration'],
            'migration_sha256': chain['migration_sha256'],
            'checkpoint': checkpoint, 'problems': problems,
            'caveat': ('valid_unanchored 只证明链自洽，不证明历史未被重建；'
                       'achieved 需要 anchor 签名的 checkpoint。')}


def _append_audit_entry(repo: Path, fields: dict) -> dict:
    path = _audit_path(repo)
    entries = []
    if path.is_file():
        try:
            entries = _read_audit_entries(path)
        except (OSError, ValueError) as exc:
            raise PMError(f'审计账本不可读：{exc}') from exc
        if any(not _is_chained(entry) for entry in entries):
            audit_migrate(repo)
            entries = _read_audit_entries(path)
    previous = entries[-1]['entry_hash'] if entries else AUDIT_GENESIS
    entry = {'schema_version': AUDIT_SCHEMA, 'kind': 'verification_attempt',
             'seq': len(entries) + 1, 'timestamp': utc_now()}
    entry.update(fields)
    entry['prev_hash'] = previous
    entry['entry_hash'] = _audit_entry_hash(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = ''.join(json.dumps(item, ensure_ascii=False, sort_keys=True) + '\n'
                   for item in entries + [entry])
    atomic_replace(path, text)
    return entry


def _audit_attempt(repo: Path, **fields) -> dict:
    """T-05 + B4: persist every attempt as a hash-chained ledger entry."""
    return _append_audit_entry(repo, fields)


def audit_migrate(repo: Path) -> dict:
    """Give pre-1.3 unhashed audit lines a chain.  Migration is not a trust anchor."""
    path = _audit_path(repo)
    if not path.is_file():
        raise PMError('没有可迁移的审计账本')
    raw = path.read_text(encoding='utf-8')
    try:
        entries = _read_audit_entries(path)
    except (OSError, ValueError) as exc:
        raise PMError(f'审计账本不可读：{exc}') from exc
    if entries and all(_is_chained(entry) for entry in entries):
        return {'schema_version': AUDIT_SCHEMA, 'kind': 'audit_migration_result',
                'changed': False, 'entries': len(entries), 'path': relpath(repo, path)}
    if not entries:
        raise PMError('审计账本为空；空账本不能迁移为有效历史')
    source_sha256 = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    backup = path.parent / AUDIT_BACKUP_FILE
    if not backup.exists():
        write_new(backup, raw)
    chained, previous = [], AUDIT_GENESIS
    for index, entry in enumerate(entries, 1):
        item = {key: value for key, value in entry.items()
                if key not in ('seq', 'prev_hash', 'entry_hash')}
        item['schema_version'] = AUDIT_SCHEMA
        item['seq'] = index
        item['prev_hash'] = previous
        item['entry_hash'] = _audit_entry_hash(item)
        chained.append(item)
        previous = item['entry_hash']
    text = ''.join(json.dumps(item, ensure_ascii=False, sort_keys=True) + '\n'
                   for item in chained)
    atomic_replace(path, text)
    migration = {'schema_version': AUDIT_SCHEMA, 'kind': 'audit_migration',
                 'at': utc_now(), 'source_sha256': source_sha256,
                 'entries': len(chained), 'head': previous,
                 'backup': relpath(repo, backup),
                 'note': '迁移本身不是信任锚；只有 anchor 签名的 checkpoint 才能使其权威'}
    atomic_replace(_audit_migration_path(repo), json_text(migration))
    return {'schema_version': AUDIT_SCHEMA, 'kind': 'audit_migration_result',
            'changed': True, 'entries': len(chained), 'head': previous,
            'source_sha256': source_sha256, 'path': relpath(repo, path),
            'migration': migration}


def _goal_evidence_digest(goal: dict, evaluation: dict) -> str:
    satisfying = []
    for criterion in evaluation.get('criteria') or []:
        for item in criterion.get('evidence') or []:
            if item.get('satisfies'):
                satisfying.append({'criterion_id': criterion.get('id'),
                                   'kind': item.get('kind'),
                                   'ref': item.get('ref')})
    satisfying.sort(key=lambda item: (str(item['criterion_id']), str(item['kind']),
                                      str(item['ref'])))
    return canonical_digest({
        'goal_id': goal.get('id'),
        'criteria_definition_sha256': _criteria_definition_digest(
            goal.get('success_criteria', [])),
        'satisfying': satisfying})


def _checkpoint_payload(repo: Path, goal: dict, evaluation: dict,
                        approved_by: str | None) -> dict:
    chain = _audit_chain(repo)
    if chain['problems']:
        raise PMError('审计链不完整，不能生成 checkpoint 请求：'
                      + '；'.join(chain['problems']))
    if not chain['length']:
        raise PMError('没有审计条目，不能生成 checkpoint 请求')
    at = utc_now()
    checkpoint_id = 'CKPT-' + canonical_digest(
        {'goal_id': goal.get('id'), 'chain_head': chain['head'],
         'chain_length': chain['length'], 'at': at})[:12]
    return {'schema_version': AUDIT_SCHEMA, 'kind': 'audit_checkpoint',
            'checkpoint_id': checkpoint_id,
            'goal_id': goal.get('id'), 'status': 'achieved',
            'chain_head': chain['head'], 'chain_length': chain['length'],
            'at': at, 'approved_by': approved_by or goal.get('approved_by'),
            'evidence_sha256': _goal_evidence_digest(goal, evaluation),
            'migration_sha256': chain['migration_sha256']}


def write_audit_checkpoint_request(repo: Path, goal_id: str,
                                   approved_by: str | None = None,
                                   status: str = 'achieved') -> dict:
    """Stage an unsigned checkpoint payload for an external anchor signature."""
    if status not in AUDITED_GOAL_STATUSES:
        raise PMError(f'{status} 不是需要 checkpoint 的关键状态')
    goal = load_goal(repo, goal_id)
    if goal.get('status') != status:
        raise PMError(f'Goal {goal_id} 当前状态是 {goal.get("status")}，'
                      f'不能为 {status} 生成 checkpoint 请求')
    evaluation = evaluate_goal(repo, goal_id)
    if not evaluation['satisfied']:
        raise PMError('成功标准尚未满足，不能生成 achieved checkpoint 请求')
    payload = _checkpoint_payload(repo, goal, evaluation, approved_by)
    path = _audit_request_path(repo)
    atomic_replace(path, canonical_bytes(payload).decode('utf-8'))
    return {'schema_version': AUDIT_SCHEMA,
            'kind': 'audit_checkpoint_request_result',
            'path': relpath(repo, path), 'payload': payload,
            'payload_sha256': canonical_digest(payload),
            'requires': ('由仓库外 anchor 私钥对 payload 的 canonical JSON 字节签名，'
                         '再运行 audit checkpoint-attach；Agent 不能自行签名')}


def attach_audit_checkpoint(repo: Path, signature_path) -> dict:
    """Attach an externally produced signature; verify it in-process first."""
    request_path = _audit_request_path(repo)
    if not request_path.is_file():
        raise PMError('没有 checkpoint 请求；先运行 audit checkpoint-request 或 goal transition')
    try:
        payload = json.loads(request_path.read_text(encoding='utf-8'))
    except ValueError as exc:
        raise PMError(f'checkpoint 请求不是合法 JSON：{exc}') from exc
    if not isinstance(payload, dict) or payload.get('kind') != 'audit_checkpoint':
        raise PMError('checkpoint 请求格式不正确')
    goal_id = payload.get('goal_id')
    load_goal(repo, goal_id)
    signature_file = Path(signature_path)
    if not signature_file.is_file():
        raise PMError(f'签名文件不存在：{signature_file}')
    signature = signature_file.read_bytes()
    if not signature:
        raise PMError('签名为空')
    anchor, anchor_reason = authority.load_anchor(repo)
    if anchor is None:
        raise PMError(f'无法验证 checkpoint：{anchor_reason}')
    record = {**payload, 'authority': {
        'status': 'trusted', 'anchor_id': anchor['anchor_id'],
        'issuer': anchor['issuer'], 'algorithm': anchor['algorithm'],
        'signed_payload_sha256': canonical_digest(payload),
        'signature_b64': base64.b64encode(signature).decode('ascii')}}
    verdict = signed_record_authority(repo, record, '审计 checkpoint')
    if not verdict.get('trusted'):
        raise PMError(f'checkpoint 签名无效（{verdict.get("status")}）：'
                      f'{verdict.get("reason")}')
    chain = _audit_chain(repo)
    if chain['problems']:
        raise PMError('审计链不完整，拒绝附加 checkpoint：'
                      + '；'.join(chain['problems']))
    length = payload.get('chain_length')
    if not isinstance(length, int) or not 0 < length <= chain['length']:
        raise PMError('checkpoint 请求的链长度与当前账本不一致')
    if chain['entries'][length - 1].get('entry_hash') != payload.get('chain_head'):
        raise PMError('checkpoint 请求的链头与当前账本不一致（账本已被改写或重建）')
    if payload.get('migration_sha256') != chain['migration_sha256']:
        raise PMError('checkpoint 请求的迁移摘要与当前账本不一致')
    path = _audit_checkpoint_path(repo)
    atomic_replace(path, json_text(record))
    return {'schema_version': AUDIT_SCHEMA, 'kind': 'audit_checkpoint_attach_result',
            'path': relpath(repo, path), 'checkpoint': record, 'trusted': True,
            'anchor_id': anchor['anchor_id'], 'chain_head': payload.get('chain_head'),
            'chain_length': length}


def audit_head(repo: Path) -> dict:
    report = audit_verify(repo)
    return {'schema_version': AUDIT_SCHEMA, 'kind': 'audit_head_result',
            'status': report['status'], 'head': report['head'],
            'entries': report['entries'], 'authoritative': report['authoritative'],
            'checkpoint': report['checkpoint'], 'problems': report['problems'],
            'migration': report['migration']}


def _achieved_status(repo: Path, goal: dict, satisfied: bool, evaluation: dict,
                     audit_report: dict) -> tuple[str, bool | None, list[str]]:
    """Derive the status a consumer may act on; raw ``achieved`` is only a claim."""
    raw = goal.get('status')
    if raw != 'achieved':
        return raw, None, []
    problems = []
    if not satisfied:
        problems.append('goal_not_satisfied')
    for problem in audit_report.get('chain_problems') or []:
        if problem.startswith('audit_missing'):
            problems.append('audit_missing')
        elif problem.startswith('audit_empty'):
            problems.append('audit_empty')
        else:
            problems.append('audit_chain_invalid')
    checkpoint = audit_report.get('checkpoint') or {}
    if not checkpoint.get('present'):
        problems.append('checkpoint_missing')
    else:
        if not checkpoint.get('trusted'):
            problems.append('checkpoint_untrusted')
        if not checkpoint.get('matches'):
            problems.append('checkpoint_chain_mismatch')
        record = _load_checkpoint(repo) or {}
        if record.get('goal_id') != goal.get('id'):
            problems.append('checkpoint_goal_mismatch')
        if record.get('status') != 'achieved':
            problems.append('checkpoint_status_mismatch')
        if record.get('evidence_sha256') != _goal_evidence_digest(goal, evaluation):
            problems.append('checkpoint_evidence_mismatch')
    history = goal.get('history')
    if not isinstance(history, list) or not history or history[-1].get('to') != raw:
        problems.append('status_history_mismatch')
    problems = list(dict.fromkeys(problems))
    if problems:
        return 'achieved_unverified', False, problems
    return 'achieved', True, []


def _approval_problem(ref: str | None) -> str | None:
    value = str(ref or '').strip()
    if not value:
        return 'manual 证据的 ref 必须是批准链接、PR/Issue 编号或 40 位提交 SHA'
    if APPROVAL_REF.fullmatch(value):
        return None
    return 'manual 证据的 ref 必须是批准链接、PR/Issue 编号或 40 位提交 SHA'


def _approved_by_problem(approved_by: str | None) -> str | None:
    """R-1 Fix: Validate that approved_by looks like a verifiable human identity."""
    value = str(approved_by or '').strip()
    if not value:
        return 'manual 证据必须提供 approved_by'
    # Reject known agent self-reference patterns
    if value.lower() in AGENT_SELF_PATTERNS:
        return f'approved_by 不能是 Agent 自报标识（{value}）；必须是可验证的人类身份'
    # Require email-like format for verifiable human identity
    if not HUMAN_IDENTITY_PATTERN.match(value):
        return 'approved_by 必须是邮箱地址格式（如 reviewer@example.com），以便追溯人类身份'
    return None


def _norm_text(value) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip().casefold()


def _repo_binding(repo: Path, declared: str) -> str | None:
    """Return how ``declared`` names the repository at ``repo``, or ``None``.

    Two forms are accepted, both tied to the stable identity from
    :func:`execution.repo_identity` (canonical remote + root commits):

    * ``identity`` -- the identity id or its canonical ``host/path`` remote;
    * ``path`` -- an absolute path to this checkout, or to another checkout
      whose identity is identical (a copy of the same repository).

    A bare directory name is deliberately not accepted: an unrelated repository
    with the same directory name would pass.  An absolute path that does not
    exist, or that resolves to a different identity, is not evidence of
    "this repository".
    """
    value = str(declared or '').strip()
    if not value:
        return None
    current = repo_identity(repo)
    if value.casefold() in {current['id'], (current.get('remote') or '').casefold()}:
        return 'identity'
    candidate = Path(value)
    if not candidate.is_absolute():
        return None
    try:
        candidate = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not candidate.is_dir():
        return None
    if candidate == repo.resolve():
        return 'path'
    try:
        candidate.relative_to(repo.resolve())
    except ValueError:
        pass
    else:
        return None  # a subdirectory cannot stand in for the repository
    code, toplevel = _git(candidate, 'rev-parse', '--show-toplevel')
    if code != 0 or Path(toplevel).resolve() != candidate:
        return None  # only another checkout root, not a random subdirectory
    try:
        other = repo_identity(candidate)
    except PMError:
        return None
    return 'identity' if other['id'] == current['id'] else None


def _repo_matches(repo: Path, declared: str) -> bool:
    return _repo_binding(repo, declared) is not None


def _external_ci_status(pr_number: int | None) -> tuple[dict | None, dict]:
    """Fetch a PR's CI status from GitHub; return ``(status_or_none, info)``.

    B-9: only an explicit PR number plus ``GITHUB_REPOSITORY`` triggers the
    fetch. Missing configuration, network trouble and API errors all degrade to
    None, so the caller keeps agent_claimed trust instead of blocking work.
    ``info`` records the repository slug and a failure category
    (``not_requested``/``missing_repository``/``invalid_repository``/
    ``invalid_pr``/``api_error``/``shape_error``/``ok``) for audit; it never
    carries tokens, headers or response bodies.
    """
    slug = os.getenv('GITHUB_REPOSITORY') or ''
    info = {'repository': '', 'fetch': 'not_requested'}
    if pr_number is None:
        return None, info
    if isinstance(pr_number, bool) or not isinstance(pr_number, int) or pr_number < 1:
        info['fetch'] = 'invalid_pr'
        return None, info
    if not slug:
        info['fetch'] = 'missing_repository'
        return None, info
    info['repository'] = slug
    if not re.fullmatch(r'[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+', slug):
        info['fetch'] = 'invalid_repository'
        return None, info
    try:
        status = GitHubReader(slug).pull_request_ci_status(pr_number)
    except Exception:
        # B-9 contract: any fetch failure (config, network, API, shape) degrades
        # to agent_claimed; external evidence must never block local work.
        info['fetch'] = 'api_error'
        return None, info
    if not isinstance(status, dict) or status.get('_provenance') != 'github_api':
        info['fetch'] = 'shape_error'
        return None, info
    info['fetch'] = 'ok'
    return status, info


def _criterion_evidence_entries(value, repo: Path, goal: dict, target: dict,
                                verifier: dict, target_head: str | None,
                                external_ci: dict | None = None) -> list[dict]:
    """Validate criterion-to-evidence mappings. Structural errors raise; semantic gaps are recorded."""
    if value is None:
        return []
    if isinstance(value, dict):
        value = value.get('criteria', value.get('criterion_evidence'))
    if not isinstance(value, list):
        raise PMError('criterion evidence 必须是数组，或包含 criteria 数组的对象')
    criteria = {c['id']: c for c in goal.get('success_criteria', [])}
    used = {}
    for record in iter_verifications(repo):
        for entry in record.get('criterion_evidence') or []:
            evidence_id = entry.get('evidence_id')
            if evidence_id:
                used.setdefault(evidence_id, set()).add(record.get('goal_id'))
    entries, seen, evidence_ids = [], set(), set()
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict):
            raise PMError(f'criterion evidence 第 {index} 项必须是对象')
        cid = _single_line(str(item.get('criterion_id') or ''), 'criterion_id')
        if cid not in criteria:
            raise PMError(f'criterion_id {cid} 不属于 Goal {goal.get("id")}')
        if cid in seen:
            raise PMError(f'criterion id 重复映射：{cid}；一个标准只能有一条映射')
        seen.add(cid)
        description = _single_line(str(item.get('criterion_description') or ''),
                                   'criterion_description')
        goal_id = _single_line(str(item.get('goal_id') or ''), 'goal_id')
        if goal_id != goal.get('id'):
            raise PMError(f'criterion evidence 的 goal_id {goal_id} 与验证目标 {goal.get("id")} 不一致')
        task_id = _single_line(str(item.get('task_id') or ''), 'task_id')
        if _task_key(task_id) != _task_key(target.get('task')):
            raise PMError(f'criterion evidence 的 task_id {task_id} 与执行任务 {target.get("task")} 不一致')
        repository = _single_line(str(item.get('target_repository') or ''),
                                  'target_repository')
        if not _repo_matches(repo, repository):
            raise PMError(f'criterion evidence 的 target_repository {repository!r} 不是当前仓库')
        sha = _single_line(str(item.get('target_commit_sha') or ''), 'target_commit_sha')
        if not GIT_SHA.fullmatch(sha):
            raise PMError('target_commit_sha 必须是完整的 40 位 SHA')
        if sha != target_head:
            raise PMError(f'criterion evidence 绑定到 {sha}，不是被验证提交 {target_head}')
        if not _commit_exists(repo, sha):
            raise PMError(f'target_commit_sha 不存在：{sha}')
        evidence_id = _single_line(str(item.get('evidence_id') or ''), 'evidence_id')
        if evidence_id in evidence_ids:
            raise PMError(f'evidence_id {evidence_id} 在同一次验证中被多个标准复用')
        evidence_ids.add(evidence_id)
        if evidence_id in used and goal.get('id') not in used[evidence_id]:
            raise PMError(f'evidence_id {evidence_id} 已被其他 Goal 使用：'
                          + '、'.join(sorted(x for x in used[evidence_id] if x)))
        source = _single_line(str(item.get('evidence_source') or ''), 'evidence_source')
        if source not in CRITERION_SOURCES:
            raise PMError('evidence_source 必须是以下之一：' + '、'.join(sorted(CRITERION_SOURCES)))
        local = source in ('test', 'check', 'command')
        command = _single_line(str(item.get('evidence_command') or ''), 'evidence_command',
                               required=local)
        log = _single_line(str(item.get('evidence_log') or ''), 'evidence_log',
                           required=local)
        exit_code = item.get('evidence_exit_code')
        status = _single_line(str(item.get('execution_status') or ''), 'execution_status')
        if status not in EXECUTION_STATUSES:
            raise PMError('execution_status 必须是以下之一：' + '、'.join(sorted(EXECUTION_STATUSES)))
        coverage_claim = _single_line(str(item.get('coverage_claim') or ''), 'coverage_claim')
        review_status = _single_line(str(item.get('coverage_review_status') or ''),
                                     'coverage_review_status')
        if review_status not in COVERAGE_REVIEW_STATUSES:
            raise PMError('coverage_review_status 必须是以下之一：'
                          + '、'.join(sorted(COVERAGE_REVIEW_STATUSES)))
        independent = _single_line(str(item.get('independent_verifier') or ''),
                                   'independent_verifier')
        if independent != verifier.get('agent'):
            raise PMError('independent_verifier 必须是当前 verifier 执行记录的 agent')
        if independent == target.get('agent'):
            model_differs = ((target.get('model') or {}).get('id')
                             != (verifier.get('model') or {}).get('id'))
            session_differs = (target.get('session_id') and verifier.get('session_id')
                               and target.get('session_id') != verifier.get('session_id'))
            if not (model_differs or session_differs):
                raise PMError('独立验证者与被验证执行使用相同的 agent/model/session')
        result = _single_line(str(item.get('verification_result') or ''),
                              'verification_result')
        if result not in ('pass', 'fail', 'inconclusive'):
            raise PMError('verification_result 必须是 pass、fail 或 inconclusive')
        receipt_info = None
        if local:
            if not isinstance(exit_code, int):
                raise PMError('本地执行证据必须提供整数 evidence_exit_code')
            receipt_ref = _single_line(str(item.get('evidence_receipt') or ''),
                                       'evidence_receipt', required=True)
            receipt_info = verify_receipt(
                repo, receipt_ref,
                expected={'commit_sha': sha, 'command': command, 'exit_code': exit_code})
            if not receipt_info['valid']:
                raise PMError('criterion evidence 的执行收据无效：'
                              + '；'.join(receipt_info['problems']))
            problem = _log_problem(repo, log)
            if problem:
                raise PMError(f'evidence_log 无效：{problem}')
            receipt_log = receipt_info['receipt'].get('log_path')
            if _norm_text(log) != _norm_text(receipt_log):
                raise PMError('evidence_log 与执行收据记录的日志不一致')
            if status == 'passed' and exit_code != 0:
                raise PMError('execution_status=passed 与 evidence_exit_code 非 0 矛盾')
            if status == 'passed' and result == 'pass' and exit_code != 0:
                raise PMError('执行收据退出码非 0，不能声明 pass')
        ci_url = _single_line(str(item.get('evidence_ci_url') or ''), 'evidence_ci_url',
                              required=source == 'ci')
        ci_status = _single_line(str(item.get('evidence_ci_status') or ''), 'evidence_ci_status',
                                 required=source == 'ci')
        review_url = _single_line(str(item.get('evidence_review_url') or ''),
                                  'evidence_review_url', required=source == 'review')
        review_state = _single_line(str(item.get('evidence_review_state') or ''),
                                    'evidence_review_state', required=source == 'review')
        if ci_url and not _valid_http_url(ci_url):
            raise PMError('evidence_ci_url 必须是 http(s) 地址')
        if review_url and not _valid_http_url(review_url):
            raise PMError('evidence_review_url 必须是 http(s) 地址')
        description_match = _norm_text(description) == _norm_text(criteria[cid]['statement'])
        external_ci_verified = False
        if source in ('test', 'check', 'command'):
            # R-2: only a receipt-backed execution counts as locally observed.
            observed = ('locally_observed'
                        if receipt_info and receipt_info['valid'] and status == 'passed'
                        and exit_code == 0 else 'agent_claimed')
        elif source == 'ci':
            # B-9: CI raises trust only when the GitHub API reports a green build
            # for this exact commit.  A declared URL/status is still a claim.
            external_ci_verified = bool(
                external_ci
                and external_ci.get('status') == 'success'
                and external_ci.get('head_sha') == sha)
            observed = 'externally_verified' if external_ci_verified else 'agent_claimed'
        elif source == 'review':
            # R-1: declared_unfetched review cannot get human_approved trust.
            observed = 'agent_claimed'
        else:
            observed = 'agent_claimed'
        # R-2: an independent verifier's JSON "confirmed" is still an agent claim.
        # Only a trusted human approval event (not available in this build) may
        # confirm semantic coverage, so no machine mapping can auto-verify.
        human_review_claimed = (review_status == 'human_confirmed'
                                and bool(str(item.get('coverage_review_ref') or '').strip()))
        coverage_confirmed = False
        evidence_matched = False
        problems = []
        if not description_match:
            problems.append('criterion_description 与 Goal 标准不一致')
        if review_status != 'human_confirmed':
            problems.append('语义覆盖未由可信人工来源确认（不是 VERIFIED）')
        elif human_review_claimed:
            problems.append('人工覆盖确认仍是调用者声明，缺少可信审批来源')
        if status != 'passed':
            problems.append('execution_status 不是 passed')
        if result != 'pass':
            problems.append('verification_result 不是 pass')
        if observed == 'agent_claimed':
            problems.append('没有可观察的执行证据（缺少有效执行收据）')
        elif observed == 'externally_verified':
            # The GitHub API proves the build outcome for this commit only; it
            # says nothing about semantic coverage of the criterion.
            problems.append('CI 成功只证明该提交的构建事实；语义覆盖仍需可信人工确认')
        structural_ok = (description_match and status == 'passed' and result == 'pass')
        if observed in ('locally_observed', 'externally_verified') and structural_ok:
            state = 'MANUAL_REVIEW_REQUIRED'
        elif observed == 'locally_observed':
            state = 'executed'
        elif observed == 'externally_verified':
            state = 'external_observed'
        else:
            state = 'agent_claimed'
        receipt = (receipt_info or {}).get('receipt') or {}
        entries.append({
            'criterion_id': cid,
            'goal_id': goal_id,
            'task_id': task_id,
            'criterion_description': description,
            'target_repository': repository,
            'target_commit_sha': sha,
            'evidence_id': evidence_id,
            'evidence_source': source,
            'evidence_command': command,
            'evidence_log': log,
            'evidence_exit_code': exit_code,
            'evidence_receipt': str(item.get('evidence_receipt') or ''),
            'receipt_id': receipt.get('receipt_id'),
            'receipt_sha256': receipt.get('content_sha256'),
            'snapshot_id': receipt.get('snapshot_id'),
            'snapshot_sha256': receipt.get('snapshot_sha256'),
            'execution_status': status,
            'coverage_claim': coverage_claim,
            'coverage_review_status': review_status,
            'human_review_claimed': human_review_claimed,
            'independent_verifier': independent,
            'verification_result': result,
            'description_match': description_match,
            'observed_level': observed,
            'external_ci_verified': external_ci_verified,
            # A valid receipt proves content integrity only.  No receipt in this
            # build carries an authenticated, external provenance, so execution
            # is never upgraded to "verified by a trusted source" here.
            'receipt_integrity_valid': bool(receipt_info and receipt_info['valid']),
            'receipt_provenance': (receipt_info or {}).get('provenance'),
            'execution_trust': receipt.get('trust'),
            'execution_verified': False,
            'semantic_coverage_verified': False,
            'evidence_state': state,
            'coverage_confirmed': coverage_confirmed,
            'evidence_matched': evidence_matched,
            'problems': problems,
        })
    return entries


def _mapping_summary(entries: list[dict], goal: dict) -> dict:
    required = [c['id'] for c in goal.get('success_criteria', []) if c.get('required', True)]
    by_criterion = {}
    for entry in entries:
        by_criterion.setdefault(entry['criterion_id'], []).append(entry)
    covered, execution_covered, partial, review_required, problems = [], [], [], [], []
    for cid in required:
        items = by_criterion.get(cid, [])
        if items and all(entry['evidence_matched'] for entry in items):
            covered.append(cid)
        elif items:
            partial.append(cid)
            for entry in items:
                problems.extend(f'{cid}: {problem}' for problem in entry['problems'])
            executed = all(entry.get('receipt_integrity_valid') and entry.get('description_match')
                           and entry.get('execution_status') == 'passed'
                           and entry.get('verification_result') == 'pass'
                           for entry in items)
            # B-9: a green CI build fetched for this commit is an externally
            # observed execution, but semantic coverage is still unconfirmed.
            externally_observed = all(entry.get('external_ci_verified')
                                      and entry.get('description_match')
                                      and entry.get('execution_status') == 'passed'
                                      and entry.get('verification_result') == 'pass'
                                      for entry in items)
            if executed or externally_observed:
                execution_covered.append(cid)
                review_required.append(cid)
    missing = [cid for cid in required if cid not in by_criterion]
    unexpected = sorted(cid for cid in by_criterion if cid not in required)
    if not entries:
        status = 'missing'
    elif missing or unexpected or set(execution_covered) != set(required):
        status = 'partial'
    elif review_required:
        status = 'review_required'
    else:
        status = 'complete'
    return {'status': status, 'required': required, 'covered': covered,
            'execution_covered': execution_covered,
            'review_required': review_required,
            'partial': partial, 'missing': missing, 'unexpected': unexpected,
            'problems': problems}


def _mapping_outcome(entries: list[dict], mapping: dict) -> str:
    if not entries:
        return 'INSUFFICIENT_EVIDENCE'
    if mapping['missing'] or mapping['unexpected'] or mapping['partial'] and not mapping['review_required']:
        return 'PARTIAL_COVERAGE'
    if mapping['status'] == 'review_required':
        return 'MANUAL_REVIEW_REQUIRED'
    return 'INSUFFICIENT_EVIDENCE'


def _open_high_defects(repo: Path, goal_id: str) -> list[dict]:
    return [d for d in iter_defects(repo)
            if d.get('goal_id') == goal_id
            and d.get('status') in ('open', 'fixed')
            and d.get('severity') == 'high']


def _independence(target: dict, verifier: dict) -> dict:
    if target.get('role', 'executor') != 'executor':
        raise PMError('被验证执行必须是 executor；验证执行不能作为被验证对象')
    if verifier.get('role', 'executor') != 'verifier':
        raise PMError('验证者必须使用 role=verifier 的执行记录')
    basis = []
    if target.get('agent') != verifier.get('agent'):
        basis.append('agent')
    if (target.get('model') or {}).get('id') != (verifier.get('model') or {}).get('id'):
        basis.append('model')
    if target.get('session_id') and verifier.get('session_id') and target.get('session_id') != verifier.get('session_id'):
        basis.append('session')
    if not basis:
        raise PMError('验证者与被验证执行使用相同的 agent/model/session；请用独立会话或不同模型')
    return {'distinct': True, 'basis': basis,
            'note': '独立会话或不同模型只证明记录不同，不证明验证结论正确。'}


def _check_run_transition(run: dict, target: str):
    current = run.get('status')
    if target == current:
        return
    allowed = RUN_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise PMError(f'不允许的执行状态转换：{current} -> {target}')


def _verification_current(repo: Path, verification: dict) -> bool:
    if verification.get('stale'):
        return False
    target_head = verification.get('target_head_sha')
    current = git_sha_optional(repo)
    if target_head and current and target_head != current:
        return False
    run_path = _find_run_by_id(repo, verification.get('target_run'))
    if run_path is None:
        return False
    run = _load(run_path)
    if (run.get('git') or {}).get('head_sha') != target_head:
        return False
    # Bind the immutable inputs used by the verification.  A later edit to the
    # run record, verifier record or Goal criteria must invalidate the record
    # even when the commit SHA and tracked status letters are unchanged.
    recorded_run_digest = verification.get('target_run_sha256')
    if recorded_run_digest and canonical_digest(run) != recorded_run_digest:
        return False
    recorded_verifier_digest = verification.get('verifier_run_sha256')
    if recorded_verifier_digest:
        verifier_path = _find_run_by_id(repo, verification.get('verifier_run'))
        if verifier_path is None or canonical_digest(_load(verifier_path)) != recorded_verifier_digest:
            return False
    recorded_goal_digest = verification.get('goal_criteria_sha256')
    if recorded_goal_digest:
        try:
            goal = load_goal(repo, verification.get('goal_id'))
        except PMError:
            return False
        if not _criteria_digest_matches(recorded_goal_digest,
                                        goal.get('success_criteria', [])):
            return False
    # T-04 (fixed): compare tracked-file state against the state recorded at
    # verification time. Untracked files (including .project-memory receipts and
    # test logs) are excluded, so recording a log no longer makes every attempt
    # look dirty; a later edit to tracked code does invalidate the record.
    checks = verification.get('checks') or {}
    tests_info = checks.get('tests') or {}
    if not isinstance(tests_info, dict):
        return False
    recorded_status = tests_info.get('tracked_changes_at_verification')
    code, out = _git(repo, 'status', '--porcelain', '--untracked-files=no')
    if code != 0:
        return False
    current_status = out.strip()
    if recorded_status is not None and current_status != recorded_status:
        return False
    # Status letters alone cannot distinguish "M" from a different "M".  Bind
    # the actual tracked diff bytes as well.
    recorded_diff = tests_info.get('tracked_diff_sha256')
    if recorded_diff is not None:
        current_diff = _tracked_diff_sha256(repo)
        if current_diff is None or current_diff != recorded_diff:
            return False
    # T-03: log content hash binding.
    log_hash = tests_info.get('log_content_sha256')
    if log_hash:
        log_path = tests_info.get('log', '')
        if log_path:
            full_path = Path(log_path)
            if not full_path.is_absolute():
                full_path = repo / full_path
            from .common import sha256_file
            if not full_path.is_file() or sha256_file(full_path) != log_hash:
                return False
    # R-2: the execution receipt, snapshot and log must still verify, and the
    # receipt must be the exact one recorded (not merely another valid receipt
    # for the same commit).
    receipt_ref = tests_info.get('receipt')
    if receipt_ref:
        checked = verify_receipt(repo, receipt_ref,
                                 expected={'commit_sha': target_head})
        if not checked['valid']:
            return False
        receipt = checked['receipt'] or {}
        field_map = {'receipt_id': 'receipt_id', 'receipt_sha256': 'content_sha256',
                     'snapshot_id': 'snapshot_id', 'snapshot_sha256': 'snapshot_sha256'}
        for recorded_key, receipt_key in field_map.items():
            recorded = tests_info.get(recorded_key)
            if recorded is not None and receipt.get(receipt_key) != recorded:
                return False
        if receipt.get('command') != tests_info.get('command'):
            return False
        if receipt.get('exit_code') != tests_info.get('exit_code'):
            return False
        if _norm_text(receipt.get('log_path')) != _norm_text(tests_info.get('log')):
            return False
        if receipt.get('commit_sha') != target_head:
            return False
    elif verification.get('status') == 'VERIFIED':
        # A record claiming authoritative success without any receipt is invalid.
        return False
    # "Current" describes whether the recorded evidence still matches the current
    # commit, tracked worktree, log and snapshot. Whether a run was upgraded to
    # verified is a separate question (see _verification_ok / resume filters).
    return True


def _criteria_definition_changed(repo: Path, verification: dict) -> bool:
    recorded = verification.get('goal_criteria_sha256')
    if not recorded:
        return False
    try:
        goal = load_goal(repo, verification.get('goal_id'))
    except PMError:
        return False
    return not _criteria_digest_matches(recorded, goal.get('success_criteria', []))


def _verification_ok(repo: Path, evidence: dict, goal_id: str,
                     criterion_id: str = '') -> tuple[bool, str, str]:
    ref = str(evidence.get('ref') or '').strip()
    if not ref:
        return False, '缺少 verification 引用', 'invalid'
    path = _find_record(repo, 'verifications', ref)
    if path is None:
        return False, f'找不到验证记录 {ref}', 'invalid'
    verification = _load(path)
    if verification.get('kind') not in (None, 'verification_record'):
        return False, f'{ref} 不是 verification 记录', 'invalid'
    if verification.get('goal_id') != goal_id:
        return False, f'{ref} 属于其他目标：{verification.get("goal_id")}', 'invalid'
    if verification.get('verdict') != 'pass' or verification.get('status') != 'VERIFIED':
        return False, f'{ref} 不是已通过的验证', 'invalid'
    # A locally written JSON with verdict=pass/status=VERIFIED is still only a
    # claim.  Only a record counter-signed by the protected trust anchor may
    # satisfy a criterion.  Without an anchor this always fails closed.
    authority = verification_authority(repo, verification)
    if not authority.get('trusted'):
        return (False, f'{ref} 没有可信授权来源（{authority.get("status")}）：'
                       f'{authority.get("reason")}', 'untrusted')
    checks = verification.get('checks')
    tests_info = (checks or {}).get('tests') if isinstance(checks, dict) else None
    if not isinstance(checks, dict) or not checks or not isinstance(tests_info, dict):
        return False, f'{ref} 缺少执行检查记录', 'invalid'
    if not tests_info.get('receipt_integrity_valid'):
        return False, f'{ref} 的执行收据没有通过完整性校验', 'invalid'
    if not criterion_id:
        return False, f'{ref} 缺少 criterion id，无法确认覆盖', 'unconfirmed'
    # B2: a signed record must not vouch for a handwritten receipt.
    receipt_ref = tests_info.get('receipt')
    if not receipt_ref:
        return False, f'{ref} 缺少执行收据引用，无法确认执行来源', 'untrusted'
    checked_receipt = verify_receipt(
        repo, receipt_ref, expected={'commit_sha': verification.get('target_head_sha')})
    if not checked_receipt.get('valid'):
        return (False, f'{ref} 的执行收据内容不完整：'
                       + '；'.join(checked_receipt.get('problems') or []), 'invalid')
    provenance = verify_execution_provenance(
        repo, checked_receipt.get('receipt') or {},
        verification.get('target_head_sha') or '',
        goal_id=goal_id, criterion_id=criterion_id)
    if not provenance.get('authenticated'):
        return (False, f'{ref} 的执行来源不可信：{provenance.get("reason")}',
                'untrusted')
    entries = [entry for entry in (verification.get('criterion_evidence') or [])
               if entry.get('criterion_id') == criterion_id and entry.get('evidence_matched')]
    if not entries:
        return (False, f'{ref} 没有覆盖标准 {criterion_id} 的已确认证据映射；'
                       '旧验证记录不能被当作该标准的达成依据', 'unconfirmed')
    if verification.get('mapping_status') != 'complete':
        return False, f'{ref} 的 criterion 覆盖映射不完整', 'unconfirmed'
    if any(entry.get('target_commit_sha') != verification.get('target_head_sha')
           for entry in entries):
        return False, f'{ref} 的证据映射与验证提交不一致', 'invalid'
    if not _verification_current(repo, verification):
        if _criteria_definition_changed(repo, verification):
            return (False, f'{ref} 的判据定义已变化（id/statement/required），'
                           '验证记录失效；追加证据本身不会导致失效', 'unconfirmed')
        return False, f'{ref} 针对的不是当前提交或执行已失效', 'unconfirmed'
    return True, '独立验证通过，且覆盖该成功标准', 'evidence_matched'


def _evidence_result(repo: Path, evidence: dict, goal_id: str = '',
                     criterion_id: str = '') -> tuple[bool, str, str, bool, str]:
    """Return (valid, reason, trust, satisfies, state)."""
    if not isinstance(evidence, dict):
        return False, '证据项必须是对象', 'invalid', False, 'invalid'
    kind = str(evidence.get('kind') or '').strip()
    ref = str(evidence.get('ref') or '').strip()
    if kind == 'verification':
        ok, reason, trust = _verification_ok(repo, evidence, goal_id, criterion_id)
        return ok, reason, trust, ok, 'evidence_matched' if ok else 'unconfirmed'
    if kind == 'commit':
        if not GIT_SHA.fullmatch(ref):
            return False, 'commit 证据必须是完整的 40 位 SHA', 'invalid', False, 'invalid'
        if not _commit_exists(repo, ref):
            return False, f'提交不存在：{ref}', 'invalid', False, 'invalid'
        if _is_ancestor(repo, ref, git_sha_optional(repo)) is False:
            return False, f'提交不在当前 HEAD 历史中：{ref}', 'invalid', False, 'invalid'
        return (True, '提交存在且在当前历史中；提交本身不证明成功标准已被覆盖',
                'artifact', False, 'artifact_only')
    if kind == 'test':
        problem = _log_problem(repo, ref)
        if problem:
            return False, problem, 'invalid', False, 'invalid'
        if evidence.get('exit_code') != 0:
            return False, '测试证据的 exit_code 必须为 0', 'invalid', False, 'invalid'
        return (True, '有本地测试日志和 0 退出码；但缺少 criterion 映射和独立 coverage 复核',
                'locally_observed', False, 'executed_not_matched')
    if kind == 'manual':
        # R-1 Fix: Validate approved_by is a verifiable human identity
        approved_by = evidence.get('approved_by')
        if not approved_by:
            return False, 'manual 证据必须提供 approved_by', 'invalid', False, 'invalid'
        approval_id_problem = _approved_by_problem(approved_by)
        if approval_id_problem:
            return False, approval_id_problem, 'invalid', False, 'invalid'
        problem = _approval_problem(ref)
        if problem:
            return False, problem, 'invalid', False, 'invalid'
        # R-1: an email-shaped approved_by plus an approval ref is still only a
        # caller claim. There is no trusted approval event source in this build,
        # so the best possible state is UNVERIFIED_APPROVAL; it never satisfies
        # a criterion and never grants human_approved trust.
        return (True, f'人工批准声明（{approved_by}，引用 {ref}）尚未由可信组件核验；'
                      '不能单独证明标准达成',
                'unverified_approval', False, 'UNVERIFIED_APPROVAL')
    return False, f'未知证据类型：{kind}', 'invalid', False, 'invalid'


def evaluate_goal(repo: Path, goal_id: str) -> dict:
    goal = load_goal(repo, goal_id)
    criteria_out, blocking, partial = [], [], []
    open_high = _open_high_defects(repo, goal_id)
    for criterion in goal.get('success_criteria', []):
        evidence_out = []
        satisfied = False
        reviewable = False
        for evidence in criterion.get('evidence', []):
            valid, reason, trust, satisfies, state = _evidence_result(
                repo, evidence, goal_id, criterion['id'])
            evidence_out.append({**evidence, 'ok': valid, 'satisfies': satisfies,
                                 'reason': reason, 'trust': trust, 'state': state})
            if satisfies:
                satisfied = True
            # R-1: manual evidence is reviewable but never auto-satisfying; an
            # UNVERIFIED_APPROVAL must be reviewed by a human before it counts.
            if valid and state in ('executed_not_matched', 'evidence_matched',
                                   'human_review_required', 'UNVERIFIED_APPROVAL',
                                   'human_approved', 'externally_verified'):
                reviewable = True
        if satisfied:
            status = 'satisfied'
        elif reviewable:
            status = 'needs_review'
            partial.append(criterion['id'])
        else:
            status = 'insufficient_evidence'
        if criterion.get('required') and not satisfied:
            blocking.append(criterion['id'])
        criteria_out.append({'id': criterion['id'], 'statement': criterion['statement'],
                             'required': criterion.get('required', True), 'status': status,
                             'evidence': evidence_out})
    required = [c for c in criteria_out if c.get('required')]
    # R1 (#19): an empty required set is not a vacuous success.  A hand-edited
    # Goal can flip every criterion to optional or delete them; ``all([])`` must
    # never be read as "satisfied".  Fail closed with a machine-readable marker.
    no_required_criteria = not required
    required_satisfied = bool(required) and all(c['status'] == 'satisfied' for c in required)
    if no_required_criteria:
        state = 'insufficient_evidence'
        recommendation = 'insufficient_evidence'
    elif open_high:
        state = 'blocked_by_defect'
        recommendation = 'fix_defects'
    elif required_satisfied:
        state = 'satisfied'
        recommendation = 'achieved'
    elif any(c['status'] == 'needs_review' for c in required):
        state = 'needs_review'
        recommendation = 'needs_review'
    elif any(c['status'] == 'satisfied' for c in required):
        state = 'partial'
        recommendation = 'not_achieved'
    else:
        state = 'insufficient_evidence'
        recommendation = 'insufficient_evidence'
    satisfied = state == 'satisfied'
    audit_report = audit_verify(repo)
    result = {
        'schema_version': '1.2', 'kind': 'goal_evaluation', 'goal_id': goal_id,
        'goal_status': goal['status'], 'satisfied': satisfied,
        'recorded_status': goal['status'],
        'recorded_status_consistent': goal['status'] != 'achieved' or satisfied,
        'status_authority': 'local_untrusted',
        'evaluation_status': state, 'criteria': criteria_out,
        'no_required_criteria': no_required_criteria,
        'blocking': blocking, 'partial': partial,
        'open_high_defects': [d['defect_id'] for d in open_high],
        'recommendation': recommendation,
        'audit': audit_verify_summary(audit_report),
        'caveat': ('只接受带 criterion evidence mapping 且 coverage 经独立复核的证据；'
                   '直接 test/commit 证据和旧验证记录可读，但不能单独证明标准已达成。'
                   'CLI 不能判断语义相关性，仍需人工审查。'),
    }
    effective, trusted, status_problems = _achieved_status(
        repo, goal, satisfied, result, audit_report)
    result['raw_status'] = goal['status']
    if no_required_criteria:
        status_problems = list(dict.fromkeys(
            [*status_problems, 'no_required_criteria']))
    result['effective_status'] = effective
    result['status_trusted'] = trusted
    result['status_problems'] = status_problems
    if effective == 'achieved':
        result['status_authority'] = 'anchor_signed_checkpoint'
    if goal['status'] == 'achieved' and effective != 'achieved':
        result['recommendation'] = 'checkpoint_required'
    return result


def audit_verify_summary(report: dict) -> dict:
    return {'status': report.get('status'), 'valid': report.get('valid'),
            'authoritative': report.get('authoritative'),
            'entries': report.get('entries'), 'head': report.get('head'),
            'problems': list(report.get('problems') or []),
            'migration_sha256': report.get('migration_sha256'),
            'checkpoint': report.get('checkpoint')}


def add_goal_evidence(repo: Path, goal_id: str, criterion_id: str, kind: str, ref: str,
                      note: str = '', approved_by: str | None = None, exit_code: int | None = None) -> dict:
    goal = load_goal(repo, goal_id)
    evidence = {'kind': kind, 'ref': ref.strip(), 'note': note.strip()}
    if approved_by:
        evidence['approved_by'] = approved_by
    if exit_code is not None:
        evidence['exit_code'] = exit_code
    valid, reason, trust, _, state = _evidence_result(repo, evidence, goal_id, criterion_id)
    if not valid:
        _audit_attempt(repo, outcome='rejected', reason='goal_evidence_invalid',
                       goal_id=goal_id, criterion_id=criterion_id,
                       evidence_kind=kind, evidence_ref=evidence.get('ref'),
                       evidence_trust=trust, evidence_state=state,
                       verified=False, detail=reason)
        raise PMError(f'证据无效：{reason}')
    if not any(criterion.get('id') == criterion_id for criterion in goal.get('success_criteria', [])):
        raise PMError(f'Goal {goal_id} 没有 criterion {criterion_id}')

    def mutate(current):
        for criterion in current.get('success_criteria', []):
            if criterion.get('id') != criterion_id:
                continue
            items = criterion.setdefault('evidence', [])
            if not any(x.get('kind') == kind and x.get('ref') == ref.strip() for x in items):
                items.append(evidence)
            return current
        raise PMError(f'Goal {goal_id} 没有 criterion {criterion_id}')

    updated = _mutate(_goal_path(repo, goal_id), mutate)
    return {'schema_version': '1.2', 'kind': 'goal_evidence_result', 'goal_id': goal_id,
            'criterion': criterion_id, 'evidence': evidence, 'goal': updated}


def transition_goal(repo: Path, goal_id: str, target: str, approved_by: str | None = None,
                    reason: str = '', dry_run: bool = False) -> dict:
    current = load_goal(repo, goal_id)
    source = current['status']
    if target not in GOAL_STATUSES:
        raise PMError('goal status 必须是以下之一：' + '、'.join(sorted(GOAL_STATUSES)))
    if target == source:
        return {'schema_version': '1.2', 'kind': 'goal_transition_result', 'goal': current,
                'changed': False, 'reason': '状态未变化'}
    if target not in GOAL_TRANSITIONS[source]:
        raise PMError(f'不允许的 Goal 状态转换：{source} -> {target}')
    if target in ('approved', 'achieved') and not approved_by:
        raise PMError(f'转换到 {target} 必须提供 --approved-by（人工批准）')
    # R-1 Fix: Validate approved_by for goal transitions is a verifiable human identity
    if approved_by:
        approval_id_problem = _approved_by_problem(approved_by)
        if approval_id_problem:
            raise PMError(f'Goal 批准人身份无效：{approval_id_problem}')
    if target in ('blocked', 'cancelled') and not reason.strip():
        raise PMError(f'转换到 {target} 必须提供 --reason')
    evaluation = None
    if target == 'achieved':
        evaluation = evaluate_goal(repo, goal_id)
        if not evaluation['satisfied']:
            detail = '、'.join(evaluation['blocking']) or '无'
            _audit_attempt(repo, outcome='rejected', reason='goal_achieved_unsatisfied',
                           goal_id=goal_id, evaluation_status=evaluation['evaluation_status'],
                           no_required_criteria=evaluation.get('no_required_criteria', False),
                           blocking=evaluation['blocking'], verified=False,
                           detail='local Goal status cannot be authoritative without signed evidence')
            raise PMError(f'Goal 的成功标准尚未满足（{evaluation["evaluation_status"]}）：{detail}；'
                          '不能仅凭 Issue 关闭或 Agent 声明标记 achieved')

    def mutate(goal):
        goal['status'] = target
        if approved_by:
            goal['approved_by'] = approved_by
            goal.setdefault('approvals', []).append({'at': utc_now(), 'by': approved_by,
                                                     'from': source, 'to': target, 'reason': reason,
                                                     'approval_authority': 'claimed_unverified'})
        goal.setdefault('history', []).append({'at': utc_now(), 'from': source, 'to': target,
                                               'by': approved_by or goal.get('owner'), 'reason': reason})
        return goal
    updated = mutate(copy.deepcopy(current)) if dry_run else _mutate(_goal_path(repo, goal_id), mutate)
    result = {'schema_version': '1.2', 'kind': 'goal_transition_result', 'goal': updated,
              'changed': True, 'evaluation': evaluation, 'dry_run': dry_run}
    if dry_run:
        return result
    try:
        _audit_attempt(repo, outcome='applied', reason='goal_transition',
                       goal_id=goal_id, from_status=source, to_status=target,
                       approved_by=approved_by, goal_revision=updated.get('revision'))
    except PMError as exc:
        result['audit_error'] = str(exc)
    if target in AUDITED_GOAL_STATUSES:
        try:
            result['checkpoint_request'] = write_audit_checkpoint_request(
                repo, goal_id, approved_by, target)
        except PMError as exc:
            result['checkpoint_request'] = {'error': str(exc),
                                            'requires': 'achieved 在 anchor 签名 checkpoint 前不生效'}
    return result


def goal_show(repo: Path, goal_id: str) -> dict:
    goal = load_goal(repo, goal_id)
    runs = [r for r in iter_runs(repo) if r.get('goal_id') == goal_id]
    verifications = [v for v in iter_verifications(repo) if v.get('goal_id') == goal_id]
    defects = [d for d in iter_defects(repo) if d.get('goal_id') == goal_id]
    run_counts = {}
    for run in runs:
        run_counts[run['status']] = run_counts.get(run['status'], 0) + 1
    open_defects = [d for d in defects if d.get('status') in ('open', 'fixed')]
    evaluation = evaluate_goal(repo, goal_id)
    trusted_verified = [v for v in verifications if _record_verified(repo, v)]
    claimed_verified = [v for v in verifications
                        if v.get('verified') and not _record_verified(repo, v)]
    return {
        'schema_version': '1.2', 'kind': 'goal_show_result', 'goal': goal,
        'progress': {
            'runs': run_counts,
            'tasks': sorted({str(r.get('task')) for r in runs}),
            'verifications': len(verifications),
            'verified_verifications': len(trusted_verified),
            'claimed_verified_verifications': len(claimed_verified),
            'defects': len(defects),
            'open_defects': len(open_defects),
        },
        'status_authority': evaluation['status_authority'],
        'status_consistent': evaluation['recorded_status_consistent'],
        'raw_status': goal['status'],
        'effective_status': evaluation['effective_status'],
        'status_trusted': evaluation['status_trusted'],
        'status_problems': evaluation['status_problems'],
        'audit': evaluation['audit'],
        'evaluation': evaluation,
        'runs': runs,
        'verifications': verifications,
        'defects': defects,
        'caveat': 'Goal 进度是关联记录的数量；Goal 是否达成只看成功标准，不看 Issue 是否关闭。',
    }


def goal_list(repo: Path) -> dict:
    goals = sorted(iter_goals(repo), key=lambda g: g.get('id', ''))
    return {'schema_version': '1.2', 'kind': 'goal_list_result',
            'goals': [{'id': g.get('id'), 'title': g.get('title'), 'status': g.get('status'),
                       'owner': g.get('owner'), 'updated_at': g.get('updated_at')} for g in goals]}


# ---------------------------------------------------------------- runs

def start_run(repo: Path, goal_id: str, task, run_id: str, agent: str,
              model_provider: str, model_id: str,
              tool: str | None = None, session_id: str | None = None,
              branch: str | None = None, base_sha: str | None = None,
              authorization: str | None = None, status: str = 'running',
              role: str = 'executor', dry_run: bool = False) -> dict:
    load_goal(repo, goal_id)
    task_id = task_id_of({'id': task})
    run_id = validate_identifier(run_id, 'run_id')
    agent = validate_identifier(agent, 'agent')
    model_provider = _single_line(model_provider, 'model provider')
    model_id = _single_line(model_id, 'model id')
    if role not in RUN_ROLES:
        raise PMError('run role 必须是以下之一：' + '、'.join(sorted(RUN_ROLES)))
    if status not in RUN_STATUSES:
        raise PMError('run status 必须是以下之一：' + '、'.join(sorted(RUN_STATUSES)))
    if status not in ACTIVE_RUN_STATUSES:
        raise PMError('新建执行记录只能是 queued、running 或 paused')
    head = base_sha or git_sha_optional(repo)
    if head and not GIT_SHA.fullmatch(head):
        raise PMError('base_sha 必须是完整的 40 位 Git SHA')
    if head and not _commit_exists(repo, head):
        raise PMError(f'base_sha 不存在：{head}')
    for other in iter_runs(repo):
        if other.get('run_id') == run_id and _task_key(other.get('task')) != _task_key(task_id):
            raise PMError(f'run_id {run_id} 已被任务 {other.get("task")} 使用；run_id 必须全局唯一')
    record = {
        'schema_version': '1.2', 'kind': 'agent_run', 'run_id': run_id,
        'goal_id': goal_id, 'task': task_id, 'agent': agent, 'role': role,
        'model': {'provider': model_provider, 'id': model_id},
        'tool': tool or '', 'session_id': session_id or '',
        'git': {'base_sha': head, 'head_sha': head, 'branch': branch or _branch(repo)},
        'authorization': authorization or '',
        'status': status, 'created_at': utc_now(), 'updated_at': utc_now(),
        'started_at': utc_now() if status == 'running' else None, 'ended_at': None,
        'artifacts': [], 'evidence': [], 'blockers': [], 'handoff': None,
        'revision': 1,
    }
    path = _run_path(repo, task_id, run_id)
    identity = ('run_id', 'goal_id', 'task', 'agent', 'role', 'model', 'tool',
                'session_id', 'git', 'authorization', 'status')
    warnings = []
    for other in iter_runs(repo, task=task_id):
        if other.get('status') in ACTIVE_RUN_STATUSES and other.get('run_id') != run_id:
            warnings.append(f'同一任务已有活跃执行 {other.get("run_id")}（{other.get("agent")}）；本地没有分布式锁，需人工确认由谁继续。')
    result = {'schema_version': '1.2', 'kind': 'run_start_result', 'run': record,
              'path': relpath(repo, path), 'created': True, 'warnings': warnings, 'dry_run': dry_run}
    if dry_run:
        if path.is_file():
            existing = _load(path)
            if _diff(existing, record, identity):
                raise PMError(f'执行记录 {run_id} 已存在且内容不同：{path}')
            result.update({'run': existing, 'created': False})
        return result
    if not _write(path, record):
        existing = _load(path)
        if _diff(existing, record, identity):
            raise PMError(f'执行记录 {run_id} 已存在且内容不同：{path}')
        return {'schema_version': '1.2', 'kind': 'run_start_result', 'run': existing,
                'path': relpath(repo, path), 'created': False, 'warnings': warnings, 'dry_run': False}
    return result


def iter_runs(repo: Path, task=None, goal=None):
    runs = [safe_json(p) for p in _json_files(_root(repo, 'runs')) if not _is_checkpoint_path(p)]
    if task is not None:
        key = _task_key(task)
        runs = [r for r in runs if _task_key(r.get('task')) == key]
    if goal is not None:
        runs = [r for r in runs if r.get('goal_id') == goal]
    return sorted(runs, key=lambda r: (r.get('created_at') or '', r.get('run_id') or ''))


def load_run(repo: Path, task, run_id: str) -> dict:
    run_id = validate_identifier(run_id, 'run_id')
    return _load(_run_path(repo, task, run_id))


def _find_run_by_id(repo: Path, run_id: str):
    if not run_id:
        return None
    matches = []
    for path in _json_files(_root(repo, 'runs')):
        if _is_checkpoint_path(path):
            continue
        record = safe_json(path)
        if record.get('run_id') == run_id:
            matches.append((path, record))
    if len(matches) > 1:
        tasks = '、'.join(str(record.get('task')) for _, record in matches)
        raise PMError(f'run_id {run_id} 在多个任务中重复：{tasks}；请使用全局唯一的 run_id')
    return matches[0][0] if matches else None


def _find_record(repo: Path, kind: str, record_id: str):
    root = _root(repo, kind)
    for path in _json_files(root):
        record = safe_json(path)
        for key in ('id', 'run_id', 'verification_id', 'defect_id'):
            if record.get(key) == record_id:
                return path
    return None


def checkpoint_run(repo: Path, task, run_id: str, completed, remaining, blockers=None,
                   evidence=None, head_sha: str | None = None, note: str = '') -> dict:
    run = load_run(repo, task, run_id)
    if run['status'] not in ACTIVE_RUN_STATUSES:
        raise PMError(f'执行状态为 {run["status"]}，不能再写检查点')
    head = head_sha or git_sha_optional(repo) or run.get('git', {}).get('head_sha')
    if head and not GIT_SHA.fullmatch(head):
        raise PMError('head_sha 必须是完整的 40 位 Git SHA')
    record = {
        'schema_version': '1.2', 'kind': 'run_checkpoint', 'run_id': run_id,
        'task': run['task'], 'goal_id': run['goal_id'], 'head_sha': head,
        'completed': _list_of_strings(completed, 'completed'),
        'remaining': _list_of_strings(remaining, 'remaining'),
        'blockers': _list_of_strings(blockers, 'blockers'),
        'evidence': _list_of_strings(evidence, 'evidence'),
        'note': note.strip(), 'created_at': utc_now(),
    }
    if not record['completed'] and not record['remaining']:
        raise PMError('检查点必须写明已完成或剩余的工作')
    directory = _checkpoint_dir(repo, task, run_id)
    previous = sorted(directory.glob('*.json')) if directory.is_dir() else []
    if previous:
        latest = safe_json(previous[-1])
        for key in ('completed', 'remaining', 'blockers', 'evidence', 'head_sha', 'note'):
            if latest.get(key) != record.get(key):
                break
        else:
            return {'schema_version': '1.2', 'kind': 'run_checkpoint_result', 'checkpoint': latest,
                    'path': relpath(repo, previous[-1]), 'created': False}
    for index in range(len(previous) + 1, len(previous) + 200):
        path = directory / f'{index:04d}.json'
        if _write(path, record):
            return {'schema_version': '1.2', 'kind': 'run_checkpoint_result', 'checkpoint': record,
                    'path': relpath(repo, path), 'created': True}
    raise PMError('无法分配检查点序号：并发冲突过多')


def _handoff_path(repo: Path, task, run_id: str) -> Path:
    return repo / '.project-memory' / 'handoffs' / _task_key(task) / (run_id + '.json')


def _iter_checkpoints(repo: Path, task, run_id: str):
    directory = _checkpoint_dir(repo, task, run_id)
    return [safe_json(p) for p in sorted(directory.glob('*.json'))] if directory.is_dir() else []


def finish_run(repo: Path, task, run_id: str, completed, remaining, blockers=None,
               evidence=None, head_sha: str | None = None, commits=None,
               changed_files=None, tests=None, open_questions=None, next_actions=None,
               status: str = 'submitted', dry_run: bool = False) -> dict:
    run = load_run(repo, task, run_id)
    if run['status'] in ('verified', 'cancelled', 'superseded'):
        raise PMError(f'执行状态为 {run["status"]}，不能执行 finish')
    if status not in ('submitted', 'failed', 'cancelled'):
        raise PMError('finish 只能把执行设置为 submitted、failed 或 cancelled')
    _check_run_transition(run, status)
    head = head_sha or git_sha_optional(repo) or run.get('git', {}).get('head_sha')
    if head and not GIT_SHA.fullmatch(head):
        raise PMError('head_sha 必须是完整的 40 位 Git SHA')
    if head and not _commit_exists(repo, head):
        raise PMError(f'head_sha 不存在：{head}')
    test_list = tests or []
    if not isinstance(test_list, list):
        raise PMError('tests 必须是数组')
    for item in test_list:
        if not isinstance(item, dict) or not item.get('command'):
            raise PMError('每条测试证据必须包含 command')
        if not isinstance(item.get('exit_code'), int):
            raise PMError('每条测试证据必须包含整数 exit_code')
        problem = _log_problem(repo, item.get('log'))
        if problem:
            raise PMError(f'测试证据日志无效：{problem}')
    commit_list = _list_of_strings(commits, 'commits')
    for sha in commit_list:
        if not GIT_SHA.fullmatch(sha):
            raise PMError(f'commit 必须是完整的 40 位 SHA：{sha!r}')
        if not _commit_exists(repo, sha):
            raise PMError(f'commit 不存在：{sha}')
    files = _list_of_strings(changed_files, 'changed_files')
    cfg = load_config(repo)
    docs = [f for f in files if any(f.startswith(root.rstrip('/') + '/') for root in cfg['doc_roots']) and f.endswith('.md')]
    metadata = {
        'goal_id': run['goal_id'], 'from_run': run_id, 'model': run['model'],
        'session_id': run.get('session_id', ''), 'head_sha': head,
        'commits': commit_list, 'changed_files': files, 'tests': test_list,
        'docs_changed': docs,
        'open_questions': _list_of_strings(open_questions, 'open_questions'),
        'next_actions': _list_of_strings(next_actions, 'next_actions'),
    }
    handoff_path = _handoff_path(repo, run['task'], run_id)
    if handoff_path.is_file():
        existing_handoff = safe_json(handoff_path)
        if existing_handoff.get('schema_version') == '1.1':
            raise PMError(f'{run_id} 已有 1.1 handoff；1.1 不可原地升级为 1.2，请使用新的 run ID 记录本次 finish')
    if dry_run:
        return {'schema_version': '1.2', 'kind': 'run_finish_result', 'run_id': run_id,
                'would_write_handoff': relpath(repo, handoff_path), 'metadata': metadata,
                'handoff_exists': handoff_path.is_file(), 'dry_run': True}
    record = write_handoff(repo, run['task'], run['agent'], run_id, completed, remaining,
                           blockers or [], evidence or [], run.get('git', {}).get('base_sha'),
                           metadata=metadata)
    updated = _mutate(_run_path(repo, run['task'], run_id), lambda current: {
        **current, 'status': status, 'git': {**current.get('git', {}), 'head_sha': head},
        'ended_at': utc_now(), 'handoff': relpath(repo, handoff_path),
        'evidence': list(current.get('evidence', [])) + _list_of_strings(evidence, 'evidence'),
        'blockers': _list_of_strings(blockers, 'blockers'),
    })
    return {'schema_version': '1.2', 'kind': 'run_finish_result', 'run': updated,
            'handoff': record, 'handoff_path': relpath(repo, handoff_path)}


def resume_run(repo: Path, task, run_id: str | None = None, goal_id: str | None = None) -> dict:
    runs = iter_runs(repo, task=task, goal=goal_id)
    if not runs:
        return {'schema_version': '1.2', 'kind': 'run_resume_result', 'task': str(task),
                'status': 'no_run', 'warnings': ['没有找到执行记录。'],
                'next_actions': ['先创建 Goal 和 run start，或确认任务 ID。']}
    executors = [r for r in runs if r.get('role', 'executor') != 'verifier']
    active = [r for r in executors if r.get('status') in ACTIVE_RUN_STATUSES]
    selected = None
    if run_id:
        selected = next((r for r in runs if r.get('run_id') == run_id), None)
        if selected is None:
            raise PMError(f'任务 {task} 没有执行记录 {run_id}')
    else:
        selected = active[-1] if active else (executors[-1] if executors else runs[-1])
    handoff = None
    handoff_path = _handoff_path(repo, selected['task'], selected['run_id'])
    if handoff_path.is_file():
        handoff = safe_json(handoff_path)
    inherited_from = None
    inherited_handoff = None
    if handoff is None and selected.get('status') in ACTIVE_RUN_STATUSES:
        earlier = executors[:next((i for i, r in enumerate(executors)
                                   if r.get('run_id') == selected.get('run_id')), 0)]
        for other in reversed(earlier):
            if other.get('status') not in ('submitted', 'verified', 'failed'):
                continue
            candidate = _handoff_path(repo, selected['task'], other['run_id'])
            if candidate.is_file():
                inherited_from = other['run_id']
                inherited_handoff = safe_json(candidate)
                break
    checkpoints = _iter_checkpoints(repo, selected['task'], selected['run_id'])
    latest_checkpoint = checkpoints[-1] if checkpoints else None
    verifications = [v for v in iter_verifications(repo, task=task, target_run=selected['run_id'])]
    current_verifications = [v for v in verifications
                             if _record_verified(repo, v) and _verification_current(repo, v)]
    defects = [d for d in iter_defects(repo, task=task) if d.get('target_run') == selected['run_id']]
    current_head = git_sha_optional(repo)
    base = (selected.get('git') or {}).get('base_sha')
    head = (selected.get('git') or {}).get('head_sha')
    warnings, checks = [], []
    if len(active) > 1:
        warnings.append('同一任务有多个活跃执行：' + '、'.join(r['run_id'] for r in active))
    if base and current_head:
        ancestor = _is_ancestor(repo, base, current_head)
        checks.append({'id': 'base_is_ancestor', 'status': 'pass' if ancestor else 'fail',
                       'detail': f'base={base} head={current_head}'})
        if ancestor is False:
            warnings.append('基准提交不在当前 HEAD 历史中，必须先人工对齐分支。')
    else:
        checks.append({'id': 'base_is_ancestor', 'status': 'unknown', 'detail': '没有 Git 基准'})
    if head and current_head and head != current_head:
        warnings.append(f'执行记录 head 与当前 HEAD 不同：{head} != {current_head}')
        checks.append({'id': 'head_matches_current', 'status': 'warn', 'detail': f'{head} != {current_head}'})
    else:
        checks.append({'id': 'head_matches_current', 'status': 'pass', 'detail': head or '无 head'})
    if handoff is None and inherited_handoff is None:
        checks.append({'id': 'handoff_present', 'status': 'fail', 'detail': 'missing'})
        if latest_checkpoint is not None and selected.get('status') in ACTIVE_RUN_STATUSES:
            warnings.append('没有 handoff；使用最近检查点恢复，仍需核对提交和测试。')
        else:
            warnings.append('没有 handoff；只能从代码、提交和运行记录恢复。')
    elif handoff is None:
        checks.append({'id': 'handoff_present', 'status': 'pass',
                       'detail': f'inherited from {inherited_from}'})
        warnings.append(
            f'当前执行没有自己的 handoff；继承自 {inherited_from}，继续前必须核对提交和测试。')
    else:
        checks.append({'id': 'handoff_present', 'status': 'pass', 'detail': relpath(repo, handoff_path)})
        if handoff.get('schema_version') == '1.1':
            warnings.append('handoff 是 1.1 旧契约，缺少模型、head SHA、测试证据和下一步。')
    source = handoff or inherited_handoff or latest_checkpoint or {}
    multiple_active = len(active) > 1
    stale_base = any(w.startswith('基准提交不在') for w in warnings)
    if selected.get('status') == 'verified':
        if current_verifications and (not head or not current_head or head == current_head):
            resume_status = 'verified'
        else:
            warnings.append('执行标记为 verified，但验证绑定的提交不是当前 HEAD；需要重新验证。')
            resume_status = 'needs_human'
    elif current_verifications:
        resume_status = 'verified'
    elif stale_base:
        resume_status = 'stale_base'
    elif multiple_active:
        resume_status = 'needs_human'
    elif handoff is None and inherited_handoff is None and not (latest_checkpoint is not None and selected.get('status') in ACTIVE_RUN_STATUSES):
        resume_status = 'needs_handoff'
    else:
        resume_status = 'resume_ready'
    return {
        'schema_version': '1.2', 'kind': 'run_resume_result', 'task': str(task),
        'goal_id': selected.get('goal_id'), 'run_id': selected['run_id'],
        'status': resume_status, 'base_sha': base, 'head_sha': head,
        'current_head_sha': current_head, 'model': selected.get('model'),
        'role': selected.get('role', 'executor'),
        'completed': source.get('completed', []),
        'remaining': source.get('remaining', []),
        'blockers': source.get('blockers', []),
        'open_questions': source.get('open_questions', []),
        'next_actions': source.get('next_actions', []),
        'tests': source.get('tests', []),
        'handoff_inherited_from': inherited_from,
        'checkpoints': len(checkpoints),
        'latest_checkpoint': latest_checkpoint,
        'verifications': verifications, 'current_verifications': current_verifications,
        'defects': defects,
        'checks': checks, 'warnings': warnings,
        'caveat': '恢复包只汇总记录，不证明前一个 Agent 的声明为真；继续执行前必须核对提交和测试。',
    }


def run_show(repo: Path, task, run_id: str) -> dict:
    run = load_run(repo, task, run_id)
    handoff = None
    path = _handoff_path(repo, run['task'], run_id)
    if path.is_file():
        handoff = safe_json(path)
    return {'schema_version': '1.2', 'kind': 'run_show_result', 'run': run,
            'checkpoints': _iter_checkpoints(repo, run['task'], run_id),
            'handoff': handoff,
            'verifications': iter_verifications(repo, task=task, target_run=run_id),
            'defects': [d for d in iter_defects(repo, task=task) if d.get('target_run') == run_id]}


# ---------------------------------------------------------------- verification and defects

def iter_verifications(repo: Path, task=None, goal=None, target_run=None):
    values = [safe_json(p) for p in _json_files(_root(repo, 'verifications'))]
    if task is not None:
        key = _task_key(task)
        values = [v for v in values if _task_key(v.get('task')) == key]
    if goal is not None:
        values = [v for v in values if v.get('goal_id') == goal]
    if target_run is not None:
        values = [v for v in values if v.get('target_run') == target_run]
    return sorted(values, key=lambda v: (v.get('created_at') or '', v.get('verification_id') or ''))


def load_verification(repo: Path, task, verification_id: str) -> dict:
    return _load(_verification_path(repo, task, verification_id))


def iter_defects(repo: Path, task=None, status=None):
    values = [safe_json(p) for p in _json_files(_root(repo, 'defects'))]
    if task is not None:
        key = _task_key(task)
        values = [d for d in values if _task_key(d.get('task')) == key]
    if status is not None:
        values = [d for d in values if d.get('status') == status]
    return sorted(values, key=lambda d: (d.get('created_at') or '', d.get('defect_id') or ''))


def load_defect(repo: Path, defect_id: str) -> tuple[dict, Path]:
    path = _find_record(repo, 'defects', defect_id)
    if path is None:
        raise PMError(f'缺陷不存在：{defect_id}')
    return _load(path), path


def _findings(value) -> list[dict]:
    if isinstance(value, dict):
        value = value.get('findings', [])
    if not isinstance(value, list):
        raise PMError('findings 必须是数组或包含 findings 数组的对象')
    out = []
    for item in value:
        if not isinstance(item, dict):
            raise PMError('每条 finding 必须是对象')
        severity = str(item.get('severity') or '').strip()
        if severity not in SEVERITIES:
            raise PMError('finding severity 必须是 high、medium 或 low')
        summary = _single_line(str(item.get('summary') or ''), 'finding summary')
        file = str(item.get('file') or '').strip()
        line = item.get('line')
        if line is not None and (not isinstance(line, int) or line < 1):
            raise PMError('finding line 必须是正整数')
        out.append({'severity': severity, 'file': file, 'line': line,
                    'summary': summary, 'repro': str(item.get('repro') or '').strip()})
    return out


def _verification_inputs(test_command, test_exit, test_log, ci_url, ci_status,
                         review_url, review_state, evidence_level, verdict,
                         test_receipt=None, pr_number=None):
    if verdict not in ('pass', 'fail', 'inconclusive'):
        raise PMError('verdict 必须是 pass、fail 或 inconclusive')
    if evidence_level not in EVIDENCE_LEVELS:
        raise PMError('evidence level 必须是以下之一：' + '、'.join(sorted(EVIDENCE_LEVELS)))
    if verdict == 'pass' and evidence_level == 'agent_claimed':
        raise PMError('Agent 自报不能作为 pass；请提供本地日志、外部 CI 或人工批准')
    # B-9: externally_verified may only be declared together with --pr, which
    # reads the real CI outcome.  The record still caps trust at the observed
    # evidence (min() below), so a failed fetch or a SHA mismatch degrades to
    # agent_claimed instead of raising.
    if evidence_level == 'externally_verified' and not pr_number:
        raise PMError('externally_verified 需要 --pr 从 GitHub 读取 CI 状态；'
                      '没有外部取证时不能声明该等级')
    # D-1: the non-PASS branch never fetches CI, so it must not echo a declared
    # externally_verified back as observed trust.  Only a green CI on a PASS can
    # establish external evidence.
    if evidence_level == 'externally_verified' and verdict != 'pass':
        raise PMError('externally_verified 只适用于 pass；'
                      'fail/inconclusive 不能声明该等级')
    if evidence_level == 'human_approved':
        raise PMError('human_approved 不能作为声明的 evidence level；'
                      '人工批准必须通过 verification 记录与 criterion mapping 证明')
    log_path = None
    if test_log:
        log_path = Path(test_log)
        if not log_path.is_absolute():
            # Resolved by caller against the repo; kept as text in the record.
            pass
    if evidence_level == 'locally_observed':
        if not test_receipt:
            raise PMError('locally_observed 需要可信执行收据（test-run 生成）；'
                          'Agent 手写的 test log 不构成执行证据')
        if not test_command or not isinstance(test_exit, int):
            raise PMError('locally_observed 需要 test command 和整数 test exit')
    if ci_url and not _valid_http_url(ci_url):
        raise PMError('CI URL 必须是 http(s) 地址')
    if review_url and not _valid_http_url(review_url):
        raise PMError('review URL 必须是 http(s) 地址')
    if verdict == 'pass' and evidence_level == 'locally_observed' and test_exit != 0:
        raise PMError('测试没有通过，不能给出 pass')
    return log_path


def _ci_payload(ci_url, ci_status, external_ci, pr_number, target_head,
                fetch_info=None) -> dict:
    """Shape the checks.ci record; never store tokens, only the fetched outcome."""
    info = fetch_info or {}
    repository = info.get('repository') or ''
    fetch = info.get('fetch') or 'not_requested'
    if external_ci is None:
        return {'url': ci_url or '', 'status': ci_status or 'not_provided',
                'provenance': 'declared_unfetched' if ci_url else 'none',
                'repository': repository, 'fetch': fetch}
    return {'url': ci_url or '', 'status': external_ci.get('status'),
            'declared_status': ci_status or 'not_provided',
            'provenance': 'github_api', 'pr': pr_number,
            'repository': repository, 'fetch': fetch,
            'head_sha': external_ci.get('head_sha'),
            'head_sha_matches_target': external_ci.get('head_sha') == target_head,
            'truncated': bool(external_ci.get('truncated')),
            'runs': external_ci.get('runs') or []}


def verify_run(repo: Path, target_run: str, verifier_run: str, standard: str,
               verdict: str, evidence_level: str, test_command: str | None = None,
               test_exit: int | None = None, test_log: str | None = None,
               ci_url: str | None = None, ci_status: str | None = None,
               review_url: str | None = None, review_state: str | None = None,
               findings=None, verification_id: str | None = None,
               resolves_defects=None, expected_sha: str | None = None,
               criterion_evidence=None, test_receipt: str | None = None,
               dry_run: bool = False, pr_number: int | None = None) -> dict:
    target_path = _find_run_by_id(repo, target_run)
    verifier_path = _find_run_by_id(repo, verifier_run)
    if target_path is None:
        raise PMError(f'被验证的执行不存在：{target_run}')
    if verifier_path is None:
        raise PMError(f'验证者的执行不存在：{verifier_run}')
    if target_run == verifier_run:
        raise PMError('验证者不能是被验证的同一个执行')
    target = _load(target_path)
    verifier = _load(verifier_path)
    if _task_key(verifier.get('task')) != _task_key(target.get('task')):
        raise PMError('验证执行必须与被验证执行属于同一任务')
    if verifier.get('goal_id') != target.get('goal_id'):
        raise PMError('验证执行必须与被验证执行属于同一 Goal')
    if target.get('status') not in ('submitted', 'verified', 'failed'):
        raise PMError(f'被验证执行状态为 {target.get("status")}，需要先 run finish')
    independence = _independence(target, verifier)
    goal = load_goal(repo, target.get('goal_id'))
    standard = _single_line(standard, 'verification standard')
    target_head = (target.get('git') or {}).get('head_sha')
    current_head = git_sha_optional(repo)
    if expected_sha and expected_sha != target_head:
        raise PMError(f'expected SHA {expected_sha} 与被验证执行 head {target_head} 不一致')
    if target_head and not GIT_SHA.fullmatch(target_head):
        raise PMError('被验证执行的 head_sha 不是完整 SHA')
    if target_head and not _commit_exists(repo, target_head):
        raise PMError(f'被验证提交不存在：{target_head}')
    receipt_info = None
    if test_receipt:
        receipt_info = verify_receipt(repo, test_receipt,
                                      expected={'commit_sha': target_head})
        if not receipt_info['valid']:
            raise PMError('执行收据无效：' + '；'.join(receipt_info['problems']))
        receipt = receipt_info['receipt']
        if test_command and test_command != receipt['command']:
            raise PMError('test command 与执行收据记录的命令不一致')
        if test_exit is not None and test_exit != receipt['exit_code']:
            raise PMError('test exit 与执行收据记录的退出码不一致')
        test_command = receipt['command']
        test_exit = receipt['exit_code']
        test_log = receipt['log_path']
    _verification_inputs(test_command, test_exit, test_log, ci_url, ci_status,
                         review_url, review_state, evidence_level, verdict,
                         test_receipt=test_receipt, pr_number=pr_number)
    stale = bool(current_head and target_head and current_head != target_head)
    finding_list = _findings(findings or [])
    if verdict == 'pass' and any(f['severity'] == 'high' for f in finding_list):
        raise PMError('存在 high 级缺陷时不能给出 pass')
    if verdict == 'pass' and stale:
        raise PMError('代码已经变化，不能对旧提交给出 pass；请先重新对齐并复验')
    if evidence_level == 'locally_observed':
        problem = _log_problem(repo, test_log)
        if problem:
            raise PMError(problem)
    # T-03: bind log content hash so later edits invalidate the record.
    log_hash = None
    if test_log and _log_problem(repo, test_log) is None:
        log_path = Path(test_log)
        if not log_path.is_absolute():
            log_path = repo / log_path
        if log_path.is_file():
            from .common import sha256_file
            log_hash = sha256_file(log_path)
    # T-04 (fixed): record tracked-file state only. Untracked receipts/logs must not
    # make a clean verification look dirty.
    _wt_code, _wt_out = _git(repo, 'status', '--porcelain', '--untracked-files=no')
    tracked_status = _wt_out.strip()
    worktree_dirty = bool(tracked_status)
    tracked_diff_sha256 = _tracked_diff_sha256(repo)
    criterion_entries, mapping = [], {'status': 'missing', 'required': [],
                                      'covered': [], 'partial': [], 'missing': [],
                                      'unexpected': [], 'problems': []}
    external_ci = None
    ci = None
    if verdict == 'pass':
        if not target_head:
            raise PMError('PASS 需要被验证执行绑定完整 head SHA')
        resolved_ids = set(resolves_defects or [])
        blocking_defects = [d for d in _open_high_defects(repo, goal['id'])
                            if d.get('defect_id') not in resolved_ids]
        if blocking_defects:
            _audit_attempt(repo, outcome='rejected', reason='blocking_high_defects',
                           target_run=target_run, verifier_run=verifier_run,
                           standard=standard, verdict=verdict,
                           evidence_level=evidence_level,
                           blocking_defects=[d['defect_id'] for d in blocking_defects],
                           verified=False, worktree_dirty=worktree_dirty,
                           tracked_changes=tracked_status, log_content_sha256=log_hash)
            return {'schema_version': '1.2', 'kind': 'verify_result',
                    'status': 'BLOCKED_BY_DEFECT', 'verified': False,
                    'verification': None,
                    'reason': '存在未关闭的 high 缺陷，不能给出 PASS',
                    'blocking_defects': [d['defect_id'] for d in blocking_defects],
                    'dry_run': dry_run}
        external_ci, fetch_info = _external_ci_status(pr_number)
        ci = _ci_payload(ci_url, ci_status, external_ci, pr_number, target_head,
                         fetch_info=fetch_info)
        criterion_entries = _criterion_evidence_entries(
            criterion_evidence, repo, goal, target, verifier, target_head,
            external_ci=external_ci)
        mapping = _mapping_summary(criterion_entries, goal)
        if mapping['status'] not in ('complete', 'review_required'):
            status = _mapping_outcome(criterion_entries, mapping)
            _audit_attempt(repo, outcome='rejected', reason='incomplete_mapping',
                           target_run=target_run, verifier_run=verifier_run,
                           standard=standard, verdict=verdict,
                           evidence_level=evidence_level, mapping_status=status,
                           verified=False, worktree_dirty=worktree_dirty,
                           tracked_changes=tracked_status, log_content_sha256=log_hash,
                           receipt_id=(receipt_info or {}).get('receipt', {}).get('receipt_id'))
            return {'schema_version': '1.2', 'kind': 'verify_result',
                    'status': status, 'verified': False, 'verification': None,
                    'reason': ('PASS 需要覆盖全部必达标准的 criterion evidence mapping；'
                               '只有日志和退出码不足以证明覆盖'
                               if not criterion_entries else
                               'criterion evidence 未满足完整、已确认的覆盖要求'),
                    'mapping': mapping, 'criterion_evidence': criterion_entries,
                    'ci': ci, 'dry_run': dry_run}
    tests = {'command': test_command or '', 'exit_code': test_exit,
             'log': test_log or '', 'log_exists': bool(_log_problem(repo, test_log) is None),
             'log_content_sha256': log_hash,
             'worktree_dirty_at_verification': worktree_dirty,
             'tracked_changes_at_verification': tracked_status,
             'tracked_diff_sha256': tracked_diff_sha256,
             'receipt': (receipt_info or {}).get('path'),
             'receipt_id': (receipt_info or {}).get('receipt', {}).get('receipt_id'),
             'receipt_sha256': (receipt_info or {}).get('receipt', {}).get('content_sha256'),
             'snapshot_id': (receipt_info or {}).get('receipt', {}).get('snapshot_id'),
             'snapshot_sha256': (receipt_info or {}).get('receipt', {}).get('snapshot_sha256'),
             'receipt_integrity_valid': bool(receipt_info and receipt_info['valid']),
             'execution_trust': (receipt_info or {}).get('receipt', {}).get('trust'),
             'execution_provenance': (receipt_info or {}).get('provenance')}
    if ci is None:
        ci = _ci_payload(ci_url, ci_status, None, pr_number, target_head)
    review = {'url': review_url or '', 'state': review_state or 'not_provided',
              'provenance': 'declared_unfetched' if review_url else 'none'}
    observed_rank = max([EVIDENCE_TRUST.get(entry['observed_level'], 0)
                         for entry in criterion_entries] or [0])
    if verdict != 'pass':
        observed_rank = EVIDENCE_TRUST[evidence_level]
    trust_rank = min(EVIDENCE_TRUST[evidence_level], observed_rank)
    trust_level = next(level for level, rank in EVIDENCE_TRUST.items() if rank == trust_rank)
    # R-2: a machine can only establish an execution fact. Semantic coverage
    # remains unverified until a trusted human/external source confirms it, so
    # review_required records are written as MANUAL_REVIEW_REQUIRED and never
    # satisfy a goal.
    all_criteria_matched = (verdict == 'pass' and criterion_entries
                           and all(entry.get('evidence_matched') for entry in criterion_entries))
    structural_verified = (verdict == 'pass' and evidence_level == 'locally_observed'
                           and receipt_info is not None and receipt_info['valid']
                           and not stale and mapping['status'] == 'complete'
                           and all_criteria_matched
                           and not any(f['severity'] == 'high' for f in finding_list))
    # A record written by this local CLI has no detached signature from a
    # protected anchor.  Even a structurally complete record stays
    # MANUAL_REVIEW_REQUIRED until an external signer counter-signs it; this
    # build intentionally configures no signer, so it can never self-certify.
    if verdict == 'fail':
        status = 'FAILED'
    elif verdict == 'pass' and mapping['status'] == 'review_required':
        status = 'MANUAL_REVIEW_REQUIRED'
    elif structural_verified:
        status = 'MANUAL_REVIEW_REQUIRED'
    else:
        status = 'INCONCLUSIVE'
    verified = False
    _check_run_transition(target, 'failed' if verdict == 'fail' else target.get('status'))
    record = {
        'schema_version': '1.2', 'kind': 'verification_record',
        'verification_id': verification_id or _now_id('VER', target_run, target_head, verifier_run,
                                                       verdict, standard, json.dumps(finding_list, sort_keys=True)),
        'task': target.get('task'), 'goal_id': target.get('goal_id'),
        'target_run': target_run, 'verifier_run': verifier_run,
        'target_run_sha256': canonical_digest(target),
        'verifier_run_sha256': canonical_digest(verifier),
        'goal_criteria_sha256': _criteria_definition_digest(goal.get('success_criteria', [])),
        'goal_criteria_legacy_sha256': canonical_digest(goal.get('success_criteria', [])),
        'verifier': {'agent': verifier.get('agent'), 'model': verifier.get('model'),
                     'tool': verifier.get('tool'), 'session_id': verifier.get('session_id')},
        'independence': independence,
        'target_head_sha': target_head, 'current_head_sha': current_head, 'stale': stale,
        'standard': standard, 'verdict': verdict, 'evidence_level': evidence_level,
        'trust_level': trust_level,
        'status': status,
        'mapping_status': mapping['status'],
        'criterion_evidence': criterion_entries,
        'covered_criteria': mapping.get('covered', []),
        'missing_criteria': mapping.get('missing', []),
        'verified': verified, 'checks': {'tests': tests, 'ci': ci, 'review': review},
        'findings': [], 'created_at': utc_now(), 'revision': 1,
        'authority': untrusted_envelope(
            '记录由本地 CLI 写出；没有受保护信任锚的分离签名，不能自证权威'),
    }
    record['authority_evaluation'] = verification_authority(repo, record)
    if verification_id:
        validate_identifier(verification_id, 'verification id')
    # Build defect records before writing the verification so dry-run is complete.
    defects, defect_paths = [], []
    for index, finding in enumerate(finding_list, 1):
        defect_id = _now_id('DEF', target_run, record['verification_id'], index,
                            finding['file'], finding['summary'])
        defect = {
            'schema_version': '1.2', 'kind': 'defect', 'defect_id': defect_id,
            'task': record['task'], 'goal_id': record['goal_id'],
            'verification_id': record['verification_id'], 'target_run': target_run,
            'severity': finding['severity'],
            'location': {'file': finding['file'], 'line': finding['line']},
            'summary': finding['summary'], 'repro': finding['repro'],
            'status': 'open', 'fixed_in_sha': None, 'verified_by': None,
            'created_at': utc_now(), 'updated_at': utc_now(), 'revision': 1,
        }
        defects.append(defect)
        defect_paths.append(_defect_path(repo, record['task'], defect_id))
    record['findings'] = [d['defect_id'] for d in defects]
    path = _verification_path(repo, record['task'], record['verification_id'])
    # R-1 Fix: Include 'standard' in identity to detect same verification_id with different standards
    identity = ('verification_id', 'target_run', 'verifier_run', 'target_head_sha',
                'verdict', 'evidence_level', 'trust_level', 'status', 'mapping_status',
                'criterion_evidence', 'findings', 'verified', 'standard',
                'target_run_sha256', 'verifier_run_sha256', 'goal_criteria_sha256',
                'goal_criteria_legacy_sha256', 'authority')
    resolved = []
    if verdict == 'pass':
        for defect_id in resolves_defects or []:
            defect, dpath = load_defect(repo, defect_id)
            if defect.get('task') != record['task']:
                raise PMError(f'缺陷 {defect_id} 不属于任务 {record["task"]}')
            if defect.get('status') not in ('fixed', 'verified'):
                raise PMError(f'缺陷 {defect_id} 还没有修复，不能标记 verified')
            fixed_sha = defect.get('fixed_in_sha')
            if fixed_sha and target_head and _is_ancestor(repo, fixed_sha, target_head) is False:
                raise PMError(f'缺陷 {defect_id} 的修复提交不在被验证提交历史中')
            resolved.append((defect, dpath))
    result = {'schema_version': '1.2', 'kind': 'verify_result',
              'status': record['status'], 'verified': verified,
              'verification': record, 'mapping': mapping,
              'defects': defects, 'path': relpath(repo, path), 'created': not path.is_file(),
              'would_update_run_status': ('verified' if verified else
                                          ('failed' if verdict == 'fail' else target.get('status'))),
              'caveat': ('本地 CLI 写出的验证记录没有受保护信任锚的分离签名，因此 status 最多是 '
                         'MANUAL_REVIEW_REQUIRED，verified 恒为 false。externally_verified 需要 --pr '
                         '并由 GitHub API 实际读取；CI 全绿只证明该提交的构建事实，不证明语义覆盖；'
                         'review 证据仍只是声明。测试收据只证明内容完整性，不证明来源；'
                         'PASS 仍要求每个必达标准都有绑定提交、独立复核 coverage 的证据映射。'),
              'dry_run': dry_run}
    if dry_run:
        if path.is_file():
            existing = _load(path)
            if _diff(existing, record, identity):
                raise PMError(f'验证记录已存在且内容不同：{path}')
            result.update({'verification': existing, 'created': False})
        return result
    if not _write(path, record):
        existing = _load(path)
        if _diff(existing, record, identity):
            raise PMError(f'验证记录已存在且内容不同：{path}')
        record = existing
    written_defects = []
    for defect, dpath in zip(defects, defect_paths):
        if _write(dpath, defect):
            written_defects.append(defect)
        else:
            existing = _load(dpath)
            if _diff(existing, defect, ('defect_id', 'summary', 'severity', 'location', 'target_run')):
                raise PMError(f'缺陷记录冲突：{dpath}')
            written_defects.append(existing)
    # R-2: resolving a defect is only allowed when the verification itself is
    # VERIFIED. A MANUAL_REVIEW_REQUIRED record may reference the fix, but it must
    # never upgrade the defect to verified.
    for defect, dpath in (resolved if verified else []):
        _mutate(dpath, lambda current: {**current, 'status': 'verified',
                                        'verified_by': record['verification_id'],
                                        'fixed_in_sha': current.get('fixed_in_sha') or target_head})
    if verified:
        _mutate(target_path, lambda current: {**current, 'status': 'verified',
                                              'git': {**current.get('git', {}), 'head_sha': target_head}})
    elif verdict == 'fail':
        _mutate(target_path, lambda current: {**current, 'status': 'failed'})
    _audit_attempt(repo, outcome='recorded', reason='verification_recorded',
                   verification_id=record['verification_id'],
                   target_run=target_run, verifier_run=verifier_run,
                   standard=standard, verdict=verdict,
                   evidence_level=evidence_level, trust_level=trust_level,
                   authority_status=record['authority_evaluation'].get('status'),
                   authority_trusted=record['authority_evaluation'].get('trusted'),
                   status=record['status'], mapping_status=mapping['status'],
                   verified=verified, stale=stale, worktree_dirty=worktree_dirty,
                   tracked_changes=tracked_status,
                   tracked_diff_sha256=tracked_diff_sha256, log_content_sha256=log_hash)
    result['defects'] = written_defects
    result['verification'] = record
    return result


def defect_list(repo: Path, task=None, status=None) -> dict:
    return {'schema_version': '1.2', 'kind': 'defect_list_result',
            'defects': iter_defects(repo, task=task, status=status)}


def defect_show(repo: Path, defect_id: str) -> dict:
    defect, path = load_defect(repo, defect_id)
    return {'schema_version': '1.2', 'kind': 'defect_show_result', 'defect': defect,
            'path': relpath(repo, path)}


def update_defect(repo: Path, defect_id: str, status: str, fixed_in_sha: str | None = None,
                  note: str = '', dry_run: bool = False) -> dict:
    defect, path = load_defect(repo, defect_id)
    if status not in DEFECT_STATUSES:
        raise PMError('defect status 必须是以下之一：' + '、'.join(sorted(DEFECT_STATUSES)))
    if status == 'verified':
        raise PMError('缺陷只能通过 pass 验证的 --resolves-defect 标为 verified，不能直接更新')
    if status != defect['status'] and status not in DEFECT_TRANSITIONS[defect['status']]:
        raise PMError(f'不允许的缺陷状态转换：{defect["status"]} -> {status}')
    if status == 'fixed':
        if not fixed_in_sha or not GIT_SHA.fullmatch(fixed_in_sha):
            raise PMError('标记 fixed 必须提供完整的 fixed_in_sha')
        if not _commit_exists(repo, fixed_in_sha):
            raise PMError(f'修复提交不存在：{fixed_in_sha}')
    def mutate(current):
        return {
            **current, 'status': status,
            'fixed_in_sha': fixed_in_sha or current.get('fixed_in_sha'),
            'history': list(current.get('history', [])) + [{'at': utc_now(), 'to': status, 'note': note}],
        }
    updated = mutate(copy.deepcopy(defect)) if dry_run else _mutate(path, mutate)
    return {'schema_version': '1.2', 'kind': 'defect_update_result', 'defect': updated,
            'dry_run': dry_run}


# ---------------------------------------------------------------- reconciliation

def _severity_counts(items):
    counts = {s: 0 for s in SEVERITIES}
    for item in items:
        counts[item['severity']] = counts.get(item['severity'], 0) + 1
    return counts


def reconcile(repo: Path, config: dict | None = None, format: str = 'json') -> dict:
    if format not in ('json', 'markdown'):
        raise PMError('reconcile format 必须是 json 或 markdown')
    cfg = config or load_config(repo)
    goals = iter_goals(repo)
    runs = iter_runs(repo)
    verifications = iter_verifications(repo)
    defects = iter_defects(repo)
    items = []

    def add(severity, code, message, refs=None, action=''):
        items.append({'severity': severity, 'code': code, 'message': message,
                      'refs': refs or [], 'action': action})

    run_by_id = {r.get('run_id'): r for r in runs}
    goal_by_id = {g.get('id'): g for g in goals}
    verification_by_id = {v.get('verification_id'): v for v in verifications}

    for goal in goals:
        gid = goal.get('id')
        evaluation = evaluate_goal(repo, gid)
        linked_runs = [r for r in runs if r.get('goal_id') == gid]
        linked_verifications = [v for v in verifications if v.get('goal_id') == gid]
        linked_defects = [d for d in defects if d.get('goal_id') == gid]
        if goal.get('status') == 'achieved' and not evaluation['satisfied']:
            add('high', 'achieved_goal_unsatisfied', f'Goal {gid} 已标记 achieved，但成功标准未满足',
                [gid, *evaluation['blocking']], '重新评估或降级 Goal 状态')
        if goal.get('status') == 'achieved' and evaluation.get('status_trusted') is False:
            add('high', 'achieved_goal_untrusted',
                f'Goal {gid} 已标记 achieved，但没有可验证的审计链/签名 checkpoint',
                [gid, *evaluation.get('status_problems', [])],
                '由 anchor 签署 audit checkpoint；在此之前按 achieved_unverified 处理')
        if (evaluation['evaluation_status'] in ('needs_review', 'partial', 'insufficient_evidence')
                and goal.get('status') in ('active', 'evaluating')):
            add('medium', 'goal_evidence_needs_review',
                f'Goal {gid} 的证据状态是 {evaluation["evaluation_status"]}',
                [gid, *evaluation['blocking']],
                '为每个必达标准补充带 criterion 映射和独立 coverage 复核的验证证据')
        if goal.get('status') in ('approved', 'active') and not linked_runs:
            add('medium', 'goal_without_runs', f'Goal {gid} 没有关联执行记录', [gid],
                '拆分任务并 run start，或说明为何尚未开始')
        if linked_defects:
            open_high = [d for d in linked_defects if d.get('status') in ('open', 'fixed') and d.get('severity') == 'high']
            if open_high:
                add('high', 'goal_open_high_defects',
                    f'Goal {gid} 有 {len(open_high)} 个未关闭 high 缺陷',
                    [d['defect_id'] for d in open_high], '修复并重新独立验证')
        if linked_verifications:
            latest = linked_verifications[-1]
            if latest.get('verdict') == 'pass' and not _record_verified(repo, latest):
                add('high', 'goal_pass_not_verified',
                    f'Goal {gid} 的验证结论是 pass，但没有可信授权来源', [latest['verification_id']],
                    '由受保护信任锚签名，或降级为人工复核')

    for run in runs:
        rid = run.get('run_id')
        if run.get('goal_id') not in goal_by_id:
            add('medium', 'run_orphan_goal', f'执行 {rid} 关联的 Goal 不存在：{run.get("goal_id")}',
                [rid], '修正关联或创建 Goal')
        is_verifier = run.get('role', 'executor') == 'verifier'
        if run.get('status') == 'submitted' and not is_verifier:
            passed = [v for v in verifications
                      if v.get('target_run') == rid and _record_verified(repo, v)]
            if not passed:
                add('medium', 'unverified_submission', f'执行 {rid} 已提交但没有通过的独立验证', [rid],
                    '运行 verify 并绑定当前 head SHA')
        if run.get('status') == 'verified' and not is_verifier:
            passed = [v for v in verifications
                      if v.get('target_run') == rid and _record_verified(repo, v)]
            if not passed:
                add('high', 'verified_without_record', f'执行 {rid} 标记 verified，但没有可信验证记录', [rid],
                    '补签名验证记录或回退执行状态')
        handoff_path = _handoff_path(repo, run.get('task'), rid)
        if run.get('status') in ('submitted', 'verified', 'failed') and not handoff_path.is_file():
            add('medium', 'run_missing_handoff', f'执行 {rid} 已结束但没有 handoff', [rid],
                '补写交接记录')
        base = (run.get('git') or {}).get('base_sha')
        current = git_sha_optional(repo)
        if base and current and _is_ancestor(repo, base, current) is False:
            add('medium', 'run_base_not_ancestor', f'执行 {rid} 的基准不在当前 HEAD 历史中', [rid],
                '人工对齐分支后重新开始或记录原因')

    active_by_task = {}
    for run in runs:
        if run.get('role', 'executor') == 'verifier':
            continue
        if run.get('status') in ACTIVE_RUN_STATUSES:
            active_by_task.setdefault(str(run.get('task')), []).append(run['run_id'])
    for task, ids in active_by_task.items():
        if len(ids) > 1:
            add('medium', 'multiple_active_runs', f'任务 {task} 有多个活跃执行：' + '、'.join(ids), ids,
                '人工指定唯一接手者；本地 CLI 不提供分布式锁')

    current_head = git_sha_optional(repo)
    for verification in verifications:
        vid = verification.get('verification_id')
        target = run_by_id.get(verification.get('target_run'))
        if target is None:
            add('high', 'verification_orphan_run', f'验证 {vid} 指向不存在的执行', [vid],
                '修复或归档验证记录')
            continue
        target_head = (target.get('git') or {}).get('head_sha')
        if verification.get('target_head_sha') != target_head:
            add('high', 'verification_stale_head', f'验证 {vid} 绑定的提交与执行 head 不一致', [vid],
                '对最新提交重新验证')
        elif current_head and target_head and current_head != target_head and (
                _record_verified(repo, verification) or verification.get('verdict') == 'pass'):
            # A failed verification of an older commit is historical evidence, not current knowledge.
            add('medium', 'verification_behind_head', f'验证 {vid} 针对旧提交 {target_head[:8]}',
                [vid, target['run_id']], '代码变化后重新验证')
        if verification.get('verified') and not _record_verified(repo, verification):
            authority = verification_authority(repo, verification)
            add('high', 'claimed_verified_untrusted',
                f'验证 {vid} 自称 verified，但没有可信授权来源（{authority.get("status")}）',
                [vid], '由受保护信任锚签名，或把 verified 设为 false')
        if verification.get('verdict') == 'pass' and verification.get('evidence_level') == 'agent_claimed':
            add('high', 'pass_from_agent_claim', f'验证 {vid} 把 Agent 自报当成 pass', [vid],
                '改为 fail/inconclusive，补充独立证据')
        if verification.get('verdict') == 'pass':
            if not verification.get('criterion_evidence'):
                add('medium', 'pass_without_criterion_mapping',
                    f'验证 {vid} 是 pass，但没有 criterion evidence mapping', [vid],
                    '对每个必达标准记录 evidence id、提交、日志和独立 coverage 复核')
            elif verification.get('mapping_status') != 'complete':
                add('high', 'pass_with_partial_coverage',
                    f'验证 {vid} 是 pass，但 criterion 覆盖不完整', [vid],
                    '补齐未覆盖标准，或把结论降级为 partial/inconclusive')
            for entry in verification.get('criterion_evidence') or []:
                if entry.get('description_match') is False:
                    add('medium', 'criterion_description_mismatch',
                        f'验证 {vid} 的证据描述与标准 {entry.get("criterion_id")} 不一致',
                        [vid, entry.get('criterion_id')], '重新核对标准与测试覆盖范围')
        if verification.get('verdict') == 'pass' and not _record_verified(repo, verification):
            add('medium', 'unverified_pass', f'验证 {vid} 结论为 pass 但可信级别不足', [vid],
                '补充证据或降级结论')

    evidence_goals = {}
    for verification in verifications:
        for entry in verification.get('criterion_evidence') or []:
            evidence_id = entry.get('evidence_id')
            if evidence_id:
                evidence_goals.setdefault(evidence_id, set()).add(verification.get('goal_id'))
    for evidence_id, goal_ids in evidence_goals.items():
        if len(goal_ids) > 1:
            add('high', 'criterion_evidence_reused',
                f'证据 {evidence_id} 被多个 Goal 复用：' + '、'.join(sorted(goal_ids)),
                [evidence_id, *sorted(goal_ids)],
                '为每个 Goal 使用独立证据，并重新核对覆盖范围')

    for defect in defects:
        if defect.get('status') in ('open', 'fixed') and defect.get('severity') == 'high':
            add('high', 'open_high_defect', f'未关闭的 high 缺陷 {defect["defect_id"]}',
                [defect['defect_id']], '修复并通过独立验证')
        if defect.get('status') == 'verified':
            vid = defect.get('verified_by')
            record = verification_by_id.get(vid) if vid else None
            covers_fix = (record is not None and defect.get('fixed_in_sha')
                          and record.get('target_head_sha') == defect.get('fixed_in_sha'))
            valid = (record is not None and _record_verified(repo, record)
                     and record.get('verdict') == 'pass'
                     and record.get('task') == defect.get('task')
                     and (record.get('target_run') == defect.get('target_run') or covers_fix))
            if not valid:
                add('high', 'defect_verified_without_record',
                    f'缺陷 {defect["defect_id"]} 标记 verified，但没有有效的通过验证记录',
                    [defect['defect_id'], vid or 'missing'], '回退缺陷状态或补充 --resolves-defect 验证')
        fixed_sha = defect.get('fixed_in_sha')
        if fixed_sha and current_head and _is_ancestor(repo, fixed_sha, current_head) is False:
            add('medium', 'defect_fix_not_ancestor', f'缺陷 {defect["defect_id"]} 的修复提交不在当前历史中',
                [defect['defect_id']], '确认修复分支是否已合并')

    report = audit(repo, cfg, allow_empty=True, scope='current')
    for finding in report['findings']:
        severity = finding['severity']
        add(severity, 'docs_' + finding['code'], f'文档审计：{finding["message"]}',
            [finding['location']], '按知识审计建议处理；不要为清零改写历史')

    adr_dir = cfg['adr_dir']
    adr_ids = set()
    for path in iter_docs(repo, [adr_dir]):
        if path.name == 'README.md':
            continue
        try:
            meta, _ = load_doc(path)
        except PMError:
            continue
        ident = str(meta.get('id') or '')
        if meta.get('status') == 'accepted' and ident:
            adr_ids.add(ident)
    linked_adrs = {adr for goal in goals for adr in goal.get('adrs', [])}
    for adr in sorted(adr_ids - linked_adrs):
        add('low', 'accepted_adr_unlinked', f'accepted ADR {adr} 没有关联 Goal',
            [adr], '人工确认实施状态，或在 Goal 中建立关联')

    items.sort(key=lambda x: (SEVERITIES.index(x['severity']), x['code'], x['message']))
    counts = _severity_counts(items)
    state = 'clean' if counts['high'] == 0 and counts['medium'] == 0 else 'needs_attention'
    result = {
        'schema_version': '1.2', 'kind': 'knowledge_reconciliation',
        'generated_at': utc_now(), 'repo': str(repo), 'state': state,
        'counts': counts, 'items': items,
        'summary': {
            'goals': len(goals), 'runs': len(runs), 'verifications': len(verifications),
            'defects': len(defects), 'open_defects': sum(1 for d in defects if d.get('status') in ('open', 'fixed')),
            'docs': report['counts'],
        },
        'goals': [{'id': g.get('id'), 'status': g.get('status'),
                   'satisfied': evaluate_goal(repo, g['id'])['satisfied']} for g in goals],
        'recommended_next_actions': [item['action'] for item in items if item['action']][:10],
        'caveat': '对账只检查结构化记录和文档审计结果；不判断语义是否正确，也不自动修改正式文档。',
    }
    if format == 'markdown':
        result['markdown'] = _reconcile_markdown(result)
    return result


def _reconcile_markdown(report: dict) -> str:
    lines = ['# 知识对账报告', '', f'- 生成时间：{report["generated_at"]}',
             f'- 状态：{report["state"]}',
             f'- 高/中/低：{report["counts"]["high"]}/{report["counts"]["medium"]}/{report["counts"]["low"]}',
             '', '## 当前项目知识状态', '']
    summary = report['summary']
    lines.append(f'- Goals：{summary["goals"]}；Runs：{summary["runs"]}；'
                 f'Verifications：{summary["verifications"]}；Defects：{summary["defects"]}（未关闭 {summary["open_defects"]}）')
    lines.append(f'- 文档审计：high {summary["docs"]["high"]}，medium {summary["docs"]["medium"]}，low {summary["docs"]["low"]}')
    lines += ['', '## 发现', '']
    if not report['items']:
        lines.append('没有发现结构化冲突。')
    for item in report['items']:
        refs = '，'.join(item['refs'])
        lines.append(f'- **{item["severity"]} · {item["code"]}**：{item["message"]}'
                     + (f'（{refs}）' if refs else ''))
        if item['action']:
            lines.append(f'  - 建议：{item["action"]}')
    lines += ['', '## 需要人工确认', '']
    manual = [i for i in report['items'] if i['severity'] in ('high', 'medium')]
    if manual:
        for item in manual:
            lines.append(f'- {item["message"]}')
    else:
        lines.append('无。')
    lines += ['', '## 下一步', '']
    for action in report['recommended_next_actions'] or ['保持当前状态，继续按 Goal 验收。']:
        lines.append(f'- {action}')
    lines += ['', '> 对账不自动覆盖正式文档；正式知识变更仍需 PR、CODEOWNERS 和人工审查。', '']
    return '\n'.join(lines)
