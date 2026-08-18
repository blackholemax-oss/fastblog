"""GitHub 部署子包。

对外暴露 :class:`GitHubDeployer` 与工作流生成函数 :func:`ensure_actions_workflow`。
"""

from staticgen.deploy.github import GitHubDeployer, ensure_actions_workflow

__all__ = ["GitHubDeployer", "ensure_actions_workflow"]