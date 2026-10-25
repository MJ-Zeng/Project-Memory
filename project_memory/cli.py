"""Project Memory CLI: non-destructive by default; GitHub adapter is read-only."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from .common import PMError, atomic_replace, ensure_utf8_stdio, json_text, require_repo, safe_json
from .bootstrap import init
from .knowledge import create_adr, create_document, audit, load_config
from .graph import build_graph, lexical_search, semantic_search
from .workflows import context, handoff, finish
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
    s.add_argument('--test-evidence')
    s.add_argument('--docs-impact', choices=['updated', 'not-applicable', 'unknown'], default='unknown')
    s.add_argument('--docs-justification', default='')
    s.add_argument('--reviewed-by', help='人工审查声明；CLI 不会独立核验')
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
    return p


def _config(args, repo):
    cfg = load_config(repo)
    if getattr(args, 'docs_root', None):
        cfg['doc_roots'] = args.docs_root
    if getattr(args, 'mirror_root', None):
        cfg['mirror_roots'] = args.mirror_root
    if getattr(args, 'legacy_root', None):
        cfg['legacy_roots'] = args.legacy_root
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
    elif args.command == 'start':
        if args.top_k < 1 or args.top_k > 50:
            raise PMError('top-k 必须在 1 到 50 之间')
        emit(context(repo, load_task(args), args.top_k, _config(args, repo)), args.output)
    elif args.command == 'handoff':
        emit(handoff(repo, args.task, args.agent, args.run_id, args.completed, args.remaining, args.blocker, args.evidence, args.base_sha, args.store))
    elif args.command == 'finish':
        emit(finish(repo, load_task(args), load_pr(args), args.test_evidence, args.docs_impact, args.docs_justification, args.reviewed_by, _config(args, repo)), args.output)
    elif args.command == 'decision':
        emit({'schema_version': '1.1', 'kind': 'adr_proposal', 'path': create_adr(repo, args.title, args.topic, args.issue, args.options, args.rationale, args.owner, args.supersedes), 'status': 'proposed', 'requires_human_approval': True})
    elif args.command == 'new-doc':
        emit(create_document(repo, args.id, args.title, args.kind, args.status, args.owner, args.path, args.issue, _config(args, repo)))
    elif args.command == 'audit':
        report = audit(repo, _config(args, repo), args.allow_empty, args.scope)
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
