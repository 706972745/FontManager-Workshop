#!/usr/bin/env python3
"""FontManager-Workshop registry · 插件 PR 校验。

CI（.github/workflows/validate.yml）与本地自测跑的是**同一份**代码：
CI 里那点内联 python 没法在本地复现，改错了只能等推送后看红灯。

校验清单（方案 §2 / §3 / §6）：
  1. 清单字段齐全且合法（id / name / brief / detail / author / version /
     entry / apiLevel / files / permissions）
  2. 目录名必须等于 `<id>__<author>`（装到本机后目录名就是身份）
  3. entry 必须登记在 files 里，且文件真实存在（清单能解析 ≠ 插件能跑）
  4. 每个文件：路径安全、真实存在、是普通文件、后缀在白名单里
  5. 逐文件 sha256（清单里写了就必须对得上）
  6. 体积：单文件 ≤ 10MB，整包 ≤ 20MB
  7. 权限名必须在主程序 PERMS 白名单里（不在的会被运行时静默丢弃，
     等于用户看到的权限与实际签发的不一致）
  8. 作者归属：非维护者只能新增/修改/删除 `<id>__<自己登录名>` 的目录
  9. 目录里不许有未登记在 files 里的文件（面板的文件列表就是 files，
     藏文件等于骗审核）

用法：
  python .github/scripts/validate_plugins.py --root .
  python .github/scripts/validate_plugins.py --root . --author alice --base origin/main
  python .github/scripts/validate_plugins.py --root . --only plugins/foo__alice
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ── 常量（改这里 = 改 registry 规则）────────────────────────────────────

# 2026-11-25：id 放开到「小写字母 / 数字 / 点 / 短横线」，2~40 位，首尾必须是字母或数字。
# 原因：主程序里插件 id 一直用 Java 包名式写法（com.iieozo.adobe-font），
# registry 只认 a-z0-9- 会把这类插件全部挡在门外 —— 硬要改名等于换一个插件身份
# （安装目录名、配置、用户认知全变）。点号只允许出现在中间，`..`、首尾点一律拒。
ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,38}[a-z0-9])$")
AUTHOR_RE = re.compile(r"^(?:anonymous-[0-9a-z]{4,16}|[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38})$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PLUGIN_BYTES = 20 * 1024 * 1024
MAX_BRIEF = 200
MAX_DETAIL = 1000

# 与主程序 `src-tauri/src/api.rs` 的 `PERMS` **必须一致**。
# 两边不同步的后果：这里放过的权限名运行时会被 sanitize_plugin_perms 丢掉，
# 面板上写着「能改字体」实际签发出来没有 —— 用户看到的权限是假的。
PERMS = {
    "read:fonts",
    "write:fonts",
    "read:snapshot",
    "write:snapshot",
    "read:curation",
    "write:curation",
    "export",
    "import",
    "write:apply",
    "read:apps",
}

# 允许随包分发的文件类型：程序 / 清单 / 文档 / 面板资源。
#
# 2026-11-25 起**接收 .exe / .dll**（原规则是「只收脚本插件」）：
# 主程序本身早就支持 `runtime: "exe"` 的插件（`command_for` 直接起进程、stdio 走同一套
# 文本协议），只是 registry 一直把这条路堵着，导致原生语言写的插件只能私下发 zip。
# 放开后**不区分官方**：任何人都能提交 `.exe`，前提是清单里必须显式声明 entry、files 逐条登记，
# 审核就靠这份声明（目录里藏未登记的文件，第 9 条照旧拒）。
# 仍然拒收脚本宿主（bat/cmd/ps1/sh/vbs）与动态库以外的嵌入式格式：
# 那些只会被别的文件加载，允许了用户点开的其实是「看不见的脚本」，审核无从下手。
# 提交 .exe 的插件请在 detail 里写清可执行文件的作用，方便 AI 审核判断。
ALLOWED_EXT = {
    ".py", ".js", ".mjs", ".cjs", ".ts",
    ".json", ".jsonc", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".md", ".txt", ".csv", ".tsv",
    ".html", ".htm", ".css", ".svg",
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico",
    ".woff", ".woff2", ".ttf", ".otf",
    # 原生插件（runtime = "exe"）：主程序直接起进程，与 .py / .js 插件走同一套 stdio 协议
    ".exe", ".dll",
}

# 入口只认「宿主能直接执行」的后缀（与 `command_for` / `interpreter_kind` 对齐）：
# .py / .js 走解释器，.exe 是原生插件（runtime 留空或写 "exe" 都行）。
ENTRY_EXT = {".py", ".js", ".mjs", ".cjs", ".exe"}

REQUIRED_KEYS = (
    "id", "name", "brief", "detail", "author", "version",
    "entry", "apiLevel", "files", "permissions",
)


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.checked: list[str] = []

    def err(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"{where}: {msg}")

    def ok(self) -> bool:
        return not self.errors


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_rel_path(rel: str) -> bool:
    """与 Rust 侧 `safe_rel_path` 同口径：相对、无越界、无盘符、无反斜杠。"""
    if not rel or rel.startswith("/") or rel.startswith("\\"):
        return False
    if "\\" in rel or ":" in rel:
        return False
    parts = rel.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return False
    return True


def changed_plugin_dirs(root: Path, base: str) -> list[str] | None:
    """相对 base 改动到的 `plugins/<dir>` 列表；拿不到 diff 返回 None。

    `--no-renames` 是有意的：重命名会拆成「删旧 + 加新」，两个目录都要过归属校验，
    否则「把自己的目录 rename 成别人的目录」能绕过。
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "diff", "--name-only", "--no-renames", f"{base}...HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    dirs: list[str] = []
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("plugins/"):
            continue
        seg = line.split("/")
        if len(seg) < 3:
            continue  # plugins/ 根下的散文件：交给下面的目录扫描报错
        if seg[1] not in dirs:
            dirs.append(seg[1])
    return dirs


def validate_one(root: Path, pdir: Path, rep: Report) -> None:
    where = f"plugins/{pdir.name}"
    mf = pdir / "plugin.json"
    if not mf.is_file():
        rep.err(where, "缺少 plugin.json")
        return
    try:
        m = json.loads(mf.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        rep.err(where, f"plugin.json 不是合法 JSON：{e}")
        return
    if not isinstance(m, dict):
        rep.err(where, "plugin.json 顶层必须是对象")
        return

    # ── 1. 字段 ──
    missing = [k for k in REQUIRED_KEYS if k not in m]
    if missing:
        rep.err(where, f"清单缺字段：{', '.join(missing)}")
        return

    pid, author = m["id"], m["author"]
    if not isinstance(pid, str) or not ID_RE.match(pid):
        rep.err(where, f"id 不合法（小写字母/数字/点/短横线，2~40 位，首尾须为字母或数字）：{pid!r}")
    if not isinstance(author, str) or not AUTHOR_RE.match(author):
        rep.err(where, f"author 不合法（GitHub 登录名或 anonymous-xxxx）：{author!r}")
    if not isinstance(m["name"], str) or not m["name"].strip():
        rep.err(where, "name 不能为空")
    if not isinstance(m["brief"], str) or len(m["brief"]) > MAX_BRIEF:
        rep.err(where, f"brief 必须是 ≤{MAX_BRIEF} 字的字符串")
    if not isinstance(m["detail"], str) or len(m["detail"]) > MAX_DETAIL:
        rep.err(where, f"detail 必须是 ≤{MAX_DETAIL} 字的字符串")
    if not isinstance(m["version"], str) or not SEMVER_RE.match(m["version"]):
        rep.err(where, f"version 必须是 semver：{m['version']!r}")
    if m.get("official") is True:
        rep.err(where, "社区插件不许声明 official=true（官方区数据来自官方仓）")
    api_level = m["apiLevel"]
    if not isinstance(api_level, int) or isinstance(api_level, bool) or api_level < 1:
        rep.err(where, f"apiLevel 必须是 ≥1 的整数：{api_level!r}")
    elif api_level > 1:
        rep.warn(where, f"apiLevel={api_level} 高于当前主程序支持的 1，安装时会被拒")

    # ── 2. 目录名 = <id>__<author> ──
    expect = f"{pid}__{author}"
    if pdir.name != expect:
        rep.err(where, f"目录名必须等于 <id>__<author>（应为 {expect}）")

    # ── 3/4/5/6. 文件 ──
    files = m["files"]
    if not isinstance(files, list) or not files:
        rep.err(where, "files 必须是非空数组")
        return
    listed: list[str] = []
    total = 0
    for i, f in enumerate(files):
        if not isinstance(f, dict) or "path" not in f:
            rep.err(where, f"files[{i}] 必须是含 path 的对象")
            continue
        rel = f["path"]
        if not isinstance(rel, str) or not safe_rel_path(rel):
            rep.err(where, f"files[{i}] 路径不安全：{rel!r}")
            continue
        if rel in listed:
            rep.err(where, f"files 里重复登记：{rel}")
            continue
        listed.append(rel)
        target = pdir / rel
        if not target.is_file():
            rep.err(where, f"files 里登记了 {rel}，但文件不存在")
            continue
        if target.is_symlink():
            rep.err(where, f"{rel} 是符号链接，registry 不收")
            continue
        ext = target.suffix.lower()
        if ext not in ALLOWED_EXT:
            rep.err(where, f"{rel} 的类型 {ext or '(无后缀)'} 不在白名单里")
        size = target.stat().st_size
        total += size
        if size > MAX_FILE_BYTES:
            rep.err(where, f"{rel} 单文件 {size} 字节，超过 {MAX_FILE_BYTES}")
        want = f.get("sha256")
        if want:
            if not isinstance(want, str) or not re.fullmatch(r"[0-9a-f]{64}", want):
                rep.err(where, f"{rel} 的 sha256 必须是 64 位小写十六进制")
            elif sha256_of(target) != want:
                rep.err(where, f"{rel} 的 sha256 与清单不符（文件被改过？）")

    # ── 3. entry ──
    entry = m["entry"]
    if not isinstance(entry, str) or not safe_rel_path(entry):
        rep.err(where, f"entry 路径不安全：{entry!r}")
    else:
        if entry not in listed:
            rep.err(where, f"entry「{entry}」没有登记在 files 里")
        if Path(entry).suffix.lower() not in ENTRY_EXT:
            rep.err(where, f"entry「{entry}」后缀必须是 .py / .js / .exe（宿主按后缀决定用解释器还是直接执行）")
        if not (pdir / entry).is_file():
            rep.err(where, f"entry「{entry}」文件不存在")

    if total > MAX_PLUGIN_BYTES:
        rep.err(where, f"整包 {total} 字节，超过 {MAX_PLUGIN_BYTES}（20MB）")

    # ── 7. 权限 ──
    perms = m["permissions"]
    if not isinstance(perms, list) or not all(isinstance(p, str) for p in perms):
        rep.err(where, "permissions 必须是字符串数组")
    else:
        bad = [p for p in perms if p not in PERMS]
        if bad:
            rep.err(
                where,
                "权限名不在白名单里："
                + ", ".join(bad)
                + "（可用：" + ", ".join(sorted(PERMS)) + "）",
            )
        if len(set(perms)) != len(perms):
            rep.warn(where, "permissions 有重复项")

    # ── 9. 未登记文件 ──
    on_disk = {
        p.relative_to(pdir).as_posix()
        for p in pdir.rglob("*")
        if p.is_file() and not any(part.startswith(".") for part in p.relative_to(pdir).parts)
    }
    unlisted = sorted(on_disk - set(listed))
    if unlisted:
        rep.err(where, "目录里有未登记在 files 里的文件：" + ", ".join(unlisted))

    rep.checked.append(f"{expect} ({total} 字节, {len(listed)} 个文件)")


def main() -> int:
    ap = argparse.ArgumentParser(description="校验 registry 里的插件目录")
    ap.add_argument("--root", default=".", help="registry 仓库根目录")
    ap.add_argument("--author", default="", help="PR 作者登录名（作者归属校验用）")
    ap.add_argument("--base", default="", help="对比的基线 ref，如 origin/main")
    ap.add_argument("--maintainers", default=os.environ.get("WORKSHOP_MAINTAINERS", "706972745"))
    ap.add_argument("--only", default="", help="只校验某个目录（本地调试用）")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    plugins_root = root / "plugins"
    if not plugins_root.is_dir():
        print("没有 plugins/ 目录", file=sys.stderr)
        return 1

    rep = Report()
    dirs = sorted(p for p in plugins_root.iterdir() if p.is_dir())
    if args.only:
        target = (root / args.only).resolve()
        dirs = [p for p in dirs if p.resolve() == target]
        if not dirs:
            print(f"--only 没匹配到目录：{args.only}", file=sys.stderr)
            return 1

    for pdir in dirs:
        validate_one(root, pdir, rep)

    # ── 8. 作者归属 ──
    if args.base and args.author:
        maintainers = {x.strip().lower() for x in args.maintainers.split(",") if x.strip()}
        if args.author.lower() not in maintainers:
            touched = changed_plugin_dirs(root, args.base)
            if touched is None:
                rep.err("author", f"拿不到与 {args.base} 的 diff，无法校验作者归属")
            else:
                own = f"__{args.author}".lower()
                for d in touched:
                    if d.lower().endswith(own):
                        continue
                    rep.err(
                        f"plugins/{d}",
                        f"@{args.author} 不能改别人的插件目录（只有维护者可以；"
                        f"自己的目录名必须以 {own} 结尾）",
                    )
    elif args.base and not args.author:
        rep.warn("author", "传了 --base 但没传 --author，跳过作者归属校验")

    for w in rep.warnings:
        print(f"WARN  {w}")
    for e in rep.errors:
        print(f"ERROR {e}", file=sys.stderr)
    if rep.errors:
        print(f"\n校验失败：{len(rep.errors)} 个问题", file=sys.stderr)
        return 1
    print(f"校验通过：{len(rep.checked)} 个插件")
    for line in rep.checked:
        print(f"  ok  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
