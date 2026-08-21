---
name: writing-blog-posts
description: Use when 在 fastblog 项目（content/posts/）撰写或发布博客文章，包括写技术博客、开发日志、记录踩坑经历。提供文章格式契约（YAML frontmatter、[TOC]、结构模板、slug 规则）与「构建验证 → deploy 部署 → git 提交」的发布流程。
---

# 撰写 fastblog 博客文章

## 概述

fastblog 博客文章是带 YAML frontmatter 的 Markdown，写入 `content/posts/`，
由 `deploy` 命令构建并发布到 GitHub Pages。本技能定义文章必须满足的
格式契约与完整发布流程。

## 文章格式契约（必须全部满足）

每篇文章必须包含以下 frontmatter 字段：

```yaml
---
title: 文章标题（中文，简洁）
date: YYYY-MM-DD   # 当天日期
tags: [标签1, 标签2]   # 2-4 个，中文或英文
summary: 一句话摘要（30-60 字，展示在列表页）
slug: english-kebab-case   # 必填，小写英文连字符，用于 URL
---
```

- `slug` 必须是小写英文连字符（如 `blog-deploy-journey`），**禁止中文或空格**
- 正文第一行必须是 `[TOC]` 占位符（生成目录）
- 文件名为 `<slug>.md`

## 结构模板

开发日志/技术文章按此骨架组织，章节可按主题调整但顺序保持一致：

1. **背景** — 为什么做这件事
2. **方案选型 / 思路** — 对比 2+ 方案（列表或表格），说明取舍
3. **实施过程** — 分步骤，每步配命令或代码块
4. **踩坑记录** — 遇到的问题与解法（有则必写）
5. **结语** — 收获与后续计划

代码/配置示例必须标注语言（```yaml、```bash、```powershell 等）；
关键路径、命令名用反引号包裹。

## 去 AI 味（写作完成后必过一遍）

**AI 味信号——出现即改：**

- 元叙述：「本文总结」「本文将」「旨在」「值得注意的是」
- 整齐排比与对称结构（连续三四个「…要…」）
- 无信息量的表格（纯装饰性对比、凑数表格）
- 空洞结尾升华（「让我们…」「值得深思」「展望未来」）
- 高频 AI 词：赋能、沉淀、闭环、链路、范式、抓手、痛点、颗粒度
- 每节字数均匀、节奏单调，读完没有记忆点

**正面配方——重写成什么样：**

- 有人称、有具体例子（「我遇到…」「上次…」），像聊天不像汇报
- 句子长短错落，段落不必均匀
- 表格只在真有对比价值时用（如命令/方案对照）；能用列表说清就不上表
- 删掉任何「删了也不影响内容」的句子
- 结尾落在具体收获或下一步动作，不升华

## 发布流程（写完文章后必须执行）

```powershell
# 1. 本地构建验证（确认无渲染错误、新文章出现在 output/）
& .venv-win\Scripts\python.exe -m fastblog.cli build

# 2. 部署到线上（自动恢复 pages.yml、提交产物、推送触发 Actions 发布）
& .venv-win\Scripts\python.exe -m fastblog.cli deploy --message "docs: 新增文章：<标题>"

# 3. 提交文章到 fastblog 仓库（不提交 .superpowers/、docs/ 等）
git add content/posts/<slug>.md
git commit -m "docs: 新增文章：<标题>"
```

部署后验证线上可访问：`curl.exe -s https://blackholemax-oss.github.io/posts/<slug>.html`
（工作流约需 30 秒，必要时先 `gh run list --repo blackholemax-oss/blackholemax-oss.github.io` 查看状态）。

## 常见错误

| 错误 | 修正 |
| --- | --- |
| slug 用了中文/空格 | 改为小写英文连字符 |
| 缺少 summary 或 date | frontmatter 四字段（title/date/tags/summary）+ slug 缺一不可 |
| 忘记 [TOC] | 正文第一行加入 `[TOC]` |
| 直接运行 deploy 未先 build | deploy 内置构建，但先用 build 单独验证渲染 |
| 提交了 .superpowers/、docs/ | 只 add 文章文件 |
| build 后 pages.yml 被清空而惊慌 | deploy 命令会自动恢复，无需手动处理 |
| 文章满屏表格/「本文总结」/对称排比 | 按「去 AI 味」配方重写后再发布 |
