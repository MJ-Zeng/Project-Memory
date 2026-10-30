"""Read-only GitHub REST adapter. No mutations or credentials in output."""
from __future__ import annotations
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from .common import PMError

class GitHubReader:
    def __init__(self, slug: str, token: str | None = None, api: str = 'https://api.github.com'):
        if not re.fullmatch(r'[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+', slug):
            raise PMError('GitHub 仓库格式应为 owner/name')
        self.slug = slug
        self.token = token or os.getenv('GITHUB_TOKEN')
        self.api = api.rstrip('/')

    def get(self, endpoint: str):
        if not endpoint.startswith('/') or endpoint.startswith('//'):
            raise PMError('只允许使用 GitHub API 的相对路径')
        headers = {
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2026-03-10',
            'User-Agent': 'project-memory-mvp/0.1',
        }
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        request = urllib.request.Request(self.api + endpoint, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                return json.load(response)
        except urllib.error.HTTPError as e:
            raise PMError(f'GitHub API 返回 HTTP {e.code}：{endpoint}；请检查仓库可见性和令牌权限') from None
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            raise PMError(f'GitHub API 请求失败：{type(e).__name__}') from None

    def issue(self, number: int) -> dict:
        issue = self.get(f'/repos/{self.slug}/issues/{number}')
        if 'pull_request' in issue:
            raise PMError(f'#{number} 是 PR，不是 Issue')
        issue["_provenance"]="github_api"
        return issue

    def pull(self, number: int) -> dict:
        pull = self.get(f'/repos/{self.slug}/pulls/{number}')
        files = self.get(f'/repos/{self.slug}/pulls/{number}/files?per_page=100')
        pull['_provenance']='github_api'
        pull['changed_files_list'] = [p['filename'] for p in files]
        pull['files_partial'] = len(files) >= 100
        return pull

    def pull_request_ci_status(self, pr_number: int) -> dict:
        """Aggregate the check runs of a PR head commit from the GitHub API.

        ``status`` is fail-closed: a failed run wins over a pending one, an
        empty or truncated check-run list is ``error`` (never ``success``), so
        a missing CI configuration cannot be read as a green build.
        """
        if isinstance(pr_number, bool) or not isinstance(pr_number, int) or pr_number < 1:
            raise PMError('PR 编号必须是正整数')
        pull = self.get(f'/repos/{self.slug}/pulls/{pr_number}')
        head_sha = (pull.get('head') or {}).get('sha')
        if not head_sha:
            raise PMError(f'PR #{pr_number} 没有 head SHA')
        checks = self.get(f'/repos/{self.slug}/commits/{head_sha}/check-runs?per_page=100')
        raw_runs = checks.get('check_runs') or []
        runs = [{
            'name': run.get('name'),
            'conclusion': run.get('conclusion'),
            'status': run.get('status'),
            'html_url': run.get('html_url'),
        } for run in raw_runs]
        total = checks.get('total_count', len(runs))
        truncated = isinstance(total, int) and total > len(runs)
        if not runs or truncated:
            overall = 'error'
        elif any(run['status'] == 'completed' and run['conclusion'] != 'success'
                 for run in runs):
            overall = 'failure'
        elif any(run['status'] != 'completed' for run in runs):
            overall = 'pending'
        else:
            overall = 'success'
        return {'head_sha': head_sha, 'status': overall, 'runs': runs,
                'total_count': total, 'truncated': truncated,
                '_provenance': 'github_api'}
