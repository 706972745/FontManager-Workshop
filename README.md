# FontManager Workshop

FontManager 插件中心 registry。插件经 PR 审核合并后上架；浏览与下载免登录。

- `index.json` —— 聚合的卡片数据（含官方区），客户端唯一请求
- `plugins/<id>__<author>/` —— 每个插件一个文件夹，`plugin.json` + 本体文件
- 上传请使用 FontManager 主程序的「插件中心」上传流程（CI 校验 manifest / 白名单 / sha256）
