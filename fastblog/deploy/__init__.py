"""GitHub 部署子包。

对外暴露 :class:`GitHubDeployer`。
"""

from fastblog.deploy.github import GitHubDeployer

__all__ = ["GitHubDeployer"]
