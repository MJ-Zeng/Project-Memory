"""S4-3: static checks on the release-build workflow.

``.github/workflows/release.yml`` builds the release artifacts (source
archive, sdist, wheel, ``sha256sums.txt``, ``BUILD-INFO.json``), asks GitHub
for an artifact attestation over the built files and uploads everything as
workflow artifacts.  It deliberately does not create a tag or a Release.

These tests read the workflow as text; they never touch the network, never run
a workflow step and never call GitHub.  Parsing stays regex/line based (the
same loose-but-explicit style as ``test_b7_ci_second_identity.py``) instead of
a full YAML parse, so no new dependency is needed.

What a green run here does *not* establish, and what only the post-merge
``workflow_dispatch`` dry run can establish:

* that Sigstore/GitHub actually issues an attestation for this repository —
  attestation needs a hosted runner with an OIDC token, so it cannot be
  produced or verified locally;
* that ``build`` produces a working sdist/wheel for the current tree;
* that the tag-push trigger fires and resolves correctly, which stays
  unexercised until a human creates a tag (S4-5).

So these tests lock the shape that makes those claims *checkable* and honest:
narrow triggers, minimal permissions, pinned actions, no Release-creating call
and no secret reachable from the job.
"""
import re
import unittest
from pathlib import Path

WORKFLOW = (Path(__file__).resolve().parents[1]
            / '.github' / 'workflows' / 'release.yml')

CHECKOUT_SHA = 'actions/checkout@11d5960a326750d5838078e36cf38b85af677262'
ATTEST_SHA = ('actions/attest-build-provenance@'
              '4d101475d8b20a2381f78447822ac1eab6504dd8')
UPLOAD_SHA = ('actions/upload-artifact@'
              'ea165f8d65b6e75b540449e92b4886f43607fa02')

# The manifest's self-exclusion guard, in either find spelling (`!` / `-not`)
# and with or without a quoted filename; both rewrites mean the same thing, so
# the test must not pin the literal bytes.
MANIFEST_SELF_EXCLUSION = re.compile(
    r"""(?:!|-not)[ \t]+-name[ \t]+['"]?sha256sums\.txt""")

# `subject-path` must be *exactly* the whole dist tree, up to end of line.
# A same-line comment is allowed; anything else after `dist/*` narrows what the
# attestation covers, so the pattern is anchored with re.MULTILINE (`$` without
# it only matches the very end of the string and could never fire).
SUBJECT_PATH_WHOLE_DIST = re.compile(
    r"""^[ \t]*subject-path:[ \t]*"""
    r"""\$\{\{ github\.workspace \}\}/dist/\*[ \t]*(?:#.*)?$""",
    re.MULTILINE)

# Actions that would publish a Release; none of them may appear.
RELEASE_PUBLISHING = (
    'gh release create', 'gh release upload', 'gh api repos',
    'actions/create-release', 'softprops/action-gh-release',
    'actions/github-script', 'ncipolino/release-action',
)


class ReleaseWorkflowStaticTest(unittest.TestCase):
    """Card §5 items 1-10, static only."""

    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding='utf-8').replace('\r\n', '\n')
        cls.lines = cls.text.splitlines()
        cls.step_indent = min(len(line) - len(line.lstrip())
                              for line in cls.lines
                              if re.match(r'^\s*- ', line))

    def block(self, key: str):
        """The indented body of a top-level ``key:`` mapping."""
        try:
            start = next(i for i, line in enumerate(self.lines)
                         if line == f'{key}:')
        except StopIteration:
            self.fail(f'release.yml 缺少顶层 {key}: 段落')
        body = []
        for line in self.lines[start + 1:]:
            if not line.strip():
                continue
            if not line[:1].isspace():
                break
            if line.lstrip().startswith('#'):
                continue
            body.append(line)
        return body

    def step_window(self, needle):
        """Every line of the step whose definition contains ``needle``."""
        index = next((i for i, line in enumerate(self.lines) if needle in line),
                     None)
        self.assertIsNotNone(index, f'release.yml 中找不到 {needle!r}')
        marker = ' ' * self.step_indent + '- '
        for offset in range(index + 1, len(self.lines)):
            if self.lines[offset].startswith(marker):
                return self.lines[index:offset]
        return self.lines[index:]

    def permission_blocks(self):
        """Every ``permissions:`` mapping in the file, with its indentation.

        A job (or a step) may declare its own ``permissions:``; Actions then
        overlays it on the workflow-level block, so reading only column zero
        would let a ``contents: write`` buried in the job pass unnoticed.
        """
        blocks = []
        for index, line in enumerate(self.lines):
            match = re.fullmatch(r'( *)permissions:(.*)', line)
            if match is None:
                continue
            indent, inline = len(match.group(1)), match.group(2).strip()
            body = []
            for entry in self.lines[index + 1:]:
                if not entry.strip():
                    continue
                if len(entry) - len(entry.lstrip()) <= indent:
                    break
                if entry.lstrip().startswith('#'):
                    continue
                body.append(entry)
            blocks.append({'indent': indent, 'inline': inline, 'body': body})
        return blocks

    def effective_permissions(self):
        """Grants after overlaying every level, the way Actions resolves them."""
        granted, inline = {}, {}
        for block in sorted(self.permission_blocks(), key=lambda b: b['indent']):
            if block['inline']:
                inline[block['indent']] = block['inline']
            for line in block['body']:
                match = re.fullmatch(r'\s*([A-Za-z_-]+):[ \t]*(\S+)\s*', line)
                if match is None:
                    self.fail(f'无法解析权限行 {line!r}')
                granted[match.group(1)] = match.group(2)
        return granted, inline

    # 1 ------------------------------------------------------------------
    def test_workflow_exists_and_is_named_release(self):
        self.assertTrue(WORKFLOW.is_file(), f'{WORKFLOW} 不存在')
        self.assertRegex(
            self.text, re.compile(r'^name:[ \t]*release[ \t]*$', re.MULTILINE),
            '工作流必须名为 release')

    # 2 ------------------------------------------------------------------
    def test_triggers_are_only_tag_push_and_manual_dispatch(self):
        body = self.block('on')
        keys = sorted(m.group(1) for line in body
                      if (m := re.fullmatch(r' {2}([A-Za-z_-]+):.*', line)))
        self.assertEqual(['push', 'workflow_dispatch'], keys,
                         '只允许 push.tags 与 workflow_dispatch 两个入口')
        self.assertEqual(["tags: ['v*']", 'workflow_dispatch:'],
                         [line.strip() for line in body
                          if line.strip() in ("tags: ['v*']",
                                              'workflow_dispatch:')],
                         'tag 触发必须限定 v*，dispatch 必须是裸键')

    def test_no_pull_request_trigger_of_either_kind(self):
        for trigger in ('pull_request', 'pull_request_target'):
            self.assertIsNone(
                re.search(rf'^\s*{trigger}:', self.text, re.MULTILINE),
                f'{trigger}: 触发会把未合并的 PR 代码放进发布构建里')

    # 3 ------------------------------------------------------------------
    def test_permissions_is_declared_only_at_workflow_level(self):
        blocks = self.permission_blocks()
        self.assertTrue(blocks, 'release.yml 必须声明 permissions')
        self.assertEqual(1, len(blocks),
                         '多一处 permissions 就多一层覆盖关系：job 或 step 层的'
                         '声明会追加/改写工作流层的权限，不能被顶层段落代表')
        self.assertEqual([0], [block['indent'] for block in blocks],
                         'permissions 只能出现在工作流层（第 0 列）')

    def test_permissions_are_exactly_the_three_declared(self):
        granted, inline = self.effective_permissions()
        self.assertEqual({}, inline,
                         '不允许 write-all 这类行内权限；逐条列举才看得住')
        self.assertEqual({'contents': 'read', 'id-token': 'write',
                          'attestations': 'write'}, granted,
                         '按各层叠加后的有效权限比较，而不是只看顶层段落')

    def test_permissions_grant_nothing_more_than_needed(self):
        granted, _ = self.effective_permissions()
        self.assertEqual('read', granted.get('contents'),
                         '制品只进 artifact 存储，写仓库内容不在本工作流职责内')
        self.assertNotIn('write-all', self.text)

    # 4 ------------------------------------------------------------------
    def test_every_action_is_pinned_to_a_40_hex_commit(self):
        uses = re.findall(r'uses:\s*(\S+)', self.text)
        self.assertGreaterEqual(len(uses), 4, 'checkout/setup/attest/upload 都要有')
        for reference in uses:
            name, _, revision = reference.partition('@')
            self.assertRegex(name, r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$',
                             f'{reference} 不是 owner/repo 形式')
            self.assertRegex(revision, r'^[0-9a-f]{40}$',
                             f'{name} 必须按提交 SHA 固定，不能用浮动标签')

    def test_pinned_shas_are_the_resolved_ones(self):
        for reference in (CHECKOUT_SHA, ATTEST_SHA, UPLOAD_SHA):
            self.assertIn(reference, self.text,
                          f'{reference} 应与解析记录一致')
        self.assertIsNone(re.search(r'uses:\s*\S+@v\d', self.text),
                          '不允许 @vN 之类的浮动版本引用')

    # 5 ------------------------------------------------------------------
    def test_checkout_does_not_persist_credentials(self):
        body = '\n'.join(self.step_window('uses: actions/checkout@'))
        self.assertIn('persist-credentials: false', body,
                      'checkout 留下的 token 会被后续步骤复用，必须关掉')
        self.assertIn('fetch-depth: 0', body,
                      'git archive 需要完整对象库')

    # 6 ------------------------------------------------------------------
    def test_builds_sdist_wheel_source_archive_and_manifests(self):
        self.assertIn('python -m build', self.text,
                      'sdist 与 wheel 由 build 前端产出')
        self.assertIn('git archive --format=tar.gz', self.text,
                      '源码归档必须来自被构建的 commit')
        self.assertIn('BUILD-INFO.json', self.text)
        self.assertIn('dist/sha256sums.txt', self.text)
        self.assertIn('sha256sum --text', self.text,
                      '--text 固定 "<hex>  <name>" 双空格格式')

    def test_checksum_manifest_excludes_itself(self):
        # 清单若把自己的哈希也算进去，`sha256sum -c` 就永远对不上：写完清单再校验
        # 时文件内容已经变了。运行期会失败，但合并前的静态门禁也要抓得住。
        body = '\n'.join(self.step_window('- name: Write sha256sums.txt'))
        self.assertIsNotNone(
            MANIFEST_SELF_EXCLUSION.search(body),
            '列举制品时必须用 ! / -not 排除 sha256sums.txt 自身')
        self.assertIn(': > sha256sums.txt', body,
                      '清单必须先截断为空再逐行追加，否则重复运行会累积旧行')

    def test_build_info_fields_are_not_allowed_to_be_empty(self):
        # `export X="$(cmd)"` 掩盖失败：赋值命令退出码被吞掉，空字段照样写进
        # BUILD-INFO。所以取值必须是普通赋值，并且每个字段在写出前检查非空。
        body = '\n'.join(self.step_window('- name: Write BUILD-INFO.json'))
        for lower, upper in (('pm_python_version', 'PM_PYTHON_VERSION'),
                             ('pm_build_version', 'PM_BUILD_VERSION'),
                             ('pm_generated_at', 'PM_GENERATED_AT')):
            self.assertIn(f'{lower}="$(', body,
                          f'{lower} 必须先用普通赋值取到值，才能被检查')
            self.assertNotIn(f'export {upper}="$(', body,
                             f'export {upper}="$()" 会吞掉失败，把空值写进 BUILD-INFO')
        self.assertIn('取值为空', body)
        self.assertIn('exit 1', body)

    # 7 ------------------------------------------------------------------
    def test_attests_build_provenance_over_the_dist_tree(self):
        body = '\n'.join(self.step_window(
            'uses: actions/attest-build-provenance@'))
        self.assertEqual(
            1, len(re.findall(r'^[ \t]*subject-path:', body, re.MULTILINE)),
            'subject-path 只能有一条，多条会让人读错被证明的是哪些文件')
        self.assertIsNotNone(
            SUBJECT_PATH_WHOLE_DIST.search(body),
            '值必须恰好是 dist 下的全部制品：行尾多出的 *.whl / *.tar.gz 会把证明'
            '范围收窄，sdist、源码归档和哈希清单就落在证明之外')

    def test_attest_step_selects_subject_only_by_path(self):
        # 该 action 要求 subject-path / subject-digest / subject-checksums 三者
        # 只选一个；换成后两种就被指向了另一组制品，dist/* 的覆盖不再成立。
        body = '\n'.join(self.step_window(
            'uses: actions/attest-build-provenance@'))
        self.assertIn('subject-path:', body)
        for alternative in ('subject-digest:', 'subject-checksums:',
                            'push-to-registry:'):
            self.assertNotIn(alternative, body,
                             f'{alternative} 会把证明对象从 dist 目录换成别的东西')

    def test_attestation_bundle_is_kept_outside_the_checksummed_tree(self):
        # bundle 是该 action 的 *output*，不是 input；output 给了路径但文件不在
        # （或根本没给路径）时必须报错退出，否则 artifact 里会出现一个自称有
        # attestation 的空目录。
        self.assertIn('${{ steps.attest.outputs.bundle-path }}', self.text)
        lines = self.step_window('- name: Keep the attestation bundle')
        body = '\n'.join(lines)
        self.assertIn('attestation/attestation.json', body)
        self.assertIn('[ -z "${PM_BUNDLE_PATH}" ]', body,
                      'output 为空要失败，不能静默跳过')
        self.assertIn('[ ! -f "${PM_BUNDLE_PATH}" ]', body,
                      '只判断非空不够：路径存在但文件缺失时只有 cp 的报错，'
                      '看不出是“没有 attestation”')
        self.assertIn('不谎称已生成', body)
        error_line = next(i for i, line in enumerate(lines) if '::error::' in line)
        copy_line = next(i for i, line in enumerate(lines)
                         if 'cp "${PM_BUNDLE_PATH}"' in line)
        self.assertLess(error_line, copy_line, '报错必须在 cp 之前')

    # 8 ------------------------------------------------------------------
    def test_uploads_every_artifact_as_a_workflow_artifact(self):
        body = '\n'.join(self.step_window('uses: actions/upload-artifact@'))
        self.assertIn('dist/*', body, '构建目录整体上传')
        self.assertIn('attestation/*', body, 'attestation bundle 也要能下载')
        self.assertIn('if-no-files-found: error', body)

    # 9 ------------------------------------------------------------------
    def test_nothing_in_the_workflow_publishes_a_release(self):
        for marker in RELEASE_PUBLISHING:
            self.assertNotIn(marker, self.text,
                             f'出现 {marker!r}：本工作流只构建，发布留给 S4-5')
        self.assertNotIn('git tag ', self.text, '工作流不得自己创建 tag')

    # 10 -----------------------------------------------------------------
    def test_no_repository_secret_is_reachable_or_echoed(self):
        self.assertNotIn('secrets.', self.text,
                         '发布构建不读任何仓库 secret；没有 secret 就不可能回显')
        self.assertNotIn('PM_GH_TOKEN', self.text)
        self.assertIsNone(
            re.search(r'(echo|printf)[^\n]*\$\{?\{?\s*secrets\.', self.text),
            '禁止把 secret 展开进日志')

    def test_dispatch_tag_input_is_validated_before_use(self):
        body = '\n'.join(self.step_window('- name: resolve build ref'))
        self.assertIn("grep -Eq '^[A-Za-z0-9][A-Za-z0-9._-]*$'", body,
                      'tag 输入先校验形状，再进入 git fetch 与 $GITHUB_ENV')
        self.assertIn('+refs/tags/${PM_INPUT_TAG}:refs/tags/${PM_INPUT_TAG}',
                      body)


if __name__ == '__main__':
    unittest.main()
