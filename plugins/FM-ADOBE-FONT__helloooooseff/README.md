# Adobe 套字器（FontManager 插件 · 0.4.0 · `FM-ADOBE-FONT`）

**一个插件就够了**：双击套字、右键套字、设置面板、AE / PR 桥接面板都在这一个包里。
不用再装官方件 `FM-FONT-APPLY`（PS / AI / CDR 版），也不需要 Python / Node 运行时。

把字体应用到 Adobe 系列应用**当前选中的文字**上。同一套指令，按应用能力自动选通道。

## 目录结构（一个插件一个目录，源码 / 产物 / 文档 / 测试分开）

```
FM-ADOBE-FONT/
├── plugin.json           清单（打包必需，留在根目录）
├── README.md             本说明（同时进安装包）
├── src/                  源码与构建
│   ├── adobe-apply.ps1   套字主体
│   ├── install-cep.ps1   CEP 面板安装
│   ├── cep/              AE / PR 面板
│   ├── rust/             插件协议层（cargo 工程）
│   ├── probe_ae*.jsx     排查探针
│   └── tools/package.py  出包（自检 + 安装包 + 源码包）
├── dist/                 产物：*.zip / adobe font/FM-ADOBE-FONT/
├── docs/                 规则对照、测试方案与报告
└── tests/                测试脚本；reports/ 下放实测记录
```

后续新插件按同样布局另建 `FontManager-plugin/FM-XXX-XXX/`，互不干扰。

## 0.4.0：多软件同开时「自动」永远套到 Illustrator（真机 Z 序实锤）

**症状**：PS / AI / ID / CDR 同时开着，切到 InDesign 的窗口操作，再回 FontManager 双击字体，
字体永远进 Illustrator；提示还写着「已应用到 Illustrator」。点 ID 的窗口让它成为前台再回来，照样进 AI。
看起来就是「这个插件只认 AI」。

**根因**（本机真实 Z 序，AI + ID + PS 同开时采样）：

```
 Z  进程           可见   owner   标题
 0  FontManager    是     0       FontManager          ← 双击发生在这里
 1  Illustrator    否     0       Title                ← 隐藏窗口，无 owner，压在所有人上面
 2  Illustrator    否     0       Title
 3  Illustrator    否     0       OS_PopupWindow
 ...
107 InDesign       是     0       *未命名-1 @ 91%       ← 用户真正在用的
171 Illustrator    是     0       未标题-1* @ 200%
200 Photoshop      是     0       未标题-1 @ 66.7%
```

Illustrator 常驻十来个**不可见的顶层窗口**（`Title` / `OS_ViewContainer` / `wglDummyWindowFodder` /
`NVOGLDC invisible`），全部无 owner。0.3.9 的 Z 序扫描只判「无 owner」，完全不看可见性，
于是**永远命中排在最上面的那个看不见的 AI 窗口** —— 与用户实际操作无关，所以是「永远」而不是「偶尔」。

**改法**（`src/rust/src/main.rs`）：

1. Z 序扫描加「真的在用」过滤：`IsWindowVisible` + `!IsIconic` + `DwmGetWindowAttribute(DWMWA_CLOAKED)==0`
   + 无 owner（`GW_OWNER` 为空，排除浮动面板 / 对话框）。便宜的判断先做，通过了才 `OpenProcess` 取进程名。
2. 判定顺序改为以**实时证据**为主：① 前台就是设计软件 → 用它；② Z 序最上层「在用的」设计软件；
   ③ 前台事件钩子记下的「最近用过」；④ 主程序 `/apps/active`。原来 ② 排在 ③ 后面，
   一旦钩子没投递事件（受限桌面实测会出现），就只能落到 ② 并踩上面那个坑。
3. 日志写清依据和窗口标题，例如 `自动目标：InDesign（Z 序最上层在用的窗口：*未命名-1 @ 91%）`。

**实测对照**（`tests/diag_zorder.py`，依次把软件切前台再切回 FontManager 采样）：

| 刚用过 | 0.3.9 判定 | 0.4.0 判定 |
|---|---|---|
| InDesign | Illustrator ❌（Z1 隐藏窗口） | **InDesign** ✅ |
| Illustrator | Illustrator ✅ | Illustrator ✅ |
| Photoshop | Illustrator ❌ | **Photoshop** ✅ |

端到端（双击「自动」，ID 在前台过）：`自动目标：InDesign（Z 序最上层在用的窗口：*未命名-1 @ 91%）`
→ `已应用「SimHei Normal」到 InDesign（1 个图层/文本框）`。

---

## 0.3.8 / 0.3.7：双击「自动」到底套哪个软件（终于定下来了）

**问题链条**：双击发生在 FontManager 自己的窗口里，那一刻前台永远是 `fontmanager.exe`，插件只能"猜"目标。
- 0.3.4 之前：猜 Z 序最上层的设计软件 → 用户明明在 ID 里，字体跑到后台的 AI 上（AI 又慢又「新建文字」），看起来就是「ID 用不了」。
- 0.3.6 的错误尝试：把「上次套成功的软件」当粘性记忆 → ID 是记住了，但双击从此全进 ID，**PS / AI / CDR 又全用不了**。已撤掉。
- **0.3.7 起的做法**：插件是常驻进程，后台每 400 ms 采样一次前台窗口，记住「最近成为前台的设计软件」——这正是菜单上「自动：应用到**最近使用的**设计软件」的字面含义。切到 PS 就套 PS，切到 ID 就套 ID，不需要任何记忆开关，也不会粘死。
- **0.4.0 补的窟窿**：这套「最近前台」只有在钩子真能收到事件时才可靠；收不到就必须靠 Z 序，而 0.3.9 的 Z 序又被 Illustrator 的隐藏窗口劫持（见上一节）。现在 Z 序只认「在用的」窗口，并升到第二优先。

| 版本 | 改动 |
|---|---|
| 0.3.7 | 目标判定改为「最近前台」采样；删掉 `lastTarget` 粘性配置 |
| 0.4.0 | 见上一节：Z 序扫描加可见性过滤，判定顺序改成「前台 → 实时 Z 序 → 最近前台 → 主程序」。多软件同开时不再恒套 AI |
| 0.3.9 | 前台监听从「400 ms 定时轮询」换成 `SetWinEventHook(EVENT_SYSTEM_FOREGROUND)` 事件回调：**不切窗口就一次都不跑**，空闲实测 20 s 内 CPU 时间 0 ms / 内存 9.1 MB。收不到事件的环境（受限桌面、沙箱）会自动退到 2 s 一次兜底采样，且只读一个原子量、不扫窗口 |
| 0.3.8 | ① 主程序返回 `created`（没有选中文字时它真会新建一段）文案改成「…没有选中的文字，已新建一段「X」（Ctrl+Z 可撤销）」，不再让人以为套上了；② `run_powershell` 真正执行超时（原来形参被丢掉，COM 一挂住会连带卡死插件的 stdin 循环） |

实测（0.3.8，双击「自动」，各自软件在前台）：Photoshop 1.15 s、InDesign 0.94 s、CorelDRAW 0.88 s、Illustrator 3.1 s（AI 走主程序 DoJavaScript，天生慢）。全程都有 `正在套用到 X…` 提示，套错能立刻看见。

---

## 0.3.6 修了什么（已被 0.3.7 取代，留作记录）

| 问题 | 现象 | 改法 |
|---|---|---|
| 双击套错了软件（阻断，看起来像 ID 坏了） | 用户正对着 InDesign 排版，双击字体后 ID 里毫无变化——字体被套到了后台的 Illustrator 上（`/apps/active` 报的是 illustrator，Z 序最上层的也是别的软件）。AI 那条路还慢（5–6 s），更像「没反应」 | 新增 `lastTarget`：**只要有一次套成功，就记住这个软件**，之后双击「自动」优先还给它；它没开文档/已退出时，自动退到 Z 序里的另一个软件再试一次。手点过一次「应用到 InDesign」即可长期固定 |
| 不知道在套哪 | 1 秒的执行期里界面没有任何反馈 | 套字一开始就发一行 `正在套用到 InDesign…`，目标一目了然，套错也能立刻发现 |
| ID 每次多一次 COM 往返 | 关模态框（`userInteractionLevel`）原来单独发一次 DoScript，约 +100 ms | 挪进套字脚本第一行，零额外往返 |

实测（ID 2022，文档已打开、选中文本框）：**双击 → 落地 1.05 s**（其中 PowerShell 启动 ~0.37 s、COM 连接 ~0.5 s、真正赋值 ~0.15 s）。想再快只能改架构（常驻 PowerShell 宿主），暂不做。

---

## 0.3.5 修了什么（2026-11-27 全量实测后）

| 问题 | 现象 | 改法 |
|---|---|---|
| Illustrator 套不上字（阻断） | 点中文本框再双击字体，恒回 `APPLIED:0`，字体不变却 `ok:true` | `sel[i].characterAttributes` → 按选区类型取 `textRange`（TextFrame / TextRange / GroupItem 分别处理）；无选区退到整篇文字框；改了 0 个对象时不再报成功（`ERR:选中对象里没有可改的文字`） |
| InDesign `e2e` 必失败 | `SaveOptions.DO_NOT_SAVE_CHANGES` 是 PS 的枚举，ID 只有 `YES/NO/ASK` | ID/IC 分支改用 `SaveOptions.NO` |
| ID 一弹模态框就全废 | `DisplayDialogs=3` 在 ID 上不存在（空操作），宿主一弹「恢复文档」警告，`DoScript` 全卡死，而 probe 仍回 ok | 连接后显式设 `scriptPreferences.userInteractionLevel = NEVER_INTERACT`（枚举值向宿主要，不写死） |
| `%TEMP%` 越用越脏 | 每次调用泄漏一份 `adobe-apply-<pid>.jsx`（实测累计 58 份） | `Run-Jsx` 用完即删 |

AE / PR 的结论见 `docs/测试报告.md`：**面板不会自动加载，首次必须在 `窗口 > 扩展 > FontManager 套字桥` 手动开一次**（AutoVisible 在 AE 2023 上实测未生效），README 旧文里「启动自动显示」这句已作废。

---

## 安装（把 zip 拖进 FontManager 就行）

1. 把 `FM-ADOBE-FONT-0.4.0.zip`（或同内容的 `FM-ADOBE-FONT.zip`）**直接拖进 FontManager 主窗口**
   —— 软件会认出这是插件包并自动安装。
   （也可在 设置 → 插件 → 安装插件包… 选这个 zip；升级同理，拖进去会覆盖安装，配置保留。）
2. 设置 → 插件 → 找到 **Adobe 套字器（全家桶）** → 打开开关。
3. 同一行右侧的**齿轮** = 插件自己的设置面板；**行内右键**还有「双击行为…」「安装 / 重装 AE / PR 面板」「自检 Adobe 通道」。
4. 速览界面双击字体 / 字族右键菜单即可套用。
5. **AE / PR 用户多做一步**：设置面板里点一次「安装 / 重装 AE / PR 面板」（不需要管理员权限），
   重启 AE / PR 后，在 `窗口 > 扩展 > FontManager 套字桥` 打开面板。AE 与 PR 都靠这个面板在宿主内部执行脚本；
   **PR 只能靠它**，必须打开并保持开着。

> 如果以前装过官方的 `FM-FONT-APPLY`（旧名 `com.fontmanager.font-apply`），请删掉或关掉它 ——
> 两个插件都声明了「自动：」菜单，主程序双击只会转发给其中一个，留两个会造成行为不确定。

> **从 0.3.3 升级（ID 改过）**：0.3.3 的 ID 是 `com.iieozo.adobe-font`，0.3.4 起统一成
> `FM-ADOBE-FONT`（插件中心只收 `FM-` 前缀）。主程序按**清单 ID** 找已装目录，所以这次
> 改名会装成**新的一行**，旧的 `com.iieozo.adobe-font` 仍在列表里。装完新版后到
> 设置 → 插件 → 「打开插件目录」，把 `com.iieozo.adobe-font` 那个目录删掉即可
> （双击行为若改过，重设一次就行；用户级配置在 `%APPDATA%\FontManager\adobe-font\`，不受影响）。

设置面板可以配置：

| 项 | 作用 |
|---|---|
| 双击行为 | 直接套用到最近在用的软件 / 先点一下目标窗口（15 秒）/ 只复制不套用 |
| 固定目标 | 右键「自动」时也可以固定成某个软件（PS / AI / CDR / ID / IC / AE / PR） |
| 安装 / 重装 AE / PR 面板 | 一键装 CEP 面板，不需要管理员权限，装完重启 AE / PR |
| 唤出套字桥面板 | 后台通道失败时，把已加载但被藏起来的面板切到前台；没加载过会提示去「窗口 > 扩展」打开一次 |
| 自检 Adobe 通道 | 列出注册表 / 目录探测到的所有 Adobe 安装位置（写进 设置 → 诊断 日志） |

配置存在插件目录的 `config.json`；安装目录不可写时自动退到 `%APPDATA%\FontManager\adobe-font\config.json`。

---

## 插件规则对照（0.3.4 起，按 `FontManager` 仓 `docs/PLUGINS.md` + `多软件共用插件库.md` 逐条核过）

| 规则 | 要求 | 本插件 |
|---|---|---|
| ID 形态 | `FM-XXX-XXX`：前缀 `FM` 大写、后两段字母或数字、整串 ≤ 40、只许字母数字与两条短横 | `FM-ADOBE-FONT`（13 字符，0.3.3 的 `com.iieozo.adobe-font` 已不符合） |
| 显示名 | ≤ 25 字（卡片一行放得下） | 「Adobe 套字器（全家桶）」14 字 |
| 入口 | `entry` 可直接是 `.exe`，`interpreter` 留空 = 自包含 | `adobe-font.exe` + `interpreter: ""`，不依赖 Python / Node |
| 权限 | 必须是主程序 `PERMS` 白名单里的名字，不在表里的会被静默丢掉 | `read:fonts` / `write:apply` / `read:apps`（三项都在表里） |
| 菜单挂点 | `on` 只认 `family`（字族右键）/ `plugin`（插件行右键） | 8 条挂字族，7 条挂插件行（不需要选字体） |
| 设置面板 | 有面板就写 `settings`（标题 + 钩子名），没写就没有齿轮 | `title` + `hook: "settings"` |
| 运行环境自述 | 建议写 `requirements`（runtime / libraries / system / platforms / note） | 无运行时、零第三方库、Windows、PowerShell 5.1 |
| API 级别 | `apiLevel` = 1（当前主程序） | 1 |
| 版本号 | semver | `0.4.0` |
| 分发包形态 | zip 里 `plugin.json` 在根；`config.json` / `secret.bin` / `state.json` 属数据文件，**不进包**（更新时也不会被覆盖） | 根目录三个文件，见下 |
| 体积 | 单文件 ≤ 10 MB、整包 ≤ 20 MB | exe 451 KB，整包 < 1 MB |
| 命名 | 目录名 = ID；资产名 `<ID>.zip`，带版本别名 `<ID>-<version>.zip` | `FM-ADOBE-FONT/`、`FM-ADOBE-FONT.zip`、`FM-ADOBE-FONT-0.4.0.zip` |
| 通信 | stdin 收 `init` / `invoke`，stdout 每行一个 JSON（UTF-8） | `log` / `toast` / `hint` / `open-url`（都在主程序支持的类型里，0.3.4 实测两帧往返正常） |

---

## 支持矩阵

| 应用 | 通道 | 状态 | 说明 |
|---|---|---|---|
| Photoshop | 主程序 `POST /fonts/apply` | **已实测** | 2023 24.7.0，端到端换字体读回确认 |
| Illustrator | 主程序 `POST /fonts/apply` | **已实测** | 2023 27.8.1，同上 |
| CorelDRAW | 主程序 `POST /fonts/apply` + 插件自带 COM 兜底 | **已实测** | 2022 24.0.0.301：自动/指定都能选中 CDR，选中 1~2 个文字对象 → `APPLIED:1/2`，读回`黑体`/`微软雅黑`；非文字选区与无文档的提示见下 |
| InDesign | COM + DoScript（插件自带） | **已实测** | 2022 17.4.0.51：无选区套当前跨页文本框、选中文字只改选中文字，读回确认 |
| InCopy | COM + DoScript（插件自带） | 代码就绪 | 与 ID 同一套对象模型、同一套字名解析 |
| After Effects | CEP 面板（0.3.3 起面板优先） | **已实测** | 2023 23.6x62：选中文字图层 → `APPLIED\|1\|font=SimHei`，evalScript 回读一致；无选中 872ms 报 `NO_SELECTION` |
| Premiere Pro | CEP 面板（自带） | **可用（限 MOGRT 文字）** | 2023 23.6：改 MOGRT 文字参数的 JSON 换字体；PR 自带文字 Adobe 未开放字体属性，见下 |
| Audition / Media Encoder / Lightroom / Bridge | — | 不适用 | 没有可套字体的文字对象 |

AE / PR 都靠随包 CEP 面板在宿主内部执行 ExtendScript。**AE 从 0.3.3 起也是面板优先**：
原来那条 `AfterFX.exe -r` 后台通道在「AE 已经打开」时根本不执行脚本（详见下文实测），
只剩边缘兜底价值。PR 的 `AutoVisible` 不生效（实测启动后 `cep_cache` 里确实出现了面板目录，
但面板不响应指令），所以**第一次用 PR 必须手动在 `窗口 > 扩展` 里打开一次**。

PS / AI / CDR 复用主程序那套引擎（启用检查、CJK 提醒、9 种 outcome），
插件只负责挑字重、认目标、翻提示 —— 主程序修好的问题不会在插件里再留一份。

### CorelDRAW：两个会让「CDR 用不了」的坑（0.3.2 修的）

1. **进程名不是 `coreldraw.exe`，是 `CorelDRW.exe`**。插件原来按进程名精确相等认窗口，
   CDR 永远匹配不上，「自动」于是沿 Z 序落到后台的 After Effects / Illustrator 上，
   用户看到的是「AE 套字失败」——其实 CDR 一次都没被选中。现在按别名表比对
   （`coreldrw.exe` / `coreldrw.exe.exe` / `coreldraw.exe`），「先选窗口」也能点中 CDR 了。
2. **主程序的常驻 COM 宿主会攥着失效的文档引用**。它第一次 apply 时把 `$app` 缓存下来，
   用户关掉那个文档、再新建/打开另一个之后，`ActiveDocument` 就成了失效引用，
   主程序会**秒回 `no-document`**（实测 14ms，同一时刻另一个 COM 客户端明明能读到文档名）。
   插件现在对 `no-document` / `apply-failed` / `app-no-response` 用自带的
   `-Target cdr` 直连一次 COM 自证：成功就覆盖结论（`已应用「…」到 CorelDRAW`），
   失败也用它那句更准的原因（例如「选中的对象里没有文字（图片 / 椭圆 / 群组不能套字）」）。

CDR 自身的规矩也记在脚本注释里：字族名要在、`Story.Font` 中英文共用一个槽、
`FontList` 只登记显示名没有 PostScript 名、字体不认识时是**静默忽略**（只能靠读回判定）。

---

## 安装目录不一致怎么办

**没有任何地方写死路径**：

1. **PS / AI / ID / IC 走 ProgID**（`Photoshop.Application` …），由注册表解析；
2. **AE / PR 的 CEP 面板由 Adobe 自己加载**，我们不需要知道应用装在哪；
3. 需要拉起 exe 时，定位器依次查注册表 `App Paths` → `Uninstall\InstallLocation`
   → 各盘 `Program Files*` / `Adobe` / 用户目录模糊匹配 → 目录内限深递归找主 exe；
4. 兜底：`-AppPath` 参数可手动指定目录或 exe 全路径。

```powershell
# 不启动任何 Adobe，只看探测结果
adobe-font.exe -Mode locate
```

实测：本机 Adobe 装在 `D:\Users\87557\Adobe Photoshop 2023` 这种非 Program Files 布局，
定位器 2 秒内把 7 个应用全找齐。

---

## 独立命令行用法（不装进 FontManager 也能用）

```bat
adobe-font.exe -Mode locate
adobe-font.exe -Target ps -Mode probe
adobe-font.exe -Target id -Mode e2e
adobe-font.exe -Target ps -Mode apply -Font "SourceHanSansSC-Bold"
adobe-font.exe -Target ae -Mode apply -Family "思源黑体" -Style "Bold"
adobe-font.exe -Target ai -Mode fonts -MaxFonts 30
```

`-Target` 省略时默认 `auto`（`ps → ai → id → ic → ae → pr` 找第一个可用的）。

---

## After Effects：面板优先（0.3.3 纠正了原来的错误结论）

AE 没有 Application 级 COM，脚本只能由宿主内部执行。**0.3.3 之前这里写的是「优先用
`AfterFX.exe -r`，不需要打开面板」——这条结论是错的**，已实测推翻：

> AE 已经在运行时，`AfterFX.exe -r script.jsx` **完全不执行脚本**。验证方法：写一个只
> `new File(...).write('marker')` 的脚本交给 `-r`，命令 1.5 秒就返回、没有新进程、
> 30 秒没有 marker 落盘。也就是说这条通道只在「AE 没在跑、由 `-r` 顺手拉起一个新实例」时才有意义，
> 而那种场景下没有工程可选，套字本身也没有意义。

所以现在的顺序是 **CEP 面板优先，命令行只作边缘兜底**：

```
插件 / exe ──写──> %TEMP%\fm_adobe_bridge\cmd-ae.json
                         │ （面板每 300ms 轮询）
                         ▼
                   CEP 面板 → evalScript → host.jsx → AE 执行
                         │  写 res-<id>.json
                         ▼
                   exe 读回结果（872ms 就能拿到 NO_SELECTION，不再白等 20 秒）
```

- 面板由清单里的 `AutoVisible` 在 AE 启动时自动显示，**实测 AE 2023 有效**（`cep_cache` 里会出现
  `AEFT_23.6_com.fontmanager.adobebridge.panel`）；面板被收进面板组没显示时，插件会试着用 CDP
  的 `/json/activate` 把它唤到前台。
- 面板确实没加载时，提示会说清入口：「AE 里还没加载套字桥面板：窗口 > 扩展 > FontManager 套字桥
  （打开一次即可）」，不再甩「AE 可能弹着对话框」这种把人带偏的话。
- 设置面板里的「安装 / 重装 AE / PR 面板」会让 exe 从内置资源释放安装脚本并装到
  `%APPDATA%\Adobe\CEP\extensions\com.fontmanager.adobebridge`（**不需要管理员权限**），
  同时把 `PlayerDebugMode` 置 1（未签名扩展能被加载的前提）。

### AE 实测结论（2023 / 23.6x62，0.3.3 全程走面板）

| 场景 | 结果 |
|---|---|
| 选中文字图层 → 套 SimHei | `APPLIED\|1\|font=SimHei`，evalScript 回读 `font=SimHei` |
| 改套微软雅黑 | `APPLIED\|1`，回读 `font=MicrosoftYaHei`（AE 只回英文名，中文族名不落地） |
| 没有选中任何图层 | `NO_SELECTION`，**872ms** 返回（旧版会白等 20 秒再报错） |
| 选中的是纯色层 | `ERR:选中的图层不是文字层`（旧版会回 `APPLIED\|0` 假成功） |

两个必须记住的 API 事实：

| 属性 | 可写性 |
|---|---|
| `TextDocument.font` | **可写**（接受 PostScript 名，AE 自己解析 family + style） |
| `TextDocument.fontFamily` / `fontStyle` | **只读**，赋值抛 readOnly |
| `app.fonts` | 不存在，枚举恒为 -1（套字不需要枚举） |

所以 AE 通道统一用 PostScript 名；中文字族名经 evalScript 会变成 GBK 字节，别走这条路。

### InDesign：字名这一关（这次修的就是它）

ID 是全家桶里唯一**不吃 PostScript 名**的：同一个字体在 PS / AI / AE 里写
`SimHei-Bold` 就行，到 ID 会直接报「请求的字体系列不可用」。四条实测结论：

| 写法 | ID 2022 结果 |
|---|---|
| `MicrosoftYaHei` / `MicrosoftYaHei-Bold` | ✗ 不可用 |
| `SimHei-Bold` / `SourceHanSansSC-Bold` | ✗ 不可用 |
| `Microsoft Ya Hei`（英文族名） | ✗ 中文版 ID 不认 |
| `微软雅黑` / `微软雅黑\tBold` | ✓ |
| `HarmonyOS Sans SC\tBold` | ✓（英文族名这类能认） |
| `SimHei` / `宋体` | ✓（这类字名恰好等于 PS 名） |

所以 ID 通道的候选顺序是：**字族名+字重 → 字族名（"字族 字重" 写法）→ 纯字族名 → PS 名**，
族名同时取 FontManager 的 `family` 与 `localizedNames`（中文版 ID 往往只认本地化名），
字重从 PS 名后缀和 `weight` 数字推（FontManager 的 `style` 可能是 `Negreta` 这种写法）。

还有两个坑必须绕开：

1. `app.fonts.itemByName(错名)` **不报错**，给你的"占位字体" `isValid` 还是 `true`，
   连 `.fontStyle` 都没有；真赋值时才抛错。⇒ 字体能不能用只能靠"真赋一次值"判定，
   代码里是逐个候选 `try` 赋值，谁成功谁算命中。
2. **千万不要 `for` 循环枚举 `app.fonts`**：本机 1273 个字体，扫到某个坏字条会让
   `DoScript` 直接不返回、把调用进程拖死。定位字体一律用候选名去试，不枚举。
3. 另外 `TextFrame` 没有 `appliedFont` 属性（`Character` 有），赋值顺序得是
   `appliedFont`（选区精确）→ `parentStory`（整条故事）→ `texts`。

无选区时的行为：先当前跨页/页面里带文字的文本框，找不到再退回整篇文档；
整个文档一个带字的文本框都没有才报 `NO_TEXT`（"没有可套用的文字"），
跟"字体不可用"分开提示，不再一律说"没有选中文字"。

---

### Premiere Pro：能套什么、不能套什么

PR 没有 COM，也不支持 `-r` 跑脚本，**唯一入口是宿主内的 CEP 面板**（`窗口 > 扩展 > FontManager 套字桥`，
打开后保持开着）。所以 PR 的第一次使用必须手动开一次面板，之后双击字体才有通道。

| 文字类型 | 能不能换字体 | 怎么做的 |
|---|---|---|
| **MOGRT 模板文字**（AE 做的、带「字体」参数的模板） | 能 | 读文字参数的 JSON 值，只改 `fontEditValue` / `fontFamilyEditValue` / `fontStyleEditValue`，再 `setValue` 写回；写完读回校验 |
| PR 自带文字工具做的文字（Graphics Clip） | **不能** | Adobe 只暴露 Source Text（纯字符串）/ Scale / Opacity / Position，没有字体参数；官方在 2025-02 与 2026-04 两次明确回复「Not today」 |

宁可不做也不假装：自带文字会返回一句明确的话（「Adobe 未开放字体属性，改不了」），
不会像之前那样报成别的错误。MOGRT 那条路写完会读回确认，读回对不上就提示「已写入但回读不匹配，
请在节目监视器确认」，不硬说成功。只改字体字段，文字内容 / 字号 / 颜色 / 字偶距一律不动。

一个坑：`ComponentParam.displayName` 是本地化的，模板参数名可能是「标题」这种自定义名字，
所以代码不靠名字找参数——**凡是值形如 `{...}` 的参数就按 MOGRT 文字参数处理**，名字只用来识别"自带文字"。

---

## 文件清单

分发包 `FM-ADOBE-FONT.zip`（版本别名 `FM-ADOBE-FONT-0.4.0.zip`）里只有 3 个文件：

| 文件 | 作用 |
|---|---|
| `adobe-font.exe` | 唯一程序文件：插件协议 + 设置面板 + 套字逻辑。PowerShell 脚本与 CEP 面板在构建时混淆后嵌进 exe，运行时释放到临时目录，不随包分发明文源码。 |
| `plugin.json` | 插件清单：ID / hooks / 菜单 / 设置齿轮 / 申报权限（纯元数据） |
| `README.md` | 本说明 |

`config.json`（双击行为与固定目标）**不在包里**：主程序把 `config.json` 当插件数据文件，
首次启动时由插件自己创建，升级时永远不会被包覆盖 —— 包里放一份只会让人以为它会生效。

exe 在没有 `adobe-apply.ps1` / `cep/` / `rust/` 的干净目录里已实测可以完整工作（定位器、双击套字、面板均正常），
所以这四样不进安装包。

---

## 想接着改？源码在 `FM-ADOBE-FONT-0.4.0-source.zip`

拿到这个插件的人**不是只能装来用**：源码单独打成一个包，随安装包一起发（同一目录 / 同一个 release）。
两者必须分开，原因很硬：插件中心（registry）的文件白名单是
`.py .js .mjs .cjs .ts .exe .dll .json .yaml .toml .ini .cfg .md .txt .csv .tsv .html .css .svg`
+ 图片 / 字体 —— **`.ps1` / `.rs` / `.jsx` / `.xml` 不在名单里**，塞进安装包上传会被直接拦下。

| 源码包里的文件 | 是什么 |
|---|---|
| `rust/src/main.rs` | 插件协议层：stdin 收 `init` / `invoke`，stdout 发 `log` / `toast` / `hint` / `open-url`；菜单分派、`/fonts/apply` 与 `/apps/active` 调用、设置面板的本地 HTTP 服务都在这里 |
| `rust/build.rs` | 构建时把 ps1 与 CEP 面板按 `RES_KEY` 异或后嵌进 exe（改版本号时 `RES_KEY` 与 `main.rs` 的常量必须同版） |
| `adobe-apply.ps1` | 套字主体：PS / ID / IC / AE 的 COM + ExtendScript、CorelDRAW 直连兜底、应用定位器、CLI 模式 |
| `install-cep.ps1` | 把 `cep/` 装进 `%APPDATA%\Adobe\CEP\extensions\` 并置 `PlayerDebugMode=1`（免管理员） |
| `cep/com.fontmanager.adobebridge/` | AE / PR 面板：`main.js`（300ms 轮询指令文件）、`host.jsx`（宿主内 ExtendScript）、`index.html`、`CSXS/manifest.xml` |
| `probe_ae.jsx`、`probe_ae_live.jsx` | 排查 AE 通道用的探针脚本（一次性工具） |
| `tools/package.py` | **一键出包**：规则自检 + 安装包 + 源码包 |

构建三步（本机可复现，不需要额外装 Rust）：

```bash
source "…/fillsFontManager/Fonts工程文件/env.sh"      # 便携 Rust 1.99 + MSVC + Windows SDK
cd src/rust && cargo build --release                 # → src/rust/target/release/adobe-font-plugin.exe
cd .. && cp rust/target/release/adobe-font-plugin.exe adobe-font.exe
cd .. && python src/tools/package.py                 # 产物全部落在 dist/
```

三个必须知道的点：

1. **改 `adobe-apply.ps1` / `cep/` / `rust/` 之后必须重编 exe** —— exe 里嵌的是构建那一刻的副本，
   运行时释放到 `%TEMP%\fm-adobe-plugin-<版本>`，目录里放一份改过的明文脚本**不会生效**。
2. 改 `host.jsx` 要重启 AE / PR（`location.reload()` 不会重置 ExtendScript 环境里已定义的函数）。
3. `tools/package.py` 会先跑一遍规则自检（ID 形态、名称长度、semver、权限白名单、菜单挂点、settings、requirements），
   不过就不出包 —— 别绕过它手搓 zip，早前台拦下比等 CI 打回便宜。

<!-- ID-NOTE -->


---

## 已知坑（都已在代码里绕过）

1. `.ps1` 带中文必须 UTF-8 with BOM，且只能一个 BOM —— 双 BOM 会让 `<#` 注释块失效。
2. 控制台输出锁定 UTF-8：PowerShell 重定向按 OEM 代码页（936）写，父进程按 UTF-8 解会乱码。
3. `App Paths` 的值常带引号，`Test-Path` 会误判「不存在」，先 `Trim('"')`。
4. `CSInterface.js` 不是 CEP 内置库；面板直连 `window.__adobe_cep__`，零外部依赖。
5. AE / PR 不能共用一个指令文件，已拆成 `cmd-ae.json` / `cmd-pr.json`。
6. 改 `host.jsx` 必须重启宿主：`location.reload()` 不会重置 ExtendScript 环境里已定义的函数。
7. 面板服务只绑 `127.0.0.1`，每次打开生成一次性 key，别的站点读不到，45 分钟无请求自动停。
8. ID 的 ExtendScript 是 **ES3**：`String.prototype.trim` / `Array.map` 这类都不存在，写了会静默变成 `ERR:String().trim is not a function`。
9. ID 的 `app.fonts` 不能 `for` 循环枚举（会打断脚本引擎），只按候选名 `itemByName` 试；`itemByName` 命中"占位字体"也不报错，得靠真赋值验证。
10. 换 exe 前必须先结束 `adobe-font.exe` 进程（运行中的 exe 覆盖会 `Device or resource busy`）；Windows 下可先把它改名再放新文件，但新 exe 要等 FontManager 重新拉起插件才生效 —— 在 设置 → 插件 里把开关关掉再打开即可。
11. **ID 装上以后不能改**：启用状态按 ID 记忆、主程序按清单 ID 认已装目录；改名等于换一个插件（会多出一行、旧目录留在磁盘）。插件中心只收 `FM-` 前缀，所以改名要一次改到位，并同步目录名与 zip 名。
12. **`config.json` 别塞进 zip**：它属于主程序的数据文件白名单（`config.json` / `secret.bin` / `state.json`），安装时会被直接跳过，而插件「目录不可写」时还会退到 `%APPDATA%\FontManager\adobe-font\`，包里的那份永远不是生效的那份。

