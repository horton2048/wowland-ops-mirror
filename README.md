# WowLand 运营文档镜像

飞书为权威编辑源；本仓库是 **公开只读镜像**，供 Grok Bot / 运营助手拉取最新口径。

## 官方飞书索引（权威）

1. WowLand社群｜试营业执行手册 — https://larkcommunity.feishu.cn/wiki/JdscwcN7ji2kCHke3V5chJJWnbe
2. （第二份，待导出后放入 `docs/`）— https://larkcommunity.feishu.cn/wiki/DpzZwwMFTiAqBOkBRUAcFiKAnbc

## 机器人读取入口

- 试营业手册 raw：`https://raw.githubusercontent.com/horton2048/wowland-ops-mirror/main/docs/试营业执行手册.md`
- 本 README：`https://raw.githubusercontent.com/horton2048/wowland-ops-mirror/main/README.md`

## 如何同步（飞书改了之后）

1. 在飞书打开文档 → 导出或复制为 Markdown
2. 覆盖本仓库 `docs/` 下对应文件
3. `git add -A && git commit -m "sync: 更新手册" && git push`

可选：本机用脚本定时从飞书导出后 push（第二份正文需先能导出）。

## 本地项目对照

用户本机：`/Users/hut/Projects/抖音校园/`
