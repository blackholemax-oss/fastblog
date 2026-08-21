# fastblog

fastblog 是一个静态博客生成器 CLI 工具：在 `content/` 目录撰写 Markdown，
一条命令即可渲染为完整的静态 HTML 网站，并一键同步到 GitHub 部署。

## 特性

- Markdown 渲染：`python-markdown`（Tables / CodeHilite / TOC 扩展）
- 元数据解析：`python-frontmatter`（YAML / TOML Frontmatter）
- 主题渲染：`Jinja2`，支持主题继承链（`theme.yaml` 的 `parent` 字段）
- 插件机制：`on_init` / `before_generate` / `after_generate` 三钩子，`importlib` 动态加载
- 部署自动化：`GitPython` 强制推送（`main` / `gh-pages`）+ GitHub Actions 工作流自动生成
- 本地预览：内置 `http.server`，开箱即用

## 环境要求

- Python 3.10+
- 依赖安装：`pip install -r requirements.txt`（建议使用虚拟环境）

## 快速开始

```bash
# 1. 安装依赖（示例：虚拟环境）
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. 生成用户配置（可选，缺省时使用内置默认值）
cp config.example.yaml config.yaml

# 3. 构建静态站点到 output/
.venv/bin/python -m staticgen.cli build

# 4. 本地预览 http://127.0.0.1:8000
.venv/bin/python -m staticgen.cli serve

# 4.1 热部署预览：文件变更后自动构建并刷新浏览器
.venv/bin/python -m staticgen.cli serve --watch

# 5. 构建并推送部署（需先在 config.yaml 配置 deploy.remote 指向产物仓库的远程名）
.venv/bin/python -m staticgen.cli deploy
```

## 命令参考

| 命令 | 说明 |
| --- | --- |
| `build` | 解析内容、渲染页面，输出到 `output/`（每次自动清空，幂等） |
| `serve [--host H] [--port P] [--watch] [--no-browser]` | 本地预览 `output/`；`--watch` 开启热部署，监听内容/主题/插件/配置变更后自动构建 |
| `deploy [--message M]` | 构建 + 恢复 Pages 工作流 + 提交并强制推送到远程分支 |

全局参数：`--config <path>` 指定配置文件（需置于子命令前），`--version` 查看版本。

## 目录结构

```
fastblog/
├── staticgen/            # 核心包（config / cli / engine / readers / renderers / plugins / deploy）
├── themes/default/       # 默认主题（templates/ + static/ + theme.yaml）
├── content/posts/        # Markdown 内容目录（递归扫描 .md/.markdown/.mdown）
├── plugins/              # 用户插件目录（继承 staticgen.plugins.Plugin 的 .py 文件）
├── config.example.yaml   # 示例配置（入库模板）
├── config.yaml           # 用户本地配置（.gitignore 排除，不入库）
├── requirements.txt
└── .github/workflows/    # （可选）本地 Actions 模板，不随仓库提交
```

> 配置隔离：仓库只跟踪 `config.example.yaml`；用户配置 `config.yaml`
> 由 `cp config.example.yaml config.yaml` 生成，已被 `.gitignore` 排除，
> 可安全存放 `deploy.remote_url` 等私有信息。

## 文章格式

支持 YAML（`---`）与 TOML（`+++`）Frontmatter：

```markdown
---
title: 我的第一篇文章
date: 2026-08-18
tags: [随笔, 生活]
summary: 摘要（可选，展示在列表页）
slug: my-first-post      # 可选，默认由标题生成
---

[TOC]                    # 可选，插入目录

正文内容...
```

## 配置说明（config.yaml）

从 `config.example.yaml` 复制生成；缺失时自动回退内置默认值。

| 段落 | 字段 | 说明 |
| --- | --- | --- |
| `site` | `title / description / author / language` | 站点全局信息，注入模板 `site` 变量 |
| `build` | `content_dir / output_dir / theme` | 内容/输出目录与主题名 |
| `serve` | `host / port / open_browser` | 本地预览参数 |
| `deploy` | `enabled / remote / remote_url / branch` | `enabled` 为 true 时每次 build 自动推送；`remote_url` 为远程不存在时必填；`branch` 为推送目标分支（如 `main`，配合 GitHub Actions 自动发布） |

配置缺失的字段自动回退默认值；主题目录不存在时自动回退内置 `default` 主题。

## 插件开发

在 `plugins/` 目录新建 Python 文件，继承 `Plugin` 并重写钩子即可：

```python
from staticgen.plugins import Plugin, PluginContext

class MyPlugin(Plugin):
    name = "my-plugin"

    def on_init(self, ctx: PluginContext) -> None: ...
    def before_generate(self, ctx: PluginContext) -> None:
        # 可修改 ctx.posts 干预渲染
        ...
    def after_generate(self, ctx: PluginContext) -> None: ...
```

钩子异常不会中断构建，仅打印警告。参考内置示例 `plugins/hello_plugin.py`。

## 自愈与容错机制

- 所有文件 IO 均捕获异常并输出中文提示，单篇文章/单插件损坏不影响整体构建
- 路径处理全部基于 `pathlib.Path` 绝对路径，无硬编码
- `build` 自动清空 `output/`（保留 `.git` 以保证部署历史连续）
- 部署缺少 Git 身份时自动写入本地 `user.name/email` 后重试

## GitHub Actions

部署采用「产物仓库 + GitHub Actions」模式：产物仓库（如
`username.github.io`）的 main 分支只包含静态网页文件与
`.github/workflows/pages.yml`（由 `deploy` 命令自动恢复写入）。

`deploy` 推送 main 后，线上 workflow 将仓库内容直接发布到 GitHub Pages
（GitHub Pages 设置中构建源需选择 GitHub Actions）。

> 注意：`build` 会清空 `output/`，连带删除其中的 `pages.yml`；
> `deploy` 命令会在推送前自动恢复该文件，无需手动处理。