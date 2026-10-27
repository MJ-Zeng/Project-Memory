"""Project Memory CLI: non-destructive by default; GitHub adapter is read-only."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from .common import PMError, atomic_replace, ensure_utf8_stdio, json_text, require_repo, safe_json
from .bootstrap import init, sync_tooling
from .knowledge import create_adr, create_document, audit, load_config, load_reference_manifest
from .graph import build_graph, lexical_search, semantic_search
from .workflows import context, handoff, finish
from .execution import run_command
from .coordination import (create_goal, goal_list, goal_show, evaluate_goal, add_goal_evidence,
                           transition_goal, start_run, checkpoint_run, resume_run, finish_run,
                           run_show, iter_runs, verify_run, defect_list, defect_show,
                           update_defect, reconcile)
from .gh import GitHubReader


class _Parser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs['add_help'] = False
        super().__init__(*args, **kwargs)
        self._positionals.title = '位置参数'
        self._optionals.title = '选项'
        self.add_argument('-h', '--help', action='help', default=argparse.SUPPRESS, help='显示帮助并退出')

    def format_help(self):
        return super().format_help().replace('usage: ', '用法：', 1)

    def format_usage(self):
        return super().format_usage().replace('usage: ', '用法：', 1)

    def error(self, message):
        for english, chinese in (
            ('unrecognized arguments: ', '无法识别的参数：'),
            ('the following arguments are required: ', '缺少必需参数：'),
            ('invalid choice: ', '无效选项：'),
            ('invalid int value: ', '无效整数值：'),
            ('expected one argument', '需要一个参数'),
            ('expected 0 arguments', '不接受参数'),
            ('not allowed with argument', '不能与以下参数同时使用：'),
            ('ambiguous option: ', '参数有歧义：'),
        ):
            message = message.replace(english, chinese)
        self.print_usage(sys.stderr)
        self.exit(2, f'{self.prog}：错误：{message}\n')


def _add_roots(s):
    s.add_argument('--docs-root', action='append', help='规范文档根目录，相对仓库路径（可重复）')
    s.add_argument('--mirror-root', action='append', help='只读镜像根目录，用于检查与规范文档的分歧')
    s.add_argument('--legacy-root', action='append', help='标记为历史材料的根目录')
    s.add_argument('--frozen-root', action='append', help='冻结快照根目录；其中的候选不得当作当前知识')
    s.add_argument('--evidence-root', action='append', help='证据材料根目录；只作为证据，不作为当前知识')


def _leaf(sub, name, desc):
    """Nested command; --repo is only present when supplied after the leaf name."""
    s = sub.add_parser(name, help=desc)
    s.add_argument('--repo', default=argparse.SUPPRESS, type=Path, help='本地仓库或工作区路径')
    return s


def parser():
    p = _Parser(prog='project-memory', description='面向仓库、多 Agent 共用的项目记忆工具')
    sub = p.add_subparsers(dest='command', required=True)

    def base(name, desc):
        s = sub.add_parser(name, help=desc)
        s.add_argument('--repo', default='.', type=Path, help='本地仓库或工作区路径')
        return s

    s = base('init', '初始化，不覆盖已有文件')
    s.add_argument('--install', choices=['agents', 'claude', 'both', 'none'], default='agents', help='安装 Skill 的位置：agents、claude、both 或 none')
    s.add_argument('--docs-root', default='docs', help='规范文档根目录；已有 doc/ 或 doc/new_doc 时优先使用')
    s.add_argument('--mirror-root', action='append', help='写入配置的只读镜像根目录')
    s.add_argument('--legacy-root', action='append', help='写入配置的历史材料根目录')
    s.add_argument('--profile', choices=['full', 'overlay'], default='full', help='overlay 不生成 GitHub 文件，也不生成 INDEX、CURRENT_STATE 和架构模板')
    s = base('sync-tooling', '刷新仓库内 vendored 工具；默认只预览')
    s.add_argument('--write', action='store_true', help='实际写入；不删除 extra 文件，也不覆盖已安装的 Skill 副本')
    s = base('start', '生成任务上下文包')
    s.add_argument('--issue', type=int)
    s.add_argument('--issue-file', type=Path)
    s.add_argument('--task-file', type=Path, help='本地任务 JSON（含 id/title/body），不要求 GitHub Issue')
    s.add_argument('--slug', help='GitHub 仓库，格式 owner/repo')
    s.add_argument('--top-k', type=int, default=6)
    s.add_argument('--output', type=Path)
    _add_roots(s)
    s = base('handoff', '生成可重试、不覆盖的 Agent 交接记录')
    s.add_argument('--task', required=True, help='数字 Issue 编号或稳定的本地任务 ID')
    s.add_argument('--agent', required=True)
    s.add_argument('--run-id', required=True)
    s.add_argument('--base-sha')
    s.add_argument('--completed', action='append', default=[])
    s.add_argument('--remaining', action='append', default=[])
    s.add_argument('--blocker', action='append', default=[])
    s.add_argument('--evidence', action='append', default=[])
    s.add_argument('--store', type=Path, help='覆盖交接记录目录；用于保持被审计仓库只读')
    s = base('finish', '生成只读的完成门禁')
    s.add_argument('--issue', type=int)
    s.add_argument('--issue-file', type=Path)
    s.add_argument('--task-file', type=Path)
    s.add_argument('--slug')
    s.add_argument('--pr', type=int)
    s.add_argument('--pr-file', type=Path)
    s.add_argument('--test-evidence', help='自由文本证据指针；单独出现不会让门禁通过')
    s.add_argument('--test-command')
    s.add_argument('--test-exit', type=int)
    s.add_argument('--test-log')
    s.add_argument('--ci-url')
    s.add_argument('--ci-status')
    s.add_argument('--docs-impact', choices=['updated', 'not-applicable', 'unknown'], default='unknown')
    s.add_argument('--docs-justification', default='')
    s.add_argument('--reviewed-by', help='人工审查声明；单独出现不会让门禁通过')
    s.add_argument('--review-url')
    s.add_argument('--review-state')
    s.add_argument('--output', type=Path)
    _add_roots(s)
    s = base('decision', '生成 Proposed 状态的 ADR，不会批准')
    s.add_argument('--title', required=True)
    s.add_argument('--topic', required=True)
    s.add_argument('--issue', type=int, required=True)
    s.add_argument('--owner', required=True)
    s.add_argument('--options', default='')
    s.add_argument('--rationale', required=True)
    s.add_argument('--supersedes', default='')
    s = base('new-doc', '按固定格式生成文档骨架，不覆盖已有文件')
    s.add_argument('--id', required=True, help='稳定的文档 ID，例如 DOC-CACHE-001')
    s.add_argument('--title', required=True)
    s.add_argument('--kind', choices=['canonical', 'evidence'], required=True)
    s.add_argument('--status', choices=['draft', 'in_flight', 'evidence'], required=True)
    s.add_argument('--owner', required=True)
    s.add_argument('--path', required=True, help='位于配置的文档根目录之下的 .md 相对路径')
    s.add_argument('--issue', type=int)
    _add_roots(s)
    s = base('audit', '审计本地文档的元数据与一致性')
    s.add_argument('--fail-on', choices=['high', 'medium', 'low', 'none'], default='none')
    s.add_argument('--scope', choices=['all', 'current'], default='all', help='current 只审规范根目录中 current/draft/in-flight/未分类的文档和所有 ADR，不包含 mirror、legacy、evidence 和历史文档')
    s.add_argument('--allow-empty', action='store_true', help='没有规范文档时不报错')
    s.add_argument('--repo-manifest', type=Path, help='只读仓库清单 JSON；只含路径元数据，不读取文件内容')
    s.add_argument('--path-source', choices=['manifest', 'filesystem', 'shadow'], help='显式声明路径证据来源')
    s.add_argument('--output', type=Path)
    _add_roots(s)
    s = base('graph', '用本地文档和快照构建证据图')
    s.add_argument('--output', type=Path)
    _add_roots(s)
    s = base('search', '在知识图中检索，并标注来源与权威级别')
    s.add_argument('query')
    s.add_argument('--backend', choices=['lexical', 'semantic'], default='lexical')
    s.add_argument('--model', help='语义模式使用的本地 sentence-transformers 模型目录')
    s.add_argument('--top-k', type=int, default=6)
    s.add_argument('--include-archived', action='store_true', help='包含 legacy、历史和被替代的文档')
    s.add_argument('--include-mirror', action='store_true', help='包含镜像副本')
    _add_roots(s)

    s = base('goal', '目标记忆：成功标准、证据与状态转换')
    g = s.add_subparsers(dest='goal_command', required=True)
    c = _leaf(g, 'create', '创建 Goal；默认 proposed，不自动批准')
    c.add_argument('--id', required=True)
    c.add_argument('--title', required=True)
    c.add_argument('--background', default='')
    c.add_argument('--outcome', required=True)
    c.add_argument('--owner', required=True)
    c.add_argument('--criterion', action='append', default=[], help='必达成功标准，可重复')
    c.add_argument('--issue', action='append', type=int, default=[])
    c.add_argument('--adr', action='append', default=[])
    c.add_argument('--pr', action='append', type=int, default=[])
    c.add_argument('--constraint', action='append', default=[])
    c.add_argument('--status', choices=['proposed', 'approved', 'active'], default='proposed')
    c.add_argument('--approved-by')
    c.add_argument('--dry-run', action='store_true')
    c = _leaf(g, 'show', '查看 Goal、执行、验证和缺陷汇总')
    c.add_argument('--id', required=True)
    _leaf(g, 'list', '列出 Goal')
    c = _leaf(g, 'evaluate', '按成功标准检查证据，不依赖 Issue 是否关闭')
    c.add_argument('--id', required=True)
    c = _leaf(g, 'evidence', '为成功标准添加可核验证据')
    c.add_argument('--id', required=True)
    c.add_argument('--criterion', required=True)
    c.add_argument('--kind', required=True, choices=['verification', 'commit', 'test', 'manual'])
    c.add_argument('--ref', required=True)
    c.add_argument('--note', default='')
    c.add_argument('--approved-by')
    c.add_argument('--exit-code', type=int)
    c = _leaf(g, 'transition', '执行受控的 Goal 状态转换')
    c.add_argument('--id', required=True)
    c.add_argument('--to', required=True)
    c.add_argument('--approved-by')
    c.add_argument('--reason', default='')
    c.add_argument('--dry-run', action='store_true')

    s = base('run', 'Agent 执行记忆：启动、检查点、恢复、结束')
    g = s.add_subparsers(dest='run_command', required=True)
    c = _leaf(g, 'start', '登记一次可恢复的执行')
    c.add_argument('--goal', required=True)
    c.add_argument('--task', required=True)
    c.add_argument('--run-id', required=True)
    c.add_argument('--agent', required=True)
    c.add_argument('--model-provider', required=True)
    c.add_argument('--model-id', required=True)
    c.add_argument('--tool')
    c.add_argument('--session-id')
    c.add_argument('--branch')
    c.add_argument('--base-sha')
    c.add_argument('--authorization')
    c.add_argument('--role', choices=['executor', 'verifier'], default='executor')
    c.add_argument('--status', choices=['queued', 'running', 'paused'], default='running')
    c.add_argument('--dry-run', action='store_true')
    c = _leaf(g, 'checkpoint', '写入不可变检查点，便于中断恢复')
    c.add_argument('--task', required=True)
    c.add_argument('--run-id', required=True)
    c.add_argument('--completed', action='append', default=[])
    c.add_argument('--remaining', action='append', default=[])
    c.add_argument('--blocker', action='append', default=[])
    c.add_argument('--evidence', action='append', default=[])
    c.add_argument('--head-sha')
    c.add_argument('--note', default='')
    c = _leaf(g, 'finish', '结束执行并生成 1.2 交接记录')
    c.add_argument('--task', required=True)
    c.add_argument('--run-id', required=True)
    c.add_argument('--completed', action='append', default=[])
    c.add_argument('--remaining', action='append', default=[])
    c.add_argument('--blocker', action='append', default=[])
    c.add_argument('--evidence', action='append', default=[])
    c.add_argument('--head-sha')
    c.add_argument('--commit', action='append', default=[])
    c.add_argument('--changed-file', action='append', default=[])
    c.add_argument('--test-command')
    c.add_argument('--test-exit', type=int)
    c.add_argument('--test-log')
    c.add_argument('--tests-file', type=Path, help='JSON 数组，包含 command/exit_code/log')
    c.add_argument('--open-question', action='append', default=[])
    c.add_argument('--next-action', action='append', default=[])
    c.add_argument('--status', choices=['submitted', 'failed', 'cancelled'], default='submitted')
    c.add_argument('--dry-run', action='store_true')
    c = _leaf(g, 'resume', '生成接手包并检查基准、交接和冲突')
    c.add_argument('--task', required=True)
    c.add_argument('--run-id')
    c.add_argument('--goal')
    c = _leaf(g, 'show', '查看单次执行、检查点、交接和验证')
    c.add_argument('--task', required=True)
    c.add_argument('--run-id', required=True)
    c = _leaf(g, 'list', '列出执行记录')
    c.add_argument('--task')
    c.add_argument('--goal')

    s = base('verify', '独立验证记录；验证者不能是被验证的执行')
    s.add_argument('--target-run', required=True)
    s.add_argument('--verifier-run', required=True)
    s.add_argument('--standard', required=True)
    s.add_argument('--verdict', required=True, choices=['pass', 'fail', 'inconclusive'])
    s.add_argument('--evidence-level', required=True,
                   # R-1 Fix: Only locally_observed and agent_claimed are accepted.
                   # externally_verified and human_approved are blocked because the CLI
                   # cannot actually fetch CI/review URLs to verify them.
                   choices=['agent_claimed', 'locally_observed'])
    s.add_argument('--test-command')
    s.add_argument('--test-exit', type=int)
    s.add_argument('--test-log')
    s.add_argument('--ci-url')
    s.add_argument('--ci-status')
    s.add_argument('--review-url')
    s.add_argument('--review-state')
    s.add_argument('--findings-file', type=Path)
    s.add_argument('--verification-id')
    s.add_argument('--resolves-defect', action='append', default=[])
    s.add_argument('--expected-sha')
    s.add_argument('--criterion-evidence', type=Path,
                   help='JSON：每个必达标准到证据的映射（criterion evidence mapping）')
    s.add_argument('--test-receipt',
                   help='test-run 生成的执行收据；locally_observed 必须提供')
    s.add_argument('--dry-run', action='store_true')

    s = base('test-run', '在不可变提交快照中执行命令并生成执行收据')
    s.add_argument('--command', dest='exec_command', required=True,
                   help='在快照内执行的命令')
    s.add_argument('--commit', help='要快照的完整 SHA；默认 HEAD')
    s.add_argument('--agent', default='unknown-agent', help='执行者标识')
    s.add_argument('--timeout', type=int, default=900, help='超时秒数')
    s.add_argument('--output', type=Path)

    s = base('defect', '缺陷记录与修复状态')
    g = s.add_subparsers(dest='defect_command', required=True)
    c = _leaf(g, 'list', '列出缺陷')
    c.add_argument('--task')
    c.add_argument('--status', choices=['open', 'fixed', 'verified', 'wontfix', 'closed'])
    c = _leaf(g, 'show', '查看缺陷')
    c.add_argument('--id', required=True)
    c = _leaf(g, 'update', '更新缺陷状态；fixed 必须绑定提交 SHA，verified 只能由复验产生')
    c.add_argument('--id', required=True)
    c.add_argument('--status', required=True, choices=['open', 'fixed', 'wontfix', 'closed'])
    c.add_argument('--fixed-in-sha')
    c.add_argument('--note', default='')
    c.add_argument('--dry-run', action='store_true')

    s = base('reconcile', '对账 Goal、执行、验证、缺陷、ADR 与当前文档')
    s.add_argument('--format', choices=['json', 'markdown'], default='json')
    s.add_argument('--output', type=Path)
    s.add_argument('--fail-on', choices=['high', 'medium', 'low', 'none'], default='none')
    _add_roots(s)
    return p


def _config(args, repo):
    cfg = load_config(repo)
    if getattr(args, 'docs_root', None):
        cfg['doc_roots'] = args.docs_root
    if getattr(args, 'mirror_root', None):
        cfg['mirror_roots'] = args.mirror_root
    if getattr(args, 'legacy_root', None):
        cfg['legacy_roots'] = args.legacy_root
    if getattr(args, 'frozen_root', None):
        cfg['frozen_roots'] = args.frozen_root
    if getattr(args, 'evidence_root', None):
        cfg['evidence_roots'] = args.evidence_root
    return cfg


def load_task(args):
    if getattr(args, 'task_file', None):
        obj = safe_json(args.task_file)
        if not isinstance(obj, dict):
            raise PMError('任务文件必须是 JSON 对象')
        if getattr(args, 'issue', None) and obj.get('number') != args.issue:
            raise PMError('Issue 编号与 --task-file 中的 number 不一致')
        obj.setdefault('_provenance', 'local_task_file')
        return obj
    if getattr(args, 'issue_file', None):
        obj = safe_json(args.issue_file)
        if getattr(args, 'issue', None) and obj.get('number') != args.issue:
            raise PMError('Issue 编号与 --issue-file 中的 number 不一致')
        return obj
    if not getattr(args, 'issue', None) or not args.slug:
        raise PMError('请提供 --task-file、--issue-file，或同时提供 --issue 与 --slug')
    return GitHubReader(args.slug).issue(args.issue)


def load_pr(args):
    if args.pr_file:
        obj = safe_json(args.pr_file)
        if args.pr is not None and obj.get('number') != args.pr:
            raise PMError('PR 编号与 --pr-file 中的 number 不一致')
        return obj
    if args.pr:
        if not args.slug:
            raise PMError('使用 --pr 时必须同时提供 --slug 才能查询 GitHub')
        return GitHubReader(args.slug).pull(args.pr)
    return None


def emit(obj, output: Path | None = None):
    s = json_text(obj)
    if output:
        atomic_replace(output, s)
    print(s, end='')


def run(args):
    repo = require_repo(args.repo)
    if args.command == 'init':
        emit(init(repo, args.install, args.docs_root, args.profile, args.mirror_root, args.legacy_root))
    elif args.command == 'sync-tooling':
        emit(sync_tooling(repo, args.write))
    elif args.command == 'start':
        if args.top_k < 1 or args.top_k > 50:
            raise PMError('top-k 必须在 1 到 50 之间')
        emit(context(repo, load_task(args), args.top_k, _config(args, repo)), args.output)
    elif args.command == 'handoff':
        emit(handoff(repo, args.task, args.agent, args.run_id, args.completed, args.remaining, args.blocker, args.evidence, args.base_sha, args.store))
    elif args.command == 'finish':
        emit(finish(repo, load_task(args), load_pr(args), args.test_evidence, args.docs_impact,
                    args.docs_justification, args.reviewed_by, _config(args, repo),
                    test_command=args.test_command, test_exit=args.test_exit, test_log=args.test_log,
                    ci_url=args.ci_url, ci_status=args.ci_status,
                    review_url=args.review_url, review_state=args.review_state), args.output)
    elif args.command == 'decision':
        emit({'schema_version': '1.1', 'kind': 'adr_proposal', 'path': create_adr(repo, args.title, args.topic, args.issue, args.options, args.rationale, args.owner, args.supersedes), 'status': 'proposed', 'requires_human_approval': True})
    elif args.command == 'new-doc':
        emit(create_document(repo, args.id, args.title, args.kind, args.status, args.owner, args.path, args.issue, _config(args, repo)))
    elif args.command == 'audit':
        manifest = None
        if args.repo_manifest:
            manifest = load_reference_manifest(args.repo_manifest, repo)
            declared = manifest.get('source', 'manifest')
            if declared in ('manifest', 'metadata-only'):
                declared = 'manifest'
            if args.path_source and args.path_source != declared:
                raise PMError('--path-source 与清单声明的来源不一致')
        report = audit(repo, _config(args, repo), args.allow_empty, args.scope,
                       manifest=manifest, path_source=args.path_source)
        emit(report, args.output)
        levels = {'high': {'high'}, 'medium': {'medium', 'high'}, 'low': {'low', 'medium', 'high'}, 'none': set()}
        if any(x['severity'] in levels[args.fail_on] for x in report['findings']):
            return 2
    elif args.command == 'graph':
        output = args.output or (repo / '.project-memory/cache/graph.json')
        emit(build_graph(repo, _config(args, repo)), output)
    elif args.command == 'search':
        if args.top_k < 1 or args.top_k > 50:
            raise PMError('top-k 必须在 1 到 50 之间')
        g = build_graph(repo, _config(args, repo))
        if args.backend == 'semantic':
            if not args.model:
                raise PMError('--backend semantic 需要通过 --model 指定已存在的本地模型目录')
            results = semantic_search(g, args.query, args.model, args.top_k, args.include_archived, args.include_mirror)
        else:
            results = lexical_search(g, args.query, args.top_k, args.include_archived, args.include_mirror)
        emit({
            'schema_version': '1.1',
            'kind': 'search_results',
            'backend': args.backend,
            'query': args.query,
            'filters': {'include_archived': args.include_archived, 'include_mirror': args.include_mirror},
            'results': results,
            'caveat': '检索结果是参考材料，不是权威指令。authority/status 由配置、路径和 frontmatter 推断。',
        })
    elif args.command == 'goal':
        if args.goal_command == 'create':
            emit(create_goal(repo, args.id, args.title, args.background, args.outcome, args.owner,
                             args.criterion, args.issue, args.adr, args.pr, args.constraint,
                             args.status, args.approved_by, args.dry_run))
        elif args.goal_command == 'show':
            emit(goal_show(repo, args.id))
        elif args.goal_command == 'list':
            emit(goal_list(repo))
        elif args.goal_command == 'evaluate':
            result = evaluate_goal(repo, args.id)
            emit(result)
            return 0 if result['satisfied'] else 2
        elif args.goal_command == 'evidence':
            emit(add_goal_evidence(repo, args.id, args.criterion, args.kind, args.ref,
                                   args.note, args.approved_by, args.exit_code))
        elif args.goal_command == 'transition':
            emit(transition_goal(repo, args.id, args.to, args.approved_by, args.reason, args.dry_run))
    elif args.command == 'run':
        if args.run_command == 'start':
            emit(start_run(repo, args.goal, args.task, args.run_id, args.agent,
                           args.model_provider, args.model_id, args.tool,
                           args.session_id, args.branch, args.base_sha, args.authorization,
                           args.status, args.role, args.dry_run))
        elif args.run_command == 'checkpoint':
            emit(checkpoint_run(repo, args.task, args.run_id, args.completed, args.remaining,
                                args.blocker, args.evidence, args.head_sha, args.note))
        elif args.run_command == 'finish':
            tests = []
            if args.test_command or args.test_exit is not None or args.test_log:
                if not args.test_command or args.test_exit is None:
                    raise PMError('--test-command 与 --test-exit 必须同时提供')
                tests.append({'command': args.test_command, 'exit_code': args.test_exit,
                              'log': args.test_log or ''})
            if args.tests_file:
                extra = safe_json(args.tests_file)
                if not isinstance(extra, list):
                    raise PMError('--tests-file 必须是 JSON 数组')
                tests.extend(extra)
            emit(finish_run(repo, args.task, args.run_id, args.completed, args.remaining,
                            args.blocker, args.evidence, args.head_sha, args.commit,
                            args.changed_file, tests, args.open_question, args.next_action,
                            args.status, args.dry_run))
        elif args.run_command == 'resume':
            result = resume_run(repo, args.task, args.run_id, args.goal)
            emit(result)
            return 0 if result['status'] in ('resume_ready', 'verified', 'no_run') else 2
        elif args.run_command == 'show':
            emit(run_show(repo, args.task, args.run_id))
        elif args.run_command == 'list':
            emit({'schema_version': '1.2', 'kind': 'run_list_result',
                  'runs': iter_runs(repo, task=args.task, goal=args.goal)})
    elif args.command == 'verify':
        findings = safe_json(args.findings_file) if args.findings_file else []
        mapping = safe_json(args.criterion_evidence) if args.criterion_evidence else None
        result = verify_run(repo, args.target_run, args.verifier_run, args.standard,
                            args.verdict, args.evidence_level, args.test_command, args.test_exit,
                            args.test_log, args.ci_url, args.ci_status, args.review_url,
                            args.review_state, findings, args.verification_id,
                            args.resolves_defect, args.expected_sha, mapping,
                            test_receipt=args.test_receipt, dry_run=args.dry_run)
        emit(result)
        return 0 if result.get('verified') else 2
    elif args.command == 'test-run':
        emit(run_command(repo, args.exec_command, args.commit, executed_by=args.agent,
                         timeout=args.timeout), args.output)
        return 0
    elif args.command == 'defect':
        if args.defect_command == 'list':
            emit(defect_list(repo, args.task, args.status))
        elif args.defect_command == 'show':
            emit(defect_show(repo, args.id))
        elif args.defect_command == 'update':
            emit(update_defect(repo, args.id, args.status, args.fixed_in_sha, args.note, args.dry_run))
    elif args.command == 'reconcile':
        result = reconcile(repo, _config(args, repo), args.format)
        if args.format == 'markdown':
            text = result['markdown']
            if args.output:
                atomic_replace(args.output, text)
            else:
                print(text, end='' if text.endswith('\n') else '\n')
        else:
            emit(result, args.output)
        levels = {'high': {'high'}, 'medium': {'medium', 'high'},
                  'low': {'low', 'medium', 'high'}, 'none': set()}
        if any(x['severity'] in levels[args.fail_on] for x in result['items']):
            return 2
    return 0


def main(argv=None):
    ensure_utf8_stdio()
    args = parser().parse_args(argv)
    try:
        return run(args)
    except PMError as e:
        print(f'project-memory: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
