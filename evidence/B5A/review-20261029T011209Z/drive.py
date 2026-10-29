"""Independent B5A review driver (PM-03). Runs the supported native wrappers
against fake launcher / fake package / cwd / normal, the bare -m residual, and
the previous-candidate comparison. Writes JSON evidence. No product code touched."""
import json
import os
import shutil
import subprocess
from pathlib import Path

BASE = Path(r"C:\Documents\02_Research\Code\project-memory-verification-lab\import-workspace\pm-pilot-03")
REPO = BASE / ".pilot" / "b5a-candidate"      # 9288818
REPO_PREV = BASE / ".pilot" / "b5a-prev"      # 85b1a4e
REPO_BASE = BASE / ".pilot" / "b5a-base"      # ddd9dba
FIX = Path(r"C:\Documents\02_Research\Code\project-memory-verification-lab\fixtures\b5a")
OUT = Path(r"C:\Users\ZMJ\AppData\Local\Temp\b5a-review-20261029T011209Z")
WORK = OUT / "work"
PY_WIN = r"C:\SoftWare\Anconda\python.exe"
PY_POSIX = "/c/SoftWare/Anconda/python.exe"


def fresh_env():
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env.pop("PROJECT_MEMORY_PYTHON", None)
    return env


def run(args, cwd, extra=None, timeout=120):
    env = fresh_env()
    if extra:
        env.update({k: str(v) for k, v in extra.items()})
    return subprocess.run([str(a) for a in args], cwd=str(cwd), env=env,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def classify(p):
    out = (p.stdout or "") + (p.stderr or "")
    return {
        "exit": p.returncode,
        "FAKE_LAUNCHER": "FAKE_LAUNCHER" in out,
        "SHADOW_INIT": "SHADOW_INIT" in out,
        "SHADOW_MAIN": "SHADOW_MAIN" in out,
        "real_help": "用法：project-memory" in (p.stdout or ""),
        "stdout_head": (p.stdout or "")[:200],
        "stderr_head": (p.stderr or "")[:300],
    }


def posix(args):
    return ["sh", str(REPO / "bin" / "project-memory"), *args]


def win(args):
    return [os.environ.get("COMSPEC", "cmd.exe"), "/c", str(REPO / "bin" / "project-memory.cmd"), *args]


def make_own_fixtures():
    """Independent marker-writing fixtures (extra beyond the shared ones)."""
    ld = WORK / "own_launcher"
    ld.mkdir(parents=True)
    (ld / "_project_memory_launcher.py").write_text(
        "import os, pathlib\n"
        "m = os.environ.get('B5A_MARKER')\n"
        "if m:\n    pathlib.Path(m).write_text('launcher')\n"
        "print('FAKE_LAUNCHER')\n"
        "raise SystemExit(0)\n", encoding="utf-8")
    sd = WORK / "own_shadow" / "project_memory"
    sd.mkdir(parents=True)
    (sd / "__init__.py").write_text(
        "import os, pathlib\n"
        "m = os.environ.get('B5A_MARKER')\n"
        "if m:\n    pathlib.Path(m).write_text('init')\n"
        "print('SHADOW_INIT')\n", encoding="utf-8")
    (sd / "__main__.py").write_text(
        "print('SHADOW_MAIN')\nraise SystemExit(0)\n", encoding="utf-8")
    return ld, sd.parent


def copy_cwd(name, src_fixture):
    dst = WORK / name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src_fixture, dst)
    return dst


def marker_absent(p):
    return not Path(p).exists()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    own_launcher, own_shadow = make_own_fixtures()
    empty = WORK / "empty"
    empty.mkdir()

    cwd_shadow = copy_cwd("cwd_shadow", FIX / "cwd-shadow")
    cwd_own = copy_cwd("cwd_own", own_shadow)

    pe = {"PROJECT_MEMORY_PYTHON": PY_POSIX}
    we = {"PROJECT_MEMORY_PYTHON": PY_WIN}

    results = {"fake_launcher": [], "fake_package": [], "normal": [],
               "bare_m": [], "prev": [], "env": {}}

    def rec(bucket, name, p, marker=None):
        row = {"case": name}
        row.update(classify(p))
        if marker:
            row["marker_written"] = not marker_absent(marker)
        results[bucket].append(row)
        print(f"[{bucket}] {name}: exit={row['exit']} fake={row['FAKE_LAUNCHER']} "
              f"shadow={row['SHADOW_INIT'] or row['SHADOW_MAIN']} help={row['real_help']}")

    # ---- Normal calls ----
    rec("normal", "posix_wrapper_normal", run(posix(["--help"]), empty, pe))
    rec("normal", "windows_wrapper_normal", run(win(["--help"]), empty, we))
    rec("normal", "bare_m_normal_repo", run([PY_WIN, "-m", "project_memory", "--help"], REPO))

    # ---- Fake launcher (supported wrapper must resist) ----
    for tag, wrap, e in (("posix", posix, pe), ("windows", win, we)):
        rec("fake_launcher", f"{tag}_pythonpath_shared", run(wrap(["--help"]), empty,
            {**e, "PYTHONPATH": str(FIX / "launcher-shadow")}))
        mk = WORK / f"mk_{tag}_py_shared"
        rec("fake_launcher", f"{tag}_pythonpath_own_marker", run(wrap(["--help"]), empty,
            {**e, "PYTHONPATH": str(own_launcher), "B5A_MARKER": str(mk)}), marker=mk)
    rec("fake_launcher", "posix_cwd_fake_launcher", run(posix(["--help"]), cwd_shadow, pe))

    # ---- Fake package (supported wrapper must resist) ----
    for tag, wrap, e in (("posix", posix, pe), ("windows", win, we)):
        rec("fake_package", f"{tag}_pythonpath_shared", run(wrap(["--help"]), empty,
            {**e, "PYTHONPATH": str(FIX / "shadow")}))
        mk = WORK / f"mk_{tag}_pkg_own"
        rec("fake_package", f"{tag}_pythonpath_own_marker", run(wrap(["--help"]), empty,
            {**e, "PYTHONPATH": str(own_shadow), "B5A_MARKER": str(mk)}), marker=mk)
        ck = WORK / f"mk_{tag}_cwd_own"
        rec("fake_package", f"{tag}_cwd_own_marker", run(wrap(["--help"]), cwd_own,
            {**e, "B5A_MARKER": str(ck)}), marker=ck)
    rec("fake_package", "posix_cwd_shared", run(posix(["--help"]), cwd_shadow, pe))
    rec("fake_package", "windows_cwd_shared", run(win(["--help"]), cwd_shadow, we))
    # combined cwd shadow + pythonpath launcher
    rec("fake_package", "posix_cwd_both", run(posix(["--help"]), cwd_shadow,
        {**pe, "PYTHONPATH": str(FIX / "launcher-shadow")}))

    # ---- Bare -m residual (documented; NOT a pass) ----
    rec("bare_m", "residual_tmp_pythonpath", run([PY_WIN, "-m", "project_memory", "--help"],
        empty, {"PYTHONPATH": str(FIX / "shadow")}))
    rec("bare_m", "raw_cwd_shadow", run([PY_WIN, "-m", "project_memory", "--help"], cwd_shadow))
    rec("bare_m", "guarded_repo_pythonpath", run([PY_WIN, "-m", "project_memory", "--help"],
        REPO, {"PYTHONPATH": str(FIX / "shadow")}))
    rec("bare_m", "isolated_tmp_pythonpath", run([PY_WIN, "-I", "-P", "-m", "project_memory", "--help"],
        empty, {"PYTHONPATH": str(FIX / "shadow")}))

    # ---- Previous candidate / base comparison (fixture effectiveness) ----
    probe = str(FIX / "console_entry_probe.py")
    # old module:function form, fake launcher first on PYTHONPATH -> FAKE_LAUNCHER
    p_prev = run([PY_WIN, probe, "--help"], empty,
                 {"PYTHONPATH": str(FIX / "launcher-shadow") + ";" + str(REPO_PREV)})
    rec("prev", "prev_85b1a4e_probe_fake_launcher", p_prev)
    p_cand = run([PY_WIN, probe, "--help"], empty,
                 {"PYTHONPATH": str(FIX / "launcher-shadow") + ";" + str(REPO)})
    rec("prev", "candidate_probe_oldform_fake_launcher", p_cand)
    # base repo bare -m with PYTHONPATH shadow -> SHADOW_INIT
    rec("prev", "base_ddd9dba_bare_m_pythonpath", run([PY_WIN, "-m", "project_memory", "--help"],
        empty, {"PYTHONPATH": str(FIX / "shadow")}))
    # prev pyproject still has module:function entry (record)
    results["env"]["prev_pyproject_scripts"] = [
        ln.strip() for ln in (REPO_PREV / "pyproject.toml").read_text(encoding="utf-8").splitlines()
        if "project-memory" in ln or "py-modules" in ln or "[project.scripts]" in ln
    ]
    results["env"]["cand_pyproject_scripts"] = [
        ln.strip() for ln in (REPO / "pyproject.toml").read_text(encoding="utf-8").splitlines()
        if ln.strip().startswith("project-memory") or "py-modules" in ln
    ]

    (OUT / "fake-launcher.json").write_text(json.dumps(results["fake_launcher"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "fake-package.json").write_text(json.dumps(results["fake_package"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "normal.json").write_text(json.dumps(results["normal"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "bare-m.json").write_text(json.dumps(results["bare_m"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "prev-candidate.json").write_text(json.dumps(results["prev"] + [results["env"]], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "matrix.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("DONE")


if __name__ == "__main__":
    main()
