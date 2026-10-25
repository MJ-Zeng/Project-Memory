"""Non-destructive repository initialization and skill installation."""
from __future__ import annotations
from pathlib import Path
from .common import PMError, git_sha_optional, json_text, md_header, today, write_new

TOOL_ROOT = Path(__file__).resolve().parent.parent
SKILL_SOURCE = TOOL_ROOT / 'skill' / 'project-memory'

CURRENT_STATE_BODY = '''# 当前项目状态

<!--
人类入口文档。控制在约 2k tokens，每条结论都要可核对；
只有重新核对过结论之后才更新 last_verified_at。Agent 先读这一篇。
-->

## 1. 一句话

<!-- 项目做什么，唯一可信的基线是什么。 -->

## 2. 现在到哪

| 领域 | 现状 | 状态 | 证据 |
|---|---|---|---|
| | | | |

## 3. 在做的线与阅读顺序

<!-- 每条线写：从哪开始读、接下来读什么，哪些已经暂停。 -->

## 4. 可以信什么

<!-- L = 本地复算，S = 服务器日志，D = 文档或决策。没核对过的数字要标明。 -->

## 5. 未决事项与债务

<!-- 只列出来。链接 ADR 和 Issue，不要在这里做决定。 -->

## 6. 接下来读什么

- 架构：`architecture/overview.md`
- 决策：`decisions/`
- 历史材料（不能当现状）：<!-- 路径 -->

## 接手自检

动手修改之前回答这些问题。答不出来说明这份文档有缺口，不是读者的问题。

1. 哪个基线已经验证过，用什么指标，在哪个评测集上？
2. 哪些线在做、哪些暂停或关闭，分别由谁决定？
3. 哪些数据和命令可以复现一次评测？
4. 最大的未决决策是什么，谁负责？
5. 改一处代码，可能让哪些已有结论失效？
'''


def copy_new_tree(source: Path, target: Path, files: list[str], base: Path):
    for p in sorted(source.rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts or p.suffix == '.pyc':
            continue
        out = target / p.relative_to(source)
        if write_new(out, p.read_text(encoding='utf-8')):
            files.append(out.relative_to(base).as_posix())


def _docs_root(value: str) -> str:
    root = value.strip().replace('\\', '/').strip('/')
    if not root or root == '.' or '..' in root.split('/'):
        raise PMError('--docs-root 必须是非空的相对目录')
    return root


def init(repo: Path, install: str = 'agents', docs_root: str = 'docs', profile: str = 'full',
         mirror_roots: list[str] | None = None, legacy_roots: list[str] | None = None) -> dict:
    """Does not overwrite files. Does not change GitHub branch protection or commit."""
    if install not in ('agents', 'claude', 'both', 'none'):
        raise PMError('install 目标不合法')
    if profile not in ('full', 'overlay'):
        raise PMError('init profile 不合法')
    root = _docs_root(docs_root)
    if root == 'docs' and not (repo / 'docs').exists() and (repo / 'doc').exists():
        raise PMError('已存在 doc/ 根目录；请显式传入 --docs-root，避免再创建一个竞争的 docs/ 目录')
    mirrors = [_docs_root(p) for p in (mirror_roots or [])]
    legacy = [_docs_root(p) for p in (legacy_roots or [])]
    adr_dir = root + '/decisions'
    new, skipped = [], []
    artifacts = {
        '.project-memory/.gitignore': 'cache/\nissues/\nprs/\n',
        '.project-memory/config.json': json_text({
            'schema_version': '1.1',
            'canonical_root': root,
            'doc_roots': [root],
            'mirror_roots': mirrors,
            'legacy_roots': legacy,
            'mirror_policy': 'active',
            'adr_dir': adr_dir,
            'task_source': 'github_issues_or_local_files',
            'repo_kind': 'git' if git_sha_optional(repo) else 'workspace',
            'semantic_model_path': None,
            'agent_policy': 'review_required',
            'max_search_results': 6,
            'entry_doc': root + '/CURRENT_STATE.md' if profile == 'full' else None,
            'max_verified_age_days': 90,
        }),
        f'{adr_dir}/README.md': '# 架构决策\n\nADR 状态：proposed、under-review、accepted、rejected、superseded。\n\nAccepted 决策需要可审计的人工审查；approved_by 必须指向或写明批准证据。\n',
        '.project-memory/templates/task.md': '# 任务\n\n## 目标与预期结果\n\n## 约束与非目标\n\n## 相关 canonical 文档 / ADR / 代码\n\n## 验收标准\n\n## 负责人与执行 Agent\n\n## 证据链接\n',
        '.project-memory/templates/handoff.md': '# 交接\n\n- 任务：\n- Agent / run ID：\n- 基线版本：\n- 已完成（附证据）：\n- 剩余：\n- 阻塞：\n- 改动文件：\n- 跑过的测试（命令与结果）：\n- 文档 / ADR 影响：\n- 下一步：\n',
    }
    doc_template = SKILL_SOURCE / 'assets' / 'document.template.md'
    if doc_template.is_file():
        artifacts['.project-memory/templates/document.md'] = doc_template.read_text(encoding='utf-8')
    if profile == 'full':
        artifacts.update({
            '.github/PULL_REQUEST_TEMPLATE.md': '## 任务\n\nRefs #\n\n## 改动与证据\n\n## 测试\n\n## 文档影响\n\n- [ ] 已更新 canonical 文档\n- [ ] 不适用（说明原因）\n\n## ADR 影响或架构偏差\n\n## 剩余风险与后续 Issue\n',
            '.github/ISSUE_TEMPLATE/work-item.md': '---\nname: 工作项\nabout: 可追溯的实现任务\ntitle: ""\nlabels: []\nassignees: []\n---\n\n## 问题与预期结果\n\n## 范围与约束\n\n## 验收标准\n\n## 负责人与执行 Agent\n\n## 关联 ADR / PR\n',
            '.github/CODEOWNERS.example': '# 复制审查后的条目到 .github/CODEOWNERS，并替换团队名\n# /docs/decisions/ @your-org/tech-leads\n# /docs/architecture/ @your-org/tech-leads\n# /.agents/skills/ @your-org/platform\n# /.github/workflows/ @your-org/platform\n',
            '.github/workflows/project-memory-check.yml': '''name: 项目记忆审计
on:
  pull_request:
permissions:
  contents: read
jobs:
  knowledge:
    runs-on: ubuntu-latest
    steps:
      # actions/checkout v4.2.2 固定到审核过的提交；升级时重新评估。
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
      - name: 审计当前知识
        run: PYTHONPATH=.project-memory/tooling python3 -m project_memory audit --repo . --scope current --fail-on high
''',
            f'{root}/INDEX.md': md_header({'id': 'DOC-INDEX', 'kind': 'canonical', 'title': '知识索引', 'status': 'current', 'owner': 'team', 'updated_at': today()}) + '# 知识索引\n\n- [当前状态](CURRENT_STATE.md)\n- [架构](architecture/overview.md)\n- [决策](decisions/README.md)\n',
            f'{root}/CURRENT_STATE.md': md_header({'id': 'DOC-STATE', 'kind': 'canonical', 'title': '当前项目状态', 'status': 'current', 'owner': 'team', 'updated_at': today()}) + CURRENT_STATE_BODY,
            f'{root}/architecture/overview.md': md_header({'id': 'DOC-ARCH', 'kind': 'canonical', 'title': '架构总览', 'status': 'current', 'owner': 'team', 'updated_at': today()}) + '# 架构总览\n\n待补：换成经过核实的系统架构。\n',
        })
    for rel, body in artifacts.items():
        if write_new(repo / rel, body):
            new.append(rel)
        else:
            skipped.append(rel)
    copy_new_tree(TOOL_ROOT / 'project_memory', repo / '.project-memory' / 'tooling' / 'project_memory', new, repo)
    copy_new_tree(SKILL_SOURCE, repo / '.project-memory' / 'tooling' / 'skill' / 'project-memory', new, repo)
    folders = (['.agents/skills'] if install == 'agents' else ['.claude/skills'] if install == 'claude' else ['.agents/skills', '.claude/skills'] if install == 'both' else [])
    for folder in folders:
        copy_new_tree(SKILL_SOURCE, repo / folder / 'project-memory', new, repo)
    manual_actions = [
        '检查生成的文件，配置 CODEOWNERS（示例本身不生效）。',
        '在 GitHub 开启分支 Ruleset、必需 CI 和人工批准。',
        '补全项目架构和负责人。',
        'canonical 文档被复制到别处时，在 .project-memory/config.json 设置 mirror_roots / legacy_roots。',
        '通过 PR 提交审查后的文件；初始化不会提交或推送。',
    ]
    if profile == 'full':
        manual_actions.insert(1, '填写生成的 CURRENT_STATE.md，核对之后把 last_verified_at 改成实际日期。')
    else:
        manual_actions.insert(1, 'overlay 不生成入口文档：补一篇 status 为 current、带 last_verified_at 的当前状态文档，然后在 .project-memory/config.json 设置 entry_doc。')
    return {
        'schema_version': '1.1',
        'kind': 'init_report',
        'profile': profile,
        'docs_root': root,
        'mirror_roots': mirrors,
        'legacy_roots': legacy,
        'entry_doc': root + '/CURRENT_STATE.md' if profile == 'full' else None,
        'created': new,
        'skipped_existing': skipped,
        'manual_actions': manual_actions,
    }
