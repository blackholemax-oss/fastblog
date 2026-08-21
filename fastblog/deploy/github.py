"""GitHub Pages 部署模块。

基于 GitPython 实现静态产物的自动部署（GitHub Actions 发布模式）：

- 输出目录不存在仓库时自动 ``git init``（初始分支取 ``deploy.branch``）；
- 构建后自动恢复 ``.github/workflows/pages.yml``（构建会清空输出目录，
  该文件是 GitHub Actions 触发发布的关键）；
- 全量暂存并提交，强制推送到配置的远程分支（``main``）。

所有 Git 操作均包裹异常处理并输出用户友好的中文提示。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from git import GitCommandError, GitError, Remote, Repo
from git.exc import InvalidGitRepositoryError

from fastblog.config import Config

PAGES_WORKFLOW = """name: Deploy static content to Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Remove workflow files from site
        run: rm -rf .github
      - name: Setup Pages
        uses: actions/configure-pages@v5
      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: .
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
"""


class GitHubDeployer:
    """GitHub Pages 部署器。

    Attributes:
        config: 全局配置对象。
        output: 输出目录绝对路径（部署内容的来源）。
    """

    def __init__(self, config: Config) -> None:
        """初始化部署器。

        Args:
            config: 全局配置对象。
        """
        self.config = config
        self.output = config.output_path()

    def _get_repo(self) -> Repo:
        """获取输出目录的 Git 仓库，不存在时自动初始化。

        Returns:
            Repo: 输出目录对应的仓库对象。

        Raises:
            RuntimeError: 仓库初始化失败时抛出中文错误信息。
        """
        try:
            return Repo(self.output)
        except InvalidGitRepositoryError:
            pass

        branch = self.config.deploy.branch
        try:
            repo = Repo.init(self.output, initial_branch=branch)
        except (GitError, OSError) as exc:
            raise RuntimeError(f"初始化 Git 仓库失败（{exc}）。") from exc
        print(f"[信息] 已在 {self.output} 初始化 Git 仓库（初始分支 {branch}）。")
        return repo

    def _ensure_remote(self, repo: Repo) -> Remote:
        """获取或创建配置的远程仓库。

        Args:
            repo: 输出目录的仓库对象。

        Returns:
            Remote: 配置名对应的远程仓库对象。

        Raises:
            RuntimeError: 远程仓库不存在且未配置 ``deploy.remote_url``，
                或创建失败时抛出中文错误信息。
        """
        name = self.config.deploy.remote
        try:
            return repo.remote(name)
        except ValueError:
            pass

        url = self.config.deploy.remote_url
        if not url:
            raise RuntimeError(
                "未配置远程仓库地址（config.yaml 的 deploy.remote_url），无法推送。"
            )
        try:
            remote = repo.create_remote(name, url)
        except GitError as exc:
            raise RuntimeError(f"创建远程仓库 {name} 失败（{exc}）。") from exc
        print(f"[信息] 已添加远程仓库 {name} -> {url}。")
        return remote

    def _ensure_pages_workflow(self) -> None:
        """确保 Pages 工作流存在于输出目录。

        ``build`` 每次清空输出目录，会删除
        ``.github/workflows/pages.yml``；该文件是 GitHub Actions
        自动发布的关键，缺失时按内置模板重新写入。

        Raises:
            RuntimeError: 文件写入失败时抛出中文错误信息。
        """
        target = self.output / ".github" / "workflows" / "pages.yml"
        if target.exists():
            return
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(PAGES_WORKFLOW, encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"恢复 Pages 工作流失败（{exc}）。") from exc
        print(f"[信息] 已恢复 Pages 工作流：{target}")

    def _commit_with_fallback(self, repo: Repo, message: str) -> bool:
        """提交全部变更；缺少 Git 身份时自动写入本地身份并重试。

        Args:
            repo: 输出目录的仓库对象。
            message: 提交信息。

        Returns:
            bool: 是否产生了新提交（无变更时为 ``False``）。

        Raises:
            RuntimeError: 提交失败且无法自愈时抛出中文错误信息。
        """
        try:
            if not repo.is_dirty(untracked_files=True):
                print("[信息] 无内容变更，跳过提交。")
                return False
            repo.git.add(A=True)
            repo.index.commit(message)
            print(f"[信息] 已提交：{message}")
            return True
        except GitCommandError as exc:
            if "please tell me who you are" in str(exc).lower():
                author = self.config.site.author
                email = f"{author}@fastblog.local"
                try:
                    with repo.config_writer() as writer:
                        writer.set_value("user", "name", author)
                        writer.set_value("user", "email", email)
                    repo.index.commit(message)
                    print(f"[信息] 已写入本地 Git 身份（{author} <{email}>）并提交：{message}")
                    return True
                except (GitCommandError, OSError) as retry_exc:
                    raise RuntimeError(
                        f"提交失败且自动配置 Git 身份也未成功（{retry_exc}）。"
                    ) from retry_exc
            raise RuntimeError(f"提交失败（{exc}）。") from exc

    def deploy(self, commit_message: Optional[str] = None) -> str:
        """将输出目录提交并强制推送到远程分支。

        Args:
            commit_message: 自定义提交信息；为 ``None`` 时自动生成。

        Returns:
            str: 推送后 HEAD 的短提交号。

        Raises:
            RuntimeError: 输出目录缺失、推送失败时抛出中文错误信息。
        """
        if not self.output.exists():
            raise RuntimeError(
                f"输出目录不存在：{self.output}，请先执行 build 生成站点。"
            )

        repo = self._get_repo()
        remote = self._ensure_remote(repo)
        branch = self.config.deploy.branch
        message = commit_message or f"fastblog build {datetime.now():%Y-%m-%d %H:%M:%S}"

        self._ensure_pages_workflow()
        self._commit_with_fallback(repo, message)

        try:
            repo.git.push(remote.name, f"HEAD:{branch}", force=True, set_upstream=True)
        except GitCommandError as exc:
            raise RuntimeError(
                f"强制推送到 {remote.name}/{branch} 失败（{exc}），"
                "请检查 deploy.remote_url 与仓库权限。"
            ) from exc

        sha = repo.head.commit.hexsha[:7]
        print(f"[信息] 已强制推送到 {remote.name}/{branch}（commit {sha}）。")
        return sha
