#!/usr/bin/env python3
"""registry 校验规则的自测：正例通过 + 每个反例都必须被拦住。

为什么要有这个文件：`validate_plugins.py` 是审核闸的唯一实现，它一旦失效，
registry 就变成「谁都能推什么就上什么」。改规则（放宽白名单、调大小上限）时
先跑这个，比推上去看 CI 红灯快得多：

    python .github/scripts/selftest.py

每个用例在临时目录里复制一份 registry，改一处，然后跑真正的校验脚本。
断言的是**脚本的退出码与报错文案**，不是内部函数 —— 这样重构实现不会误报。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
VALIDATOR = HERE / "validate_plugins.py"
AGGREGATOR = HERE / "aggregate_index.py"

PLUGIN_DIR = "plugins/FM-FONT-RENAME__alice"
PID = "FM-FONT-RENAME"
# 固定时间戳：聚合的输出里只有 generatedAt 会随「现在几点」变，钉住它才能比字节。
NOW = "2026-01-01T00:00:00Z"


def run(root: Path, *extra: str) -> tuple[int, str, str]:
    p = subprocess.run(
        [sys.executable, str(VALIDATOR), "--root", str(root), *extra],
        capture_output=True, text=True,
    )
    return p.returncode, p.stdout, p.stderr


def run_aggregate(root: Path, *extra: str) -> tuple[int, str, str]:
    p = subprocess.run(
        [sys.executable, str(AGGREGATOR), "--root", str(root), *extra],
        capture_output=True, text=True,
    )
    return p.returncode, p.stdout, p.stderr


def copy_repo(dst: Path) -> Path:
    shutil.copytree(
        REPO, dst,
        ignore=shutil.ignore_patterns(".git", "__pycache__"),
        dirs_exist_ok=True,
    )
    return dst


def patch_manifest(root: Path, mutate) -> None:
    mf = root / PLUGIN_DIR / "plugin.json"
    m = json.loads(mf.read_text(encoding="utf-8"))
    mutate(m)
    mf.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


CASES: list[tuple[str, str, callable]] = []


def case(name: str, expect: str):
    """注册一个「必须被拦住」的反例，expect = 报错里应出现的关键字。"""
    def deco(fn):
        CASES.append((name, expect, fn))
        return fn
    return deco


@case("篡改文件内容但没更新 sha256", "sha256 与清单不符")
def _(root: Path) -> None:
    patch_manifest(root, lambda m: m["files"][1].update(
        sha256="0" * 64,
    ))


@case("entry 没登记在 files 里", "没有登记在 files 里")
def _(root: Path) -> None:
    patch_manifest(root, lambda m: m.update(entry="other.py"))
    (root / PLUGIN_DIR / "other.py").write_text("print(1)\n", encoding="utf-8")


@case("entry 指向不存在的文件", "文件不存在")
def _(root: Path) -> None:
    patch_manifest(root, lambda m: m["files"].append({"path": "gone.py"}))


@case("名称超过 25 个字", "最多 25 个字")
def _(root: Path) -> None:
    # 面板与这里同口径：卡片一行放不下，超过就不让上架
    patch_manifest(root, lambda m: m.update(name="长" * 30))


@case("权限名不在白名单里", "权限名不在白名单里")
def _(root: Path) -> None:
    patch_manifest(root, lambda m: m.update(permissions=["fonts:read"]))


@case("路径穿越", "路径不安全")
def _(root: Path) -> None:
    patch_manifest(root, lambda m: m["files"].append({"path": "../evil.py"}))


@case("目录里有未登记的文件", "未登记在 files 里的文件")
def _(root: Path) -> None:
    (root / PLUGIN_DIR / "hidden.py").write_text("print('payload')\n", encoding="utf-8")


@case("脚本宿主类型（.bat）", "不在白名单里")
def _(root: Path) -> None:
    # .exe / .dll 自 2026-11-25 起已放开（原生插件），但 bat/cmd/ps1/sh/vbs
    # 仍然拒收 —— 它们只会被别的文件加载，用户点开的其实是「看不见的脚本」。
    (root / PLUGIN_DIR / "dropper.bat").write_bytes(b"@echo off\n")
    patch_manifest(root, lambda m: m["files"].append({"path": "dropper.bat"}))


@case("目录名与 id__author 不一致", "目录名必须等于")
def _(root: Path) -> None:
    patch_manifest(root, lambda m: m.update(author="bob"))


@case("id 不合法（无前缀）", "id 不合法")
def _(root: Path) -> None:
    patch_manifest(root, lambda m: m.update(id="Bad_ID"))


@case("id 还是旧式包名（点号）", "id 不合法")
def _(root: Path) -> None:
    # 旧规则放行 com.iieozo.adobe-font；新规则前缀必须是 FM / AM，点号一律拒
    patch_manifest(root, lambda m: m.update(id="com.example.adobe-font"))


@case("id 前缀小写", "id 不合法")
def _(root: Path) -> None:
    # 前缀是软件编号，必须大写：fm-xxx 与 FM-xxx 是两回事，不能混着收
    patch_manifest(root, lambda m: m.update(id="fm-FONT-RENAME"))


@case("id 前缀不在表里", "id 不合法")
def _(root: Path) -> None:
    patch_manifest(root, lambda m: m.update(id="ZZ-FONT-RENAME"))


@case("id 超过 40 字符", "id 不合法")
def _(root: Path) -> None:
    # 形状合法但整串超长：长度检查不能只写在正则里（换写法时最容易漏）
    patch_manifest(root, lambda m: m.update(id="FM-" + "A" * 20 + "-" + "B" * 18))


@case("社区件谎报 official", "不许声明 official=true")
def _(root: Path) -> None:
    patch_manifest(root, lambda m: m.update(official=True))


@case("brief 超长", "brief 必须是")
def _(root: Path) -> None:
    patch_manifest(root, lambda m: m.update(brief="长" * 201))


@case("单文件超过 10MB", "单文件")
def _(root: Path) -> None:
    big = root / PLUGIN_DIR / "big.bin"
    big.write_bytes(b"\0" * (10 * 1024 * 1024 + 1))
    patch_manifest(root, lambda m: m["files"].append({"path": "big.bin"}))


@case("缺 entry 字段", "清单缺字段")
def _(root: Path) -> None:
    patch_manifest(root, lambda m: m.pop("entry"))


def author_cases() -> list[tuple[str, bool, str]]:
    """作者归属：非维护者只能改自己的目录。返回 (说明, 应通过?, author)。"""
    return [
        ("非维护者改别人的目录 → 拦", False, "alice"),
        ("目录主人自己改 → 放行", True, "anonymous-7f3a"),
        ("维护者改任何目录 → 放行", True, "706972745"),
    ]


def write_index(root: Path) -> None:
    """在临时副本里真跑一遍聚合。只写副本，仓库里的 index.json 不碰。"""
    code, out, err = run_aggregate(root, "--now", NOW)
    if code != 0:
        raise RuntimeError(f"聚合失败：{err.strip() or out.strip()}")


def entry_of(root: Path, pid: str) -> dict:
    data = json.loads((root / "index.json").read_text(encoding="utf-8"))
    for e in data["plugins"]:
        if e["id"] == pid:
            return e
    raise KeyError(f"聚合结果里没有 {pid}")


def with_run_fields(m: dict) -> None:
    """模拟 1.4.1+ 上传面板写进 plugin.json 的运行字段。"""
    m.update(
        hooks=["init", "settings"],
        menus=[{"title": "双击套用", "on": "plugin"}],
        settings={"title": "设置"},
    )


def check_run_fields(e: dict) -> str | None:
    for k in ("hooks", "menus", "settings"):
        if k not in e:
            return f"条目里没有 {k}（被聚合丢掉了）"
    if e["hooks"] != ["init", "settings"]:
        return f"hooks 内容不一致：{e['hooks']!r}"
    if e["menus"] != [{"title": "双击套用", "on": "plugin"}]:
        return f"menus 内容不一致：{e['menus']!r}"
    return None


def check_no_junk(e: dict) -> str | None:
    if "__junk" in e:
        return "allowlist 外的键 __junk 混进了清单"
    return None


def check_empty_skipped(e: dict) -> str | None:
    for k in ("hooks", "summary"):
        if k in e:
            return f"空值 {k} 被写进了条目（会变成清单噪声）"
    return None


def aggregate_cases() -> list[tuple[str, callable, callable]]:
    """聚合透传用例：(说明, 改清单, 断言条目)。"""
    return [
        ("正例：hooks / menus / settings 进了清单", with_run_fields, check_run_fields),
        ("反例：allowlist 外的键不进清单", lambda m: m.update(__junk={"x": 1}), check_no_junk),
        ("空值：hooks=[] 与 summary=\"\" 不写入", lambda m: m.update(hooks=[], summary=""), check_empty_skipped),
    ]


def main() -> int:
    failures: list[str] = []

    # ── 正例 ──
    with tempfile.TemporaryDirectory() as tmp:
        root = copy_repo(Path(tmp) / "repo")
        code, out, err = run(root)
        if code != 0:
            failures.append(f"正例（当前仓库）应当通过，实际失败：\n{err}")
        else:
            print(f"ok  正例：当前仓库通过（{out.strip().splitlines()[0]}）")

    # ── 反例 ──
    for name, expect, mutate in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_repo(Path(tmp) / "repo")
            mutate(root)
            code, _out, err = run(root)
            if code == 0:
                failures.append(f"反例「{name}」没被拦住（退出码 0）")
            elif expect not in err:
                failures.append(f"反例「{name}」拦住了，但报错里没有「{expect}」：\n{err}")
            else:
                print(f"ok  反例：{name}")

    # ── 作者归属（要 git 历史，单独建仓）──
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "repo"
        copy_repo(work)
        git = ["git", "-C", str(work)]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "config", "user.email", "t@example.com"], check=True)
        subprocess.run([*git, "config", "user.name", "t"], check=True)
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-qm", "base"], check=True)
        # 第二笔提交：改 FM-FONT-COUNT（属 anonymous-7f3a）的内容
        target = work / "plugins/FM-FONT-COUNT__anonymous-7f3a/plugin.json"
        m = json.loads(target.read_text(encoding="utf-8"))
        m["brief"] = m["brief"] + "（改）"
        target.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-qm", "edit"], check=True)

        for label, should_pass, author in author_cases():
            code, _out, err = run(work, "--author", author, "--base", "HEAD~1")
            passed = code == 0
            if passed != should_pass:
                failures.append(f"作者归属「{label}」：期望{'通过' if should_pass else '拦住'}，实际相反\n{err}")
            else:
                print(f"ok  作者归属：{label}")

    # ── 聚合透传（面板字段不许静默丢）+ 幂等 ──
    aggregate_ok = 0
    for label, mutate, check in aggregate_cases():
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_repo(Path(tmp) / "repo")
            patch_manifest(root, mutate)
            try:
                write_index(root)
            except RuntimeError as e:
                failures.append(f"聚合「{label}」：{e}")
                continue
            problem = check(entry_of(root, PID))
            if problem:
                failures.append(f"聚合「{label}」：{problem}")
            else:
                aggregate_ok += 1
                print(f"ok  聚合：{label}")

    # 同一份输入连跑两次：文件字节一致，--check 两次都报「最新」且输出相同（CI 不误报）
    with tempfile.TemporaryDirectory() as tmp:
        root = copy_repo(Path(tmp) / "repo")
        patch_manifest(root, with_run_fields)
        try:
            write_index(root)
            first = (root / "index.json").read_bytes()
            write_index(root)
            second = (root / "index.json").read_bytes()
        except RuntimeError as e:
            failures.append(f"聚合幂等：{e}")
        else:
            c1, o1, _e1 = run_aggregate(root, "--now", NOW, "--check")
            c2, o2, _e2 = run_aggregate(root, "--now", NOW, "--check")
            if first != second:
                failures.append("聚合幂等：连跑两次 index.json 字节不一致")
            elif c1 != 0 or c2 != 0:
                failures.append(f"聚合幂等：--check 退出码 {c1}/{c2}（写完后应当是最新的）")
            elif o1 != o2:
                failures.append(f"聚合幂等：两次 --check 输出不同\n第一次：{o1}\n第二次：{o2}")
            else:
                aggregate_ok += 1
                print(f"ok  聚合：--check 幂等（{o1.strip()}）")

    if failures:
        print("\n自测失败：", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(
        f"\n自测全部通过：1 个正例 + {len(CASES)} 个反例 + {len(author_cases())} 个归属用例"
        f" + {aggregate_ok} 个聚合用例"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
