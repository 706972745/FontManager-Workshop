# Adobe 套字器（FontManager 插件 · 0.3.3）

**一个插件就够了**：双击套字、右键套字、设置面板、AE / PR 桥接面板都在这一个包里。
不用再下载官方「字体套用（PS / AI / CDR）」插件，也不需要 Python / Node 运行时。

把字体应用到 Adobe 系列应用**当前选中的文字**上。同一套指令，按应用能力自动选通道。

---

## 安装（把 zip 拖进 FontManager 就行）

1. 把 `Adobe套字器-0.3.3.zip` **直接拖进 FontManager 主窗口** —— 软件会认出这是插件包并自动安装。
   （也可在 设置 → 插件 → 安装插件包… 选这个 zip；升级同理，拖进去会覆盖安装，配置保留。）
2. 设置 → 插件 → 找到 **Adobe 套字器（全家桶）** → 打开开关。
3. 同一行右侧的**齿轮** = 插件自己的设置面板；**行内右键**还有「双击行为…」「安装 / 重装 AE / PR 面板」「自检 Adobe 通道」。
4. 速览界面双击字体 / 字族右键菜单即可套用。
5. **AE / PR 用户多做一步**：设置面板里点一次「安装 / 重装 AE / PR 面板」（不需要管理员权限），
   重启 AE / PR 后，在 `窗口 > 扩展 > FontManager 套字桥` 打开面板。AE 平时走后台脚本、面板只作兜底；
   **PR 只能靠这个面板**，必须打开并保持开着。

> 如果以前装过官方的 `com.fontmanager.font-apply`，请删掉或关掉它 —— 两个插件都声明了
> 「自动：」菜单，主程序双击只会转发给其中一个，留两个会造成行为不确定。

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

分发包 `com.iieozo.adobe-font.zip` 里只有 4 个文件：

| 文件 | 作用 |
|---|---|
| `adobe-font.exe` | 唯一程序文件：插件协议 + 设置面板 + 套字逻辑。PowerShell 脚本与 CEP 面板在构建时混淆后嵌进 exe，运行时释放到临时目录，不随包分发明文源码。 |
| `plugin.json` | 插件清单：hooks / 菜单 / 设置齿轮 / 申报权限（纯元数据） |
| `config.json` | 双击行为与固定目标（首次启动自动创建） |
| `README.md` | 本说明 |

开发目录里保留的 `adobe-apply.ps1`、`install-cep.ps1`、`cep/`、`rust/` 是源码，供编译和排查用，**不需要也不应该发给最终用户**。exe 在没有这些文件的干净目录里已实测可以完整工作（定位器、双击套字、面板均正常）。

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
