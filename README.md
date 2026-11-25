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
| name | 显示名，**最多 15 个字**（按字符数，中文/emoji 一个字一个）。卡片一行放不下更长的；面板上传前就拦住，这里兜住手搓的 PR |
| id | 小写字母 / 数字 / `.` / `-`，2~40 位，首尾须为字母或数字（`com.iieozo.adobe-font` 这类包名式 id 合法） |
| 目录名 | 必须等于 `<id>__<author>` |
| entry | 必须登记在 `files` 里、文件真实存在、后缀 `.py` / `.js` / `.exe`（`.py`/`.js` 走解释器，`.exe` 是原生插件） |
| 文件 | 相对路径、无 `..` / 盘符 / 反斜杠；必须是普通文件；后缀在白名单里（2026-11-25 起含 `.exe` / `.dll`，不区分官方与社区） |
| 体积 | 单文件 ≤ 10MB，整包 ≤ 20MB |
| 权限 | 必须在主程序 `src-tauri/src/api.rs` 的 `PERMS` 里（`read:fonts` / `write:fonts` / …） |
| 未登记文件 | 目录里不许有 `files` 之外的文件（面板的文件列表就是 `files`） |
| 作者归属 | 非维护者只能新增/修改/删除 `<id>__<自己登录名>` 的目录 |

`PERMS` 与主程序是**两份拷贝**，改一边必须改另一边（`validate_plugins.py` 顶部有常量）。

## 上传与下架（真实链路）

作者都在主程序「插件中心」里操作，这里只记录仓库侧发生了什么。

### 上传 = 一个 PR，需要维护者合并

面板 → 上传插件 → 选文件夹 / zip → 核对清单 → 提交。面板在自己的 fork 上建一个提交，
向上游开 **一个 PR**（多个插件共用同一个 PR 与提交），CI 跑 `validate_plugins.py`：

- 通过 → 等维护者点合并
- 不通过 → PR 上直接红，按报错改完再推

合并到 `main` 后 `aggregate.yml` 重算 `index.json`（通常几十秒到两分钟），面板刷新才看得到。

> 为什么保留人工合并：包里可以带 `.exe`，CI 只能校验规则、不能判断行为。合并是唯一的人工闸门。

### 下架 = 一条 `[takedown]` 请求，自动执行

作者在面板「我上传的插件」里点「下架」，面板向本仓提交一条 issue，标题形如：

```
[takedown] plugins/<id>__<author>
```

`takedown.yml` 用 `AGGREGATE_PAT` 直接改 `main`，**不需要维护者点合并、也不需要给作者任何写权限**。
四道闸，缺一条就评论原因并关闭、什么都不删：

1. issue 作者 == 目录名后缀（**忽略大小写**）
2. issue 里点名的路径都在 `plugins/<id>__<作者>` 这一层，不许带别的目录
3. 目录真实存在（防空请求）
4. 只做删除，不夹带新增/修改

面板侧：提交成功即在本地从中心隐藏，并用「目录级探测」（`plugins/<dir>/plugin.json` 是否 404）
确认真的删掉了；3 分钟还没删成会把条目放回来，不会出现「说没了其实还在」。

## 面板（workshop-panel）的分发

面板是**独立产物**，不跟着主程序发版：

- 打包：主程序仓库 `node tools/build-workshop-panel.mjs` → `workshop-panel.zip`（只含面板用到的 chunk）
- 上传：本仓 **release `v1`** 的资产 `workshop-panel.zip`（`--clobber` 覆盖）
- 元数据：仓库根 `panel-meta.json`（`version` / `sha256` / `size`）→ `sync-panel-meta.yml`
  校验 zip 的 sha256 与 meta 一致后，把 meta 也上传成 v1 资产
- 客户端读的是 **release 资产** `releases/download/v1/panel-meta.json`（不走 raw：raw 前面有 CDN，
  发布当天会出现「新 zip 配旧 meta」，sha256 硬门槛直接拒装）

顺序不能反：**先传 zip，再改 meta**。反过来 CI 会因为 sha 对不上而失败（这是故意的）。

## 两条容易踩的坑

1. **换行转换**：仓库根有 `.gitattributes`（`* -text`）。sha256 比的是用户下载到的
   原始字节，Windows 上 `core.autocrlf=true` 会把工作区文件转成 CRLF，本地算出的
   sha256 就跟线上对不上 —— CI 在 Linux 上看不出来，用户装的时候才报「装不上」。
   老克隆如果出现「工作区与 blob 不一致」，`git rm -r --cached . -q && git reset --hard HEAD`。
2. **分支保护与自动提交**：`aggregate.yml` 要往 main 推提交。main 开了 require review
   时，需在规则里给 `github-actions[bot]` 加 bypass，否则该 job 403 失败（表现为
   「插件已合并，中心里看不到」）。

## workflows 一览

| 文件 | 触发 | 做什么 |
|---|---|---|
| `validate.yml` | PR | 跑 `validate_plugins.py`（+ 归属校验，非维护者只能动自己的目录） |
| `aggregate.yml` | push `main` | 重算 `index.json` 并提交 |
| `takedown.yml` | issue `opened`（兼容旧的 `[remove]` PR） | 校验「发起人 == 目录作者」后直接删除并关闭 issue |
| `sync-panel-meta.yml` | push 改 `panel-meta.json` | 校验 zip sha 后把 meta 同步成 release v1 资产 |
