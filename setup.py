"""Build shim: ship the Agent Skill inside the wheel.

A wheel install has no repository root, so the ``skill/`` lookup in bootstrap
cannot reach it.  Copying the same tree into the package at build time keeps one
canonical source and makes ``init --install`` work after a plain ``pip install``.
"""
import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

ROOT = Path(__file__).resolve().parent


class build_py_with_skill(build_py):
    def run(self):
        super().run()
        source = ROOT / 'skill' / 'project-memory'
        if not source.is_dir():
            raise SystemExit(f'构建缺少 Skill 资源目录：{source}')
        target = Path(self.build_lib) / 'project_memory' / '_skill' / 'project-memory'
        shutil.copytree(source, target, dirs_exist_ok=True)


setup(cmdclass={'build_py': build_py_with_skill})