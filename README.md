# Manager Workshop — FontManager / AssetManager 共用插件库

FontManager 与 AssetManager 共用**同一个**插件库：官方件与社区件都在这里登记，
靠**插件 ID 前缀**区分归属。插件经 PR 审核合并后上架；浏览与下载免登录。

- `by-app/fm.json` —— FontManager 的清单切片（只含 `FM-*`），**FontManager 客户端唯一请求的文件**
- `by-app/am.json` —— AssetManager 的清单切片（只含 `AM-*`）
- `index.json` —— 全量清单（跨软件，给维护者看 / 兼容只认全量的旧客户端）。**不要手改**，由脚本生成
- `official.json` —— 官方区条目（手工维护：官方插件在 `Manager-Plugin` 仓发版时更新这里）
- `plugins/<id>__<author>/` —— 每个社区插件一个文件夹，`plugin.json` + 本体文件
- `panel-fm-meta.json` —— FontManager 面板产物的元数据（`version` / `sha256` / `size`），与 release 资产保持同内容
- 上传请使用主程序「插件中心」的上传流程

## 收录规则：ID 必须带软件前缀

前缀是**软件的编号**，不是可选写法：

| 前缀 | 软件 | 清单切片 |
|---|---|---|
| `FM` | FontManager | `by-app/fm.json` |
| `AM` | AssetManager | `by-app/am.json` |

- 前缀必须**大写**（`fm-…` 与 `FM-…` 是两回事，不混着收）；
- 后面两段各自是任意长度的字母或数字（大小写随意），整串 **≤ 40 字符**；
- 联合闸门：`^(FM|AM)-[A-Za-z0-9]+-[A-Za-z0-9]+$`（`app_prefixes.py` 是前缀表的唯一出处，
  registry 校验与聚合切片都 import 它；加软件只改那张表）。
- 官方件同样受这条规则约束 —— 不因为「官方」就放行别的命名。

**官方件放 `Manager-Plugin` 仓**（源码 + release 里的 `<ID>.zip`），**社区件放本仓**
（`plugins/<id>__<author>/`）。上传时 ID 不合规会在本地就被拦下。

## 清单是算出来的，不是手写的

```bash
python .github/scripts/aggregate_index.py --root .
```

脚本扫 `plugins/*/plugin.json`，逐文件算 sha256 与体积、拼出 raw 直链，再合并
`official.json` 的官方区，按 id 排序写出全量 `index.json`，并按前缀切出
`by-app/fm.json` / `by-app/am.json`（结构与 `index.json` 完全一致）。

- 某前缀一条都没有时**也会写**该切片（空数组）：客户端固定请求这个路径，文件不存在就是 404。
- 客户端只拉自己那份切片，别的软件的条目、命名不合规的条目**根本不会进内存**。

合并到 main 后 `.github/workflows/aggregate.yml` 会自动跑一遍并提交结果，
**上传者不需要碰 index.json / by-app**。

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
| name | 显示名，**最多 25 个字**（按字符数，中文/emoji 一个字一个）。卡片一行放不下更长的；面板上传前就拦住，这里兜住手搓的 PR |
| id | 必须是 `<前缀>-XXX-XXX`：前缀为 `FM`（FontManager）/ `AM`（AssetManager）之一且**大写**，两段各自是字母或数字，整串 ≤ 40 字符（旧式 `com.xxx.yyy` 包名已不再接收） |
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

合并到 `main` 后 `aggregate.yml` 重算 `index.json` 与 `by-app/*.json`（通常几十秒到两分钟），
面板刷新才看得到。

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

## 面板（panel-fm）的分发

面板是**独立产物**，不跟着主程序发版，且**按软件分开命名**（两个软件的面板互不覆盖）：

- 打包：主程序仓库 `node tools/build-workshop-panel.mjs` → `panel-fm.zip`（只含面板用到的 chunk）
- 上传：本仓 **release `v1`** 的资产 `panel-fm.zip`（`--clobber` 覆盖）
- 元数据：仓库根 `panel-fm-meta.json`（`version` / `sha256` / `size`）→ `sync-panel-meta.yml`
  校验 zip 的 sha256 与 meta 一致后，把 meta 也上传成 v1 资产 `panel-fm-meta.json`
- 客户端读的是 **release 资产** `releases/download/v1/panel-fm-meta.json`（不走 raw：raw 前面有 CDN，
  发布当天会出现「新 zip 配旧 meta」，sha256 硬门槛直接拒装）
- AssetManager 将来直接加 `panel-am.zip` / `panel-am-meta.json`，同上流程，互不影响

顺序不能反：**先传 zip，再改 meta**。反过来（或 release 里还没有 `panel-fm.zip`）CI 会因为
sha 对不上而失败 —— 这是故意的，宁可不发，也不要发一份 meta 与 zip 不配套的面板。

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
| `aggregate.yml` | push `main` | 重算 `index.json` 与 `by-app/*.json` 并提交 |
| `takedown.yml` | issue `opened`（兼容旧的 `[remove]` PR） | 校验「发起人 == 目录作者」后直接删除并关闭 issue |
| `sync-panel-meta.yml` | push 改 `panel-fm-meta.json` | 校验 zip sha 后把 meta 同步成 release v1 资产 |
