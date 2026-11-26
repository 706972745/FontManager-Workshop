#!/usr/bin/env python3
"""插件 ID 的前缀表 —— 唯一的「哪个前缀属于哪个软件」的出处。

FontManager 与 AssetManager 共用同一个插件库，靠 ID 前缀区分归属：
`FM-XXX-XXX` 是 FontManager 的，`AM-XXX-XXX` 是 AssetManager 的。

`validate_plugins.py`（闸门）、`aggregate_index.py`（清单切片）都 import 这张表。
**加软件 / 改前缀只改这里**，两边自动同口径 —— 以前一个写在正则里、一个写在注释里，
迟早会有一边漏改。

ID 规则（与主仓 `docs/多软件共用插件库.md` 一致）：
  - 前缀必须大写，且必须是下表里的键；
  - 后面两段各自是任意长度的字母或数字（大小写随意）；
  - 整串 ≤ 40 字符。
"""
from __future__ import annotations

import re

# 前缀 → 软件显示名。键必须大写。
APP_PREFIXES = {
    "FM": "FontManager",
    "AM": "AssetManager",
}

# 整串长度上限（不是每段的上限）：`FM-FONT-RENAME` 这种清晰可读的 id 有空间，
# 又不至于长到面板卡片放不下、安装目录名超 Windows 路径限制。
MAX_ID_LEN = 40

# 联合闸门：`^(FM|AM)-[A-Za-z0-9]+-[A-Za-z0-9]+$`。
# 前缀部分由 APP_PREFIXES 生成，不写死 —— 加软件时只改上面那张表。
ID_RE = re.compile(
    r"^(?:" + "|".join(re.escape(p) for p in APP_PREFIXES) + r")-[A-Za-z0-9]+-[A-Za-z0-9]+$"
)


def prefix_of(pid: str) -> str | None:
    """取 id 的前缀（`FM` / `AM`）；不在表里、或形状不对都返回 None。

    长度检查放在这里而不是正则里：正则里的长度上限写一次就很难再改对，
    而且 `ID_RE.match` 之外的地方容易忘了它。
    """
    if not isinstance(pid, str) or len(pid) > MAX_ID_LEN:
        return None
    m = ID_RE.match(pid)
    return m.group(0).split("-", 1)[0] if m else None


def is_valid_id(pid: str) -> bool:
    return prefix_of(pid) is not None


def prefixes_hint() -> str:
    """报错文案用：`FM（FontManager）/ AM（AssetManager）`。"""
    return " / ".join(f"{p}（{name}）" for p, name in APP_PREFIXES.items())
