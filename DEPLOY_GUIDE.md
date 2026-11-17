# 经济观察部署指南

网站使用 [GitHub Pages](https://lleii.github.io/economic-observer/)，仓库为 [economic-observer](https://github.com/lleii/economic-observer)。仓库 Settings → Pages → Build and deployment 的 Source 使用 GitHub Actions。

1. 以 `editions/` 中的期刊为例，为新日期整理并审阅一期数据。保留已发布日期的 JSON。
2. 把 `site-archive/` 中的快照复制到本地构建目录，运行 `python brief-preview/build.py --issues editions --output public`。检查首页、当期精选和日期归档。
3. 把构建产生的新日期 HTML 复制至 `site-archive/`，提交新日期 JSON 和 HTML 到 main。仓库 Actions 中可查部署状态，也可以手动运行工作流。
4. 次日北京时间 07:00 附近查看 Actions 的定时运行与候选状态。手动勾选“同时运行候选采集”可测试采集。采集与已审阅日报发布各自独立。GitHub 队列可能使定时启动延后。

旧项目 Pages 地址在仓库更名后可能停止提供服务，请将公开书签替换为新网址。
