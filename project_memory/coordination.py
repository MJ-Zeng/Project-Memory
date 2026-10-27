"""Goal-driven coordination records: goals, agent runs, verification, defects, reconciliation."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path

from .common import PMError, atomic_replace, git_sha_optional, json_text, relpath, safe_json, utc_now, validate_identifier, write_new
from .knowledge import (audit, iter_docs, load_config, load_doc, log_problem,
                        valid_http_url)
from .workflows import handoff as write_handoff
from .workflows import task_id_of

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
COVERAGE_REVIEW_STATUSES = {'confirmed', 'unconfirmed', 'rejected', 'not_reviewed'}
MAPPING_STATUSES = {'complete', 'partial', 'missing', 'invalid'}
VERIFY_STATUSES = {'VERIFIED', 'INSUFFICIENT_EVIDENCE', 'PARTIAL_COVERAGE',
                   'BLOCKED_BY_DEFECT', 'FAILED', 'INCONCLUSIVE'}
SEVERITIES = ('high', 'medium', 'low')
ACTIVE_RUN_STATUSES = {'queued', 'running', 'paused'}
RUN_ROLES = {'executor', 'verifier'}
GIT_SHA = re.compile(r'[0-9a-f]{40}')
APPROVAL_REF = re.compile(r'(?:https?://\S+|#\d+|(?:PR|pr|Issue|issue|Review|review)\s*#?\d+|[0-9a-f]{40})')
# R-1 Fix: Patterns that indicate agent self-approval, not human identity
AGENT_SELF_PATTERNS = {'agent-self', 'agent', 'auto', 'system', 'self', 'bot', 'ai', 'automated'}
# R-1 Fix: approved_by must look like a verifiable human identity (email or known reviewer)
HUMAN_IDENTITY_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


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


def _audit_attempt(repo: Path, **fields) -> None:
    """T-05: persist every verification attempt, including rejected ones."""
    entry = {'schema_version': '1.2', 'kind': 'verification_attempt',
             'timestamp': utc_now(), **fields}
    audit_dir = _root(repo, 'audit')
    audit_dir.mkdir(parents=True, exist_ok=True)
    with open(audit_dir / 'verification_attempts.jsonl', 'a', encoding='utf-8') as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + '\n')


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


def _repo_aliases(repo: Path) -> set[str]:
    resolved = repo.resolve()
    values = {repo.name, resolved.name, resolved.as_posix(), str(resolved)}
    return {str(value).replace('\\', '/').rstrip('/').casefold()
            for value in values if value}


def _repo_matches(repo: Path, declared: str) -> bool:
    value = str(declared or '').replace('\\', '/').rstrip('/').casefold()
    return bool(value) and value in _repo_aliases(repo)


def _criterion_evidence_entries(value, repo: Path, goal: dict, target: dict,
                                verifier: dict, target_head: str | None) -> list[dict]:
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
        if local:
            if not isinstance(exit_code, int):
                raise PMError('本地执行证据必须提供整数 evidence_exit_code')
            problem = _log_problem(repo, log)
            if problem:
                raise PMError(f'evidence_log 无效：{problem}')
            if status == 'passed' and exit_code != 0:
                raise PMError('execution_status=passed 与 evidence_exit_code 非 0 矛盾')
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
        if source in ('test', 'check', 'command'):
            observed = 'locally_observed' if status == 'passed' and exit_code == 0 else 'agent_claimed'
        elif source == 'ci':
            # R-1 Fix: declared_unfetched CI cannot get externally_verified trust
            # Only locally_observed at most, since we don't actually fetch the URL
            observed = 'agent_claimed'
        elif source == 'review':
            # R-1 Fix: declared_unfetched review cannot get human_approved trust
            observed = 'agent_claimed'
        else:
            observed = 'agent_claimed'
        coverage_confirmed = (review_status == 'confirmed'
                              and independent == verifier.get('agent')
                              and description_match)
        evidence_matched = (observed != 'agent_claimed' and coverage_confirmed
                            and status == 'passed' and result == 'pass')
        problems = []
        if not description_match:
            problems.append('criterion_description 与 Goal 标准不一致')
        if review_status != 'confirmed':
            problems.append('coverage_review_status 不是 confirmed')
        if status != 'passed':
            problems.append('execution_status 不是 passed')
        if result != 'pass':
            problems.append('verification_result 不是 pass')
        if observed == 'agent_claimed':
            problems.append('没有可观察的执行证据')
        if coverage_confirmed:
            state = 'evidence_matched'
        elif observed == 'externally_verified':
            state = 'externally_verified'
        elif observed == 'human_approved':
            state = 'human_approved'
        elif observed == 'locally_observed':
            state = 'executed'
        else:
            state = 'agent_claimed'
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
            'execution_status': status,
            'coverage_claim': coverage_claim,
            'coverage_review_status': review_status,
            'independent_verifier': independent,
            'verification_result': result,
            'description_match': description_match,
            'observed_level': observed,
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
    covered, partial, problems = [], [], []
    for cid in required:
        items = by_criterion.get(cid, [])
        if items and all(entry['evidence_matched'] for entry in items):
            covered.append(cid)
        elif items:
            partial.append(cid)
            for entry in items:
                problems.extend(f'{cid}: {problem}' for problem in entry['problems'])
    missing = [cid for cid in required if cid not in by_criterion]
    unexpected = sorted(cid for cid in by_criterion if cid not in required)
    if not entries:
        status = 'missing'
    elif missing or partial or unexpected:
        status = 'partial'
    else:
        status = 'complete'
    return {'status': status, 'required': required, 'covered': covered,
            'partial': partial, 'missing': missing, 'unexpected': unexpected,
            'problems': problems}


def _mapping_outcome(entries: list[dict], mapping: dict) -> str:
    if not entries:
        return 'INSUFFICIENT_EVIDENCE'
    if mapping['missing'] or mapping['unexpected']:
        return 'PARTIAL_COVERAGE'
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
    # T-04 (fixed): compare tracked-file state against the state recorded at
    # verification time. Untracked files (including .project-memory receipts and
    # test logs) are excluded, so recording a log no longer makes every attempt
    # look dirty; a later edit to tracked code does invalidate the record.
    checks = verification.get('checks', {})
    tests_info = checks.get('tests', {})
    recorded_status = tests_info.get('tracked_changes_at_verification')
    code, out = _git(repo, 'status', '--porcelain', '--untracked-files=no')
    current_status = out.strip()
    if recorded_status is not None and current_status != recorded_status:
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
    return run.get('status') == 'verified'


def _verification_ok(repo: Path, evidence: dict, goal_id: str,
                     criterion_id: str = '') -> tuple[bool, str, str]:
    ref = str(evidence.get('ref') or '').strip()
    if not ref:
        return False, '缺少 verification 引用', 'invalid'
    path = _find_record(repo, 'verifications', ref)
    if path is None:
        return False, f'找不到验证记录 {ref}', 'invalid'
    verification = _load(path)
    if verification.get('goal_id') != goal_id:
        return False, f'{ref} 属于其他目标：{verification.get("goal_id")}', 'invalid'
    if verification.get('verdict') != 'pass' or not verification.get('verified'):
        return False, f'{ref} 不是已通过的验证', 'invalid'
    if not criterion_id:
        return False, f'{ref} 缺少 criterion id，无法确认覆盖', 'unconfirmed'
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
        # R-1 Fix: manual evidence is structurally valid but cannot auto-satisfy;
        # it requires a verification record with criterion mapping to prove coverage
        return (True, f'人工批准（{approved_by}）需要配合 verification 记录与 criterion mapping；'
                      f'manual 证据本身不能单独证明标准达成',
                'human_approved', False, 'human_review_required')
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
            # R-1 Fix: human_review_required state means manual evidence exists but needs
            # verification record with criterion mapping to prove standard coverage
            if valid and state in ('executed_not_matched', 'evidence_matched',
                                   'human_review_required', 'human_approved', 'externally_verified'):
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
    required_satisfied = all(c['status'] == 'satisfied' for c in required)
    if open_high:
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
    return {
        'schema_version': '1.2', 'kind': 'goal_evaluation', 'goal_id': goal_id,
        'goal_status': goal['status'], 'satisfied': satisfied,
        'evaluation_status': state, 'criteria': criteria_out,
        'blocking': blocking, 'partial': partial,
        'open_high_defects': [d['defect_id'] for d in open_high],
        'recommendation': recommendation,
        'caveat': ('只接受带 criterion evidence mapping 且 coverage 经独立复核的证据；'
                   '直接 test/commit 证据和旧验证记录可读，但不能单独证明标准已达成。'
                   'CLI 不能判断语义相关性，仍需人工审查。'),
    }


def add_goal_evidence(repo: Path, goal_id: str, criterion_id: str, kind: str, ref: str,
                      note: str = '', approved_by: str | None = None, exit_code: int | None = None) -> dict:
    goal = load_goal(repo, goal_id)
    evidence = {'kind': kind, 'ref': ref.strip(), 'note': note.strip()}
    if approved_by:
        evidence['approved_by'] = approved_by
    if exit_code is not None:
        evidence['exit_code'] = exit_code
    valid, reason, _, _, _ = _evidence_result(repo, evidence, goal_id, criterion_id)
    if not valid:
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
            raise PMError(f'Goal 的成功标准尚未满足（{evaluation["evaluation_status"]}）：{detail}；'
                          '不能仅凭 Issue 关闭或 Agent 声明标记 achieved')

    def mutate(goal):
        goal['status'] = target
        if approved_by:
            goal['approved_by'] = approved_by
            goal.setdefault('approvals', []).append({'at': utc_now(), 'by': approved_by,
                                                     'from': source, 'to': target, 'reason': reason})
        goal.setdefault('history', []).append({'at': utc_now(), 'from': source, 'to': target,
                                               'by': approved_by or goal.get('owner'), 'reason': reason})
        return goal
    updated = mutate(copy.deepcopy(current)) if dry_run else _mutate(_goal_path(repo, goal_id), mutate)
    return {'schema_version': '1.2', 'kind': 'goal_transition_result', 'goal': updated,
            'changed': True, 'evaluation': evaluation, 'dry_run': dry_run}


def goal_show(repo: Path, goal_id: str) -> dict:
    goal = load_goal(repo, goal_id)
    runs = [r for r in iter_runs(repo) if r.get('goal_id') == goal_id]
    verifications = [v for v in iter_verifications(repo) if v.get('goal_id') == goal_id]
    defects = [d for d in iter_defects(repo) if d.get('goal_id') == goal_id]
    run_counts = {}
    for run in runs:
        run_counts[run['status']] = run_counts.get(run['status'], 0) + 1
    open_defects = [d for d in defects if d.get('status') in ('open', 'fixed')]
    return {
        'schema_version': '1.2', 'kind': 'goal_show_result', 'goal': goal,
        'progress': {
            'runs': run_counts,
            'tasks': sorted({str(r.get('task')) for r in runs}),
            'verifications': len(verifications),
            'verified_verifications': sum(1 for v in verifications if v.get('verified')),
            'defects': len(defects),
            'open_defects': len(open_defects),
        },
        'evaluation': evaluate_goal(repo, goal_id),
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
    current_verifications = [v for v in verifications if _verification_current(repo, v)]
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
                         review_url, review_state, evidence_level, verdict):
    if verdict not in ('pass', 'fail', 'inconclusive'):
        raise PMError('verdict 必须是 pass、fail 或 inconclusive')
    if evidence_level not in EVIDENCE_LEVELS:
        raise PMError('evidence level 必须是以下之一：' + '、'.join(sorted(EVIDENCE_LEVELS)))
    if verdict == 'pass' and evidence_level == 'agent_claimed':
        raise PMError('Agent 自报不能作为 pass；请提供本地日志、外部 CI 或人工批准')
    # R-1 Fix: Block externally-declared trust levels that cannot be verified
    if evidence_level == 'externally_verified':
        raise PMError('externally_verified 不能作为声明的 evidence level；'
                      'CI 证据在 criterion mapping 中只获得 agent_claimed 信任')
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
        if not test_command or not isinstance(test_exit, int) or not test_log:
            raise PMError('locally_observed 需要 test command、整数 test exit 和 test log')
    if ci_url and not _valid_http_url(ci_url):
        raise PMError('CI URL 必须是 http(s) 地址')
    if review_url and not _valid_http_url(review_url):
        raise PMError('review URL 必须是 http(s) 地址')
    if verdict == 'pass' and evidence_level == 'locally_observed' and test_exit != 0:
        raise PMError('测试没有通过，不能给出 pass')
    return log_path


def verify_run(repo: Path, target_run: str, verifier_run: str, standard: str,
               verdict: str, evidence_level: str, test_command: str | None = None,
               test_exit: int | None = None, test_log: str | None = None,
               ci_url: str | None = None, ci_status: str | None = None,
               review_url: str | None = None, review_state: str | None = None,
               findings=None, verification_id: str | None = None,
               resolves_defects=None, expected_sha: str | None = None,
               criterion_evidence=None, dry_run: bool = False) -> dict:
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
    standard = _single_line(standard, 'verification standard')
    _verification_inputs(test_command, test_exit, test_log, ci_url, ci_status,
                         review_url, review_state, evidence_level, verdict)
    target_head = (target.get('git') or {}).get('head_sha')
    current_head = git_sha_optional(repo)
    if expected_sha and expected_sha != target_head:
        raise PMError(f'expected SHA {expected_sha} 与被验证执行 head {target_head} 不一致')
    if target_head and not GIT_SHA.fullmatch(target_head):
        raise PMError('被验证执行的 head_sha 不是完整 SHA')
    if target_head and not _commit_exists(repo, target_head):
        raise PMError(f'被验证提交不存在：{target_head}')
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
    criterion_entries, mapping = [], {'status': 'missing', 'required': [],
                                      'covered': [], 'partial': [], 'missing': [],
                                      'unexpected': [], 'problems': []}
    if verdict == 'pass':
        if not target_head:
            raise PMError('PASS 需要被验证执行绑定完整 head SHA')
        goal = load_goal(repo, target.get('goal_id'))
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
        criterion_entries = _criterion_evidence_entries(
            criterion_evidence, repo, goal, target, verifier, target_head)
        mapping = _mapping_summary(criterion_entries, goal)
        if mapping['status'] != 'complete':
            status = _mapping_outcome(criterion_entries, mapping)
            _audit_attempt(repo, outcome='rejected', reason='incomplete_mapping',
                           target_run=target_run, verifier_run=verifier_run,
                           standard=standard, verdict=verdict,
                           evidence_level=evidence_level, mapping_status=status,
                           verified=False, worktree_dirty=worktree_dirty,
                           tracked_changes=tracked_status, log_content_sha256=log_hash)
            return {'schema_version': '1.2', 'kind': 'verify_result',
                    'status': status, 'verified': False, 'verification': None,
                    'reason': ('PASS 需要覆盖全部必达标准的 criterion evidence mapping；'
                               '只有日志和退出码不足以证明覆盖'
                               if not criterion_entries else
                               'criterion evidence 未满足完整、已确认的覆盖要求'),
                    'mapping': mapping, 'criterion_evidence': criterion_entries,
                    'dry_run': dry_run}
    tests = {'command': test_command or '', 'exit_code': test_exit,
             'log': test_log or '', 'log_exists': bool(_log_problem(repo, test_log) is None),
             'log_content_sha256': log_hash,
             'worktree_dirty_at_verification': worktree_dirty,
             'tracked_changes_at_verification': tracked_status}
    ci = {'url': ci_url or '', 'status': ci_status or 'not_provided',
          'provenance': 'declared_unfetched' if ci_url else 'none'}
    review = {'url': review_url or '', 'state': review_state or 'not_provided',
              'provenance': 'declared_unfetched' if review_url else 'none'}
    observed_rank = max([EVIDENCE_TRUST.get(entry['observed_level'], 0)
                         for entry in criterion_entries] or [0])
    if verdict != 'pass':
        observed_rank = EVIDENCE_TRUST[evidence_level]
    trust_rank = min(EVIDENCE_TRUST[evidence_level], observed_rank)
    trust_level = next(level for level, rank in EVIDENCE_TRUST.items() if rank == trust_rank)
    # R-1 Fix: verified requires locally_observed evidence AND complete criterion mapping
    # with all entries having evidence_matched=True (coverage confirmed by independent verifier)
    all_criteria_matched = (verdict == 'pass' and criterion_entries
                           and all(entry.get('evidence_matched') for entry in criterion_entries))
    verified = (verdict == 'pass' and evidence_level == 'locally_observed'
                and not stale and mapping['status'] == 'complete'
                and all_criteria_matched
                and not any(f['severity'] == 'high' for f in finding_list))
    _check_run_transition(target, 'verified' if verified else ('failed' if verdict == 'fail' else target.get('status')))
    record = {
        'schema_version': '1.2', 'kind': 'verification_record',
        'verification_id': verification_id or _now_id('VER', target_run, target_head, verifier_run,
                                                       verdict, standard, json.dumps(finding_list, sort_keys=True)),
        'task': target.get('task'), 'goal_id': target.get('goal_id'),
        'target_run': target_run, 'verifier_run': verifier_run,
        'verifier': {'agent': verifier.get('agent'), 'model': verifier.get('model'),
                     'tool': verifier.get('tool'), 'session_id': verifier.get('session_id')},
        'independence': independence,
        'target_head_sha': target_head, 'current_head_sha': current_head, 'stale': stale,
        'standard': standard, 'verdict': verdict, 'evidence_level': evidence_level,
        'trust_level': trust_level,
        'status': ('VERIFIED' if verified else ('FAILED' if verdict == 'fail' else 'INCONCLUSIVE')),
        'mapping_status': mapping['status'],
        'criterion_evidence': criterion_entries,
        'covered_criteria': mapping.get('covered', []),
        'missing_criteria': mapping.get('missing', []),
        'verified': verified, 'checks': {'tests': tests, 'ci': ci, 'review': review},
        'findings': [], 'created_at': utc_now(), 'revision': 1,
    }
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
                'criterion_evidence', 'findings', 'verified', 'standard')
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
              'caveat': ('R-1 整改：CLI 不再接受 externally_verified 或 human_approved 作为声明的 '
                         'evidence level。CI/review 证据在 criterion mapping 中只获得 agent_claimed '
                         '信任。人工批准（manual 证据）必须配合 verification 记录与 criterion mapping '
                         '才能证明标准达成。测试日志必须在仓库内。PASS 要求每个必达标准都有绑定提交、'
                         '独立复核 coverage 的证据映射，且所有映射的 evidence_matched 为 true。'),
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
    for defect, dpath in resolved:
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
                   status=record['status'], mapping_status=mapping['status'],
                   verified=verified, stale=stale, worktree_dirty=worktree_dirty,
                   tracked_changes=tracked_status, log_content_sha256=log_hash)
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
            if latest.get('verdict') == 'pass' and not latest.get('verified'):
                add('high', 'goal_pass_not_verified',
                    f'Goal {gid} 的验证结论是 pass，但证据级别不足', [latest['verification_id']],
                    '补充本地执行证据、外部 CI 或人工批准')

    for run in runs:
        rid = run.get('run_id')
        if run.get('goal_id') not in goal_by_id:
            add('medium', 'run_orphan_goal', f'执行 {rid} 关联的 Goal 不存在：{run.get("goal_id")}',
                [rid], '修正关联或创建 Goal')
        is_verifier = run.get('role', 'executor') == 'verifier'
        if run.get('status') == 'submitted' and not is_verifier:
            passed = [v for v in verifications if v.get('target_run') == rid and v.get('verified')]
            if not passed:
                add('medium', 'unverified_submission', f'执行 {rid} 已提交但没有通过的独立验证', [rid],
                    '运行 verify 并绑定当前 head SHA')
        if run.get('status') == 'verified' and not is_verifier:
            passed = [v for v in verifications if v.get('target_run') == rid and v.get('verified')]
            if not passed:
                add('high', 'verified_without_record', f'执行 {rid} 标记 verified，但没有验证记录', [rid],
                    '补验证记录或回退执行状态')
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
                verification.get('verified') or verification.get('verdict') == 'pass'):
            # A failed verification of an older commit is historical evidence, not current knowledge.
            add('medium', 'verification_behind_head', f'验证 {vid} 针对旧提交 {target_head[:8]}',
                [vid, target['run_id']], '代码变化后重新验证')
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
        if verification.get('verdict') == 'pass' and not verification.get('verified'):
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
            valid = (record is not None and record.get('verified')
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
