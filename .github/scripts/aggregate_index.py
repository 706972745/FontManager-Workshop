#!/usr/bin/env python3
"""插件库 registry · 清单聚合（FontManager / AssetManager 共用）。

两类产物，结构完全一致（`version` / `generatedAt` / `official` / `plugins`）：

    index.json        全量（跨软件）：给维护者看，也兼容只认全量清单的旧客户端
    by-app/fm.json    只含 FM-* 条目 —— FontManager 客户端唯一请求的文件
    by-app/am.json    只含 AM-* 条目 —— AssetManager 客户端唯一请求的文件

以前 `index.json` 靠手写：新增一个插件就得手抄 sha256 与体积，抄错一个字节 →
用户装不上（sha256 是硬门槛），而且没人会发现错在哪。这里改成「从目录算出来」：

    plugins/<id>__<author>/plugin.json  ──┐
    official.json（官方区，手工维护）    ──┼──> index.json + by-app/<前缀>.json
    sha256 / 体积 / 直链（从磁盘算）      ──┘

某个前缀一条都没有时**也要写**该切片（空数组）：客户端固定请求这个路径，
文件不存在就是 404，插件中心直接空着。

用法：
  python .github/scripts/aggregate_index.py --root .
  python .github/scripts/aggregate_index.py --root . --check   # 只比对，不写（CI 用）

`--check` 会把 index.json 与每份 by-app/*.json 都比一遍 —— 只比 index.json 的话，
改了插件但切片没更新时脚本会误报「是最新的」。

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
import app_prefixes as ap  # noqa: E402  前缀表只此一份
import validate_plugins as vp  # noqa: E402  同一份规则，不复制一遍

DEFAULT_REPO = "706972745/Manager-Workshop"
DEFAULT_BRANCH = "main"
SLICE_DIR = "by-app"

# 上传面板（1.4.1 起）会把运行字段写进 plugin.json，而聚合只搬下面那份固定字段表，
# 结果这些字段在 index.json 里静默消失 —— 客户端拿到的清单比作者提交的少信息。
# 只透传这张表里的键（不是原样搬运整个 plugin.json）：plugin.json 里塞的任意垃圾
# 键仍然不许进公开清单。顺序固定，保证同一输入逐字节一致。
PASSTHROUGH_KEYS = (
    "entry", "apiLevel", "hooks", "menus",
    "settings", "summary", "description", "requirements",
)


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


def has_value(v) -> bool:
    """作者到底填了没有？null / [] / {} / "" 都算没填 —— 写进清单只是噪声。"""
    if v is None:
        return False
    if isinstance(v, (str, list, dict)) and not v:
        return False
    return True


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
    entry = {
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
    }
    # 运行字段按 PASSTHROUGH_KEYS 的固定顺序插在 lang 之后、official 之前：
    # 位置固定 ⇒ 同一份 plugin.json 反复跑出来的字节完全一致（CI 才不会误判「清单变了」）。
    for key in PASSTHROUGH_KEYS:
        if has_value(m.get(key)):
            entry[key] = m[key]
    entry.update({
        "official": False,
        "uploadedAt": m.get("uploadedAt"),
        "files": files,
        "dir": f"plugins/{pdir.name}",
        "size": total,
    })
    return entry


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

    # 官方件同样受前缀闸门约束。前缀不在表里的条目**永远进不了任何切片** ——
    # 客户端根本看不到它。与其静默吞掉，不如聚合时直接报错。
    bad = sorted(e["id"] for e in official if not ap.is_valid_id(e["id"]))
    if bad:
        raise SystemExit(
            f"官方件 id 不合规（前缀必须是 {ap.prefixes_hint()}，"
            f"整串 ≤ {ap.MAX_ID_LEN} 字符）：{', '.join(bad)}"
        )

    return {
        "version": 1,
        "generatedAt": now,
        "official": official,
        "plugins": plugins,
    }


def slice_index(index: dict, prefix: str) -> dict:
    """按 id 前缀切一份清单，结构与 index.json 完全一致。"""
    def keep(entry: dict) -> bool:
        return ap.prefix_of(entry.get("id")) == prefix

    return {
        "version": index["version"],
        "generatedAt": index["generatedAt"],
        "official": [e for e in index["official"] if keep(e)],
        "plugins": [e for e in index["plugins"] if keep(e)],
    }


def outputs(root: Path, index: dict) -> list[tuple[Path, dict]]:
    """全量 + 每个前缀一份切片（某前缀没条目时仍然写空数组）。"""
    out = [(root / "index.json", index)]
    for prefix in ap.APP_PREFIXES:
        out.append((root / SLICE_DIR / f"{prefix.lower()}.json", slice_index(index, prefix)))
    return out


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
    planned = outputs(root, index)

    def same_file(path: Path, obj: dict) -> bool:
        """内容是否一致 —— 不比 generatedAt：时间戳每次跑都不同，拿它比等于永远不一致。"""
        if not path.is_file():
            return False
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False
        if not isinstance(old, dict):
            return False
        old["generatedAt"] = obj["generatedAt"]
        return dump(old) == dump(obj)

    if args.check:
        stale = [p for p, obj in planned if not same_file(p, obj)]
        if stale:
            names = "、".join(p.relative_to(root).as_posix() for p in stale)
            print(f"{names} 与目录内容不一致 —— 跑一次 aggregate_index.py 再提交", file=sys.stderr)
            return 1
        print("index.json 与 by-app/*.json 都是最新的")
        return 0

    written = 0
    for path, obj in planned:
        data = dump(obj).encode("utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        # write_bytes 而不是 write_text：Windows 上文本模式会把 \n 翻成 \r\n，
        # 同一份输入在 CI(Linux) 与本地产出的字节就不同，aggregate.yml 会一直以为清单变了。
        path.write_bytes(data)
        written += len(data)

    print(
        f"已写入 index.json + {len(planned) - 1} 份切片：官方 {len(index['official'])} 条，"
        f"社区 {len(index['plugins'])} 条，共 {written} 字节"
    )
    for path, obj in planned[1:]:
        print(
            f"  {path.relative_to(root).as_posix()}: 官方 {len(obj['official'])} 条，"
            f"社区 {len(obj['plugins'])} 条"
        )
    for e in index["plugins"]:
        print(f"  {e['id']:<20} {e['author']:<18} v{e['version']:<8} {len(e['files'])} 文件 {e['size']} 字节")
    return 0


if __name__ == "__main__":
    sys.exit(main())
