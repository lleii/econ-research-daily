# 将经研观察部署到 GitHub Pages

## 1. 创建仓库

登录 [GitHub](https://github.com/new)，新建公开仓库，例如 `econ-research-daily`。保持仓库为空，先不要添加 README、许可证或 .gitignore。

## 2. 上传当前项目

在 Windows PowerShell 中执行。把远程地址里的 `YOUR_USERNAME` 换成你的 GitHub 用户名。首次提交时，Git 可能提示配置姓名和邮箱。用 Git Credential Manager 弹出的窗口登录 GitHub。

```powershell
Set-Location -LiteralPath 'D:\桌面\经研观察'
git init -b main
git add .gitignore .github main.py sources.yaml requirements.txt page.html README.md DEPLOY_GUIDE.md data/items.json
git commit -m "Initialize economic research digest"
git remote add origin https://github.com/YOUR_USERNAME/econ-research-daily.git
git push -u origin main
```

在 GitHub 的 **Code** 页确认 `.github/workflows/daily.yml` 和 `page.html` 已上传，并关联仓库默认分支 `main`。

## 3. 启用 Pages

打开仓库 **Settings → Pages**。在 **Build and deployment → Source** 选择 **GitHub Actions**。

## 4. 手动运行并核验

进入 **Actions → 经研观察｜每日采集与发布 → Run workflow**，选 `main` 并运行。查看 `build` 下“采集文章并生成网站”的各来源统计。部署成功后，从 `deploy` 的环境链接或 **Settings → Pages** 打开网站。用手机检查类别筛选、日期顺序，并点开几篇原文核对标题和核心观点。

## 5. 检查每日更新

默认分支的任务在 UTC 23:00（北京时间 07:00）触发。GitHub 调度可能延迟，公开仓库连续 60 天无活动时计划任务可能被停用。可在 Actions 页查看并重新启用。单源访问故障会记录在 `data/last_run.json`，已有归档仍可发布。

如果保存归档报 403，查看 **Settings → Actions → General → Workflow permissions** 和分支保护规则是否允许工作流写入。若部署失败，核对 Pages 来源是否设为 GitHub Actions，以及 `github-pages` 环境的发布规则。

- [GitHub Pages 自定义工作流文档](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [GitHub Actions 定时触发文档](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
