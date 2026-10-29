"""Shared openssl discovery for the signing test suites (B2/B3/B4).

Local runs without openssl may skip the signing suites, but a release/CI run
must not treat that skip as a pass.  Set ``PROJECT_MEMORY_REQUIRE_OPENSSL=1``
(``true``/``yes`` also accepted, case-insensitive) to turn a missing binary
into a hard failure.
"""
import os
import shutil
import unittest

REQUIRE_ENV = 'PROJECT_MEMORY_REQUIRE_OPENSSL'
_TRUTHY = {'1', 'true', 'yes'}


def openssl_required() -> bool:
    return os.environ.get(REQUIRE_ENV, '').strip().casefold() in _TRUTHY


def openssl_path() -> str | None:
    return shutil.which('openssl')


def require_openssl(purpose: str) -> str:
    path = openssl_path()
    if path:
        return path
    if openssl_required():
        raise AssertionError(
            f'找不到 openssl：{purpose}；{REQUIRE_ENV} 已开启，'
            '发布/CI 不允许跳过签名测试')
    raise unittest.SkipTest(f'找不到 openssl；{purpose}；设置 {REQUIRE_ENV}=1 可要求失败')
