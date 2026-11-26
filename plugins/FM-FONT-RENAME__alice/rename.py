# -*- coding: utf-8 -*-
"""批量重命名 —— 插件中心上的社区示例插件。

主程序拉起插件后，会在 stdin 送一行 JSON（握手）：

    {"type": "init", "pluginId": "FM-FONT-RENAME", "apiLevel": 1,
     "apiBase": "http://127.0.0.1:<port>/api/v1", "apiToken": "<token>"}

协议是「stdin/stdout 逐行 JSON」：主程序发 invoke，插件回 log / toast / hint。
这个示例只实现握手回执 —— 让主程序的插件日志里能看见「插件已启动」，
真正的批量重命名逻辑等维护者上架正式版本。
"""

import json
import sys


def reply(obj):
    """往 stdout 写一行 JSON 并立刻冲刷（主程序是逐行读的，不冲刷它会一直等）。"""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except ValueError:
            continue
        kind = msg.get("type")
        if kind == "init":
            reply({
                "type": "log",
                "message": "批量重命名（示例）已启动 · 插件 ID %s · API 级别 %s"
                           % (msg.get("pluginId"), msg.get("apiLevel")),
            })
        elif kind == "invoke":
            reply({
                "type": "log",
                "message": "收到调用：%s（示例插件不做实际改动）" % (msg.get("hook"),),
            })


if __name__ == "__main__":
    main()
