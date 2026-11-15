#!/usr/bin/env python3
"""FontManager-Workshop registry · index.json 聚合。

`index.json` 是客户端**唯一**请求的文件（方案 §5），以前靠手写：新增一个插件就得
手抄 sha256 与体积，抄错一个字节 → 用户装不上（sha256 是硬门槛），而且没人会发现
错在哪。这里改成「从目录算出来」：

    plugins/<id>__<author>/plugin.json  ──┐
    official.json（官方区，手工维护）    ──┼──> index.json
    sha256 / 体积 / 直链（从磁盘算）      ──┘

用法：
  python .github/scripts/aggregate_index.py --root .
  python .github/scripts/aggregate_index.py --root . --check   # 只比对，不写（CI 用）

确定性：条目按 id 排序；`generatedAt` 取 `--now` 或 `SOURCE_DATE_EPOCH`，
都不给才用当前时间 —— 同样的输入重复跑，除 `generatedAt` 外输出逐字节一致。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_plugins as vp  # noqa: E402  同一份规则，不复制一遍

DEFAULT_REPO = "706972745/FontManager-Workshop"
DEFAULT_BRANCH = "main"


def raw_url(repo: str, branch: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"


def blob_sha256(root: Path, rel: str) -> str | None:
    """HEAD 里该文件的 blob sha256；未提交/不在 git 里返回 None。"""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "show", f"HEAD:{rel}"],
            capture_output=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return hashlib.sha256(out).hexdigest()


def eol_mismatch(root: Path, rel: str, work_sha: str) -> tuple[str, str] | None:
    """工作区字节被换行转换过吗？（返回 (工作区 sha, blob sha)）

    判据：文件在 git 里是**干净**的（没有未提交改动），但工作区 sha 与 blob sha
    不同 —— 那只可能是 checkout 时被改了换行。这种 sha 写进 index.json 就是错的：
    用户下到的是 blob 字节，拿它去比工作区算出的 sha 必然失败（表现为「装不上」）。
    """
    blob = blob_sha256(root, rel)
    if blob is None or blob == work_sha:
        return None
    clean = subprocess.run(
        ["git", "-C", str(root), "diff", "--quiet", "HEAD", "--", rel],
        capture_output=True,
    )
    return (work_sha, blob) if clean.returncode == 0 else None


def build_plugin_entry(root: Path, pdir: Path, repo: str, branch: str) -> dict:
    m = json.loads((pdir / "plugin.json").read_text(encoding="utf-8"))
    files = []
    total = 0
    for f in m["files"]:
        rel = f["path"]
        target = pdir / rel
        size = target.stat().st_size
        total += size
        sha = vp.sha256_of(target)
        repo_rel = f"plugins/{pdir.name}/{rel}"
        bad = eol_mismatch(root, repo_rel, sha)
        if bad is not None:
            raise SystemExit(
                f"{repo_rel} 的工作区字节与 git blob 不一致（工作区 {bad[0][:12]}… / "
                f"blob {bad[1][:12]}…）—— 换行被转换过，算出来的 sha256 会是错的。\n"
                f"修法：确认仓库根有 .gitattributes（`* -text`），然后 "
                f"`git rm -r --cached . -q && git reset --hard HEAD` 重新 checkout 一次。"
            )
        files.append({
            "path": rel,
            "sha256": sha,
            "url": raw_url(repo, branch, repo_rel),
            "size": size,
        })
    return {
        "id": m["id"],
        "name": m["name"],
        "brief": m["brief"],
        "detail": m["detail"],
        "author": m["author"],
        "version": m["version"],
        "permissions": list(m["permissions"]),
        "runtime": m.get("runtime"),
        "minAppVersion": m.get("minAppVersion"),
        "lang": m.get("lang"),
        "official": False,
        "uploadedAt": m.get("uploadedAt"),
        "files": files,
        "dir": f"plugins/{pdir.name}",
        "size": total,
    }


def build_index(root: Path, repo: str, branch: str, now: str) -> dict:
    official_path = root / "official.json"
    if official_path.is_file():
        official = json.loads(official_path.read_text(encoding="utf-8"))
    else:
        # 兼容：还没有 official.json 时沿用现有 index.json 的官方区（首跑不丢数据）
        old = root / "index.json"
        official = json.loads(old.read_text(encoding="utf-8")).get("official", []) if old.is_file() else []
    if not isinstance(official, list):
        raise SystemExit("official.json 顶层必须是数组")

    plugins = [
        build_plugin_entry(root, pdir, repo, branch)
        for pdir in sorted((root / "plugins").iterdir())
        if pdir.is_dir()
    ]
    plugins.sort(key=lambda e: e["id"])

    # 官方件与社区件 id 撞车 = 装的时候目录会打架，直接拒绝聚合
    ids = [e["id"] for e in official] + [e["id"] for e in plugins]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise SystemExit(f"id 重复（官方区与社区区不能同名）：{', '.join(dup)}")

    return {
        "version": 1,
        "generatedAt": now,
        "official": official,
        "plugins": plugins,
    }


def dump(index: dict) -> str:
    return json.dumps(index, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="聚合 registry 的 index.json")
    ap.add_argument("--root", default=".")
    ap.add_argument("--repo", default=os.environ.get("WORKSHOP_REPO", DEFAULT_REPO))
    ap.add_argument("--branch", default=os.environ.get("WORKSHOP_BRANCH", DEFAULT_BRANCH))
    ap.add_argument("--now", default="", help="ISO 时间；不给则用 SOURCE_DATE_EPOCH 或当前时间")
    ap.add_argument("--check", action="store_true", help="只比对，不写文件；不一致退出码 1")
    ap.add_argument("--skip-validate", action="store_true", help="跳过校验（不推荐）")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not (root / "plugins").is_dir():
        print("没有 plugins/ 目录", file=sys.stderr)
        return 1

    if not args.skip_validate:
        rep = vp.Report()
        for pdir in sorted(p for p in (root / "plugins").iterdir() if p.is_dir()):
            vp.validate_one(root, pdir, rep)
        if rep.errors:
            for e in rep.errors:
                print(f"ERROR {e}", file=sys.stderr)
            print("聚合中止：先修好校验错误（index.json 只描述通过校验的插件）", file=sys.stderr)
            return 1

    now = args.now
    if not now:
        epoch = os.environ.get("SOURCE_DATE_EPOCH")
        if epoch:
            now = datetime.fromtimestamp(int(epoch), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    index = build_index(root, args.repo, args.branch, now)
    text = dump(index)
    out = root / "index.json"

    if args.check:
        old = out.read_text(encoding="utf-8") if out.is_file() else ""
        if old != text:
            print("index.json 与目录内容不一致 —— 跑一次 aggregate_index.py 再提交", file=sys.stderr)
            return 1
        print("index.json 是最新的")
        return 0

    out.write_text(text, encoding="utf-8")
    print(
        f"已写入 {out}：官方 {len(index['official'])} 条，社区 {len(index['plugins'])} 条，"
        f"{len(text.encode('utf-8'))} 字节"
    )
    for e in index["plugins"]:
        print(f"  {e['id']:<20} {e['author']:<18} v{e['version']:<8} {len(e['files'])} 文件 {e['size']} 字节")
    return 0


if __name__ == "__main__":
    sys.exit(main())
