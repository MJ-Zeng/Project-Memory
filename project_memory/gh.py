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
