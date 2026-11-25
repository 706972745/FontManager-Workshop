# FontManager Workshop

FontManager 插件中心 registry。插件经 PR 审核合并后上架；浏览与下载免登录。

- `index.json` —— 聚合的卡片数据（含官方区），客户端唯一请求。**不要手改**，由脚本生成
- `official.json` —— 官方区条目（手工维护：官方插件在 `FontManager-Plugin` 仓发版时更新这里）
- `plugins/<id>__<author>/` —— 每个插件一个文件夹，`plugin.json` + 本体文件
- 上传请使用 FontManager 主程序的「插件中心」上传流程

## index.json 是算出来的，不是手写的

```bash
python .github/scripts/aggregate_index.py --root .
```

脚本扫 `plugins/*/plugin.json`，逐文件算 sha256 与体积、拼出 raw 直链，再合并
`official.json` 的官方区，按 id 排序写出 `index.json`。合并到 main 后
`.github/workflows/aggregate.yml` 会自动跑一遍并提交结果，**上传者不需要碰 index.json**。

手写的 sha256 抄错一个字节，用户就会卡在「sha256 校验失败」，而且从报错里看不出错在哪。

## 校验规则（PR 必过）

```bash
python .github/scripts/validate_plugins.py --root .            # 全部
python .github/scripts/validate_plugins.py --root . --author <登录名> --base origin/main
python .github/scripts/selftest.py                             # 规则自测（正例 + 反例）
```

| 项 | 规则 |
|---|---|
| 清单字段 | `id` / `name` / `brief` / `detail` / `author` / `version` / `entry` / `apiLevel` / `files` / `permissions` 必填 |
| id | 小写字母 / 数字 / `.` / `-`，2~40 位，首尾须为字母或数字（`com.iieozo.adobe-font` 这类包名式 id 合法） |
| 目录名 | 必须等于 `<id>__<author>` |
| entry | 必须登记在 `files` 里、文件真实存在、后缀 `.py` / `.js` / `.exe`（`.py`/`.js` 走解释器，`.exe` 是原生插件） |
| 文件 | 相对路径、无 `..` / 盘符 / 反斜杠；必须是普通文件；后缀在白名单里（2026-11-25 起含 `.exe` / `.dll`，不区分官方与社区） |
| 体积 | 单文件 ≤ 10MB，整包 ≤ 20MB |
| 权限 | 必须在主程序 `src-tauri/src/api.rs` 的 `PERMS` 里（`read:fonts` / `write:fonts` / …） |
| 未登记文件 | 目录里不许有 `files` 之外的文件（面板的文件列表就是 `files`） |
| 作者归属 | 非维护者只能新增/修改/删除 `<id>__<自己登录名>` 的目录 |

`PERMS` 与主程序是**两份拷贝**，改一边必须改另一边（`validate_plugins.py` 顶部有常量）。

## 两条容易踩的坑

1. **换行转换**：仓库根有 `.gitattributes`（`* -text`）。sha256 比的是用户下载到的
   原始字节，Windows 上 `core.autocrlf=true` 会把工作区文件转成 CRLF，本地算出的
   sha256 就跟线上对不上 —— CI 在 Linux 上看不出来，用户装的时候才报「装不上」。
   老克隆如果出现「工作区与 blob 不一致」，`git rm -r --cached . -q && git reset --hard HEAD`。
2. **分支保护与自动提交**：`aggregate.yml` 要往 main 推提交。main 开了 require review
   时，需在规则里给 `github-actions[bot]` 加 bypass，否则该 job 403 失败（表现为
   「插件已合并，中心里看不到」）。
