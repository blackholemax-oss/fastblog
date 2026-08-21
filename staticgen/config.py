"""配置加载器。

负责从项目根目录的 ``config.yaml`` 读取全局配置，转换为类型安全的
dataclass 对象。缺失的配置项会回退到内置默认值，避免因配置文件不完整
导致生成流程崩溃。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

# ---------------------------------------------------------------------------
# 默认值常量
# ---------------------------------------------------------------------------
DEFAULT_SITE_TITLE = "My Static Blog"
DEFAULT_SITE_DESCRIPTION = "Powered by StaticGen"
DEFAULT_SITE_AUTHOR = "Anonymous"
DEFAULT_SITE_LANGUAGE = "en"

DEFAULT_CONTENT_DIR = "content"
DEFAULT_OUTPUT_DIR = "output"
DEFAULT_THEME = "default"

DEFAULT_SERVE_HOST = "127.0.0.1"
DEFAULT_SERVE_PORT = 8000
DEFAULT_OPEN_BROWSER = True

DEFAULT_DEPLOY_ENABLED = False
DEFAULT_DEPLOY_REMOTE = "origin"
DEFAULT_DEPLOY_BRANCH = "gh-pages"
DEFAULT_AUTO_ACTIONS = True


# ---------------------------------------------------------------------------
# 配置 dataclass
# ---------------------------------------------------------------------------
@dataclass
class SiteConfig:
    """站点全局信息。"""

    title: str = DEFAULT_SITE_TITLE
    description: str = DEFAULT_SITE_DESCRIPTION
    author: str = DEFAULT_SITE_AUTHOR
    language: str = DEFAULT_SITE_LANGUAGE


@dataclass
class BuildConfig:
    """构建相关配置。"""

    content_dir: str = DEFAULT_CONTENT_DIR
    output_dir: str = DEFAULT_OUTPUT_DIR
    theme: str = DEFAULT_THEME


@dataclass
class ServeConfig:
    """本地预览服务配置。"""

    host: str = DEFAULT_SERVE_HOST
    port: int = DEFAULT_SERVE_PORT
    open_browser: bool = DEFAULT_OPEN_BROWSER


@dataclass
class DeployConfig:
    """GitHub 部署配置。

    Attributes:
        enabled: 为 ``True`` 时每次 build 自动推送。
        remote: 远程仓库名。
        remote_url: 远程仓库地址（HTTPS/SSH）；为空且远程不存在时部署失败。
        branch: 推送目标分支（``main`` 或 ``gh-pages``）。
        auto_actions: 为 ``True`` 时自动生成 GitHub Actions 工作流模板。
    """

    enabled: bool = DEFAULT_DEPLOY_ENABLED
    remote: str = DEFAULT_DEPLOY_REMOTE
    remote_url: Optional[str] = None
    branch: str = DEFAULT_DEPLOY_BRANCH
    auto_actions: bool = DEFAULT_AUTO_ACTIONS


@dataclass
class Config:
    """StaticGen 全局配置聚合对象。

    Attributes:
        root_dir: 项目根目录（config.yaml 所在目录）的绝对路径。
        site: 站点全局信息。
        build: 构建配置。
        serve: 本地预览配置。
        deploy: GitHub 部署配置。
        raw: 从 YAML 解析出的原始字典（供插件/主题扩展使用）。
    """

    root_dir: Path
    site: SiteConfig = field(default_factory=SiteConfig)
    build: BuildConfig = field(default_factory=BuildConfig)
    serve: ServeConfig = field(default_factory=ServeConfig)
    deploy: DeployConfig = field(default_factory=DeployConfig)
    raw: Dict[str, Any] = field(default_factory=dict)

    def content_path(self) -> Path:
        """返回内容目录的绝对路径。

        Returns:
            Path: 内容目录绝对路径。
        """
        return (self.root_dir / self.build.content_dir).resolve()

    def output_path(self) -> Path:
        """返回输出目录的绝对路径。

        Returns:
            Path: 输出目录绝对路径。
        """
        return (self.root_dir / self.build.output_dir).resolve()

    def theme_path(self) -> Path:
        """返回主题目录的绝对路径。

        Returns:
            Path: 主题目录绝对路径。
        """
        return (self.root_dir / "themes" / self.build.theme).resolve()


# ---------------------------------------------------------------------------
# 加载逻辑
# ---------------------------------------------------------------------------
def _as_bool(value: Any, default: bool) -> bool:
    """将 YAML 值解析为布尔值，兼容字符串 ``"true"/"false"`` 等写法。

    无法识别时回退到 ``default``，避免字符串 ``"false"`` 被 Python
    的 ``bool()`` 错误地解析为 ``True``。
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _merge_with_defaults(raw: Dict[str, Any]) -> Dict[str, Any]:
    """将用户配置与默认值合并，缺失字段自动回退。

    Args:
        raw: 从 YAML 解析出的原始配置字典。

    Returns:
        Dict[str, Any]: 合并默认值后的配置字典。
    """
    site = raw.get("site") or {}
    build = raw.get("build") or {}
    serve = raw.get("serve") or {}
    deploy = raw.get("deploy") or {}

    return {
        "site": {
            "title": site.get("title", DEFAULT_SITE_TITLE),
            "description": site.get("description", DEFAULT_SITE_DESCRIPTION),
            "author": site.get("author", DEFAULT_SITE_AUTHOR),
            "language": site.get("language", DEFAULT_SITE_LANGUAGE),
        },
        "build": {
            "content_dir": build.get("content_dir", DEFAULT_CONTENT_DIR),
            "output_dir": build.get("output_dir", DEFAULT_OUTPUT_DIR),
            "theme": build.get("theme", DEFAULT_THEME),
        },
        "serve": {
            "host": serve.get("host", DEFAULT_SERVE_HOST),
            "port": int(serve.get("port", DEFAULT_SERVE_PORT)),
            "open_browser": _as_bool(serve.get("open_browser"), DEFAULT_OPEN_BROWSER),
        },
        "deploy": {
            "enabled": _as_bool(deploy.get("enabled"), DEFAULT_DEPLOY_ENABLED),
            "remote": deploy.get("remote", DEFAULT_DEPLOY_REMOTE),
            "remote_url": deploy.get("remote_url") or None,
            "branch": deploy.get("branch", DEFAULT_DEPLOY_BRANCH),
            "auto_actions": _as_bool(deploy.get("auto_actions"), DEFAULT_AUTO_ACTIONS),
        },
    }


def load_config(config_path: Optional[Path] = None) -> Config:
    """从 YAML 文件加载配置。

    若 ``config.yaml`` 不存在或内容非法，则回退到内置默认值并打印警告，
    保证构建流程不会因配置文件问题而中断。

    Args:
        config_path: 配置文件路径。为 ``None`` 时自动在项目根目录查找
            ``config.yaml``（不存在则按根目录为当前工作目录处理）。

    Returns:
        Config: 加载完成的配置对象。

    Raises:
        SystemExit: 配置文件存在但无法解析（YAML 语法错误）时直接终止，
            避免携带半损坏配置继续执行。
    """
    if config_path is None:
        config_path = Path.cwd() / "config.yaml"

    root_dir = config_path.parent.resolve()
    config_path = config_path.resolve()

    if not config_path.exists():
        print(
            f"[警告] 未找到配置文件 {config_path}，已回退到默认配置。"
            "可将 config.example.yaml 复制为 config.yaml 进行自定义。"
        )
        return Config(root_dir=root_dir)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw: Dict[str, Any] = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        raise SystemExit(f"[错误] 配置文件 {config_path} 语法错误，请检查 YAML 格式：\n{exc}")
    except OSError as exc:
        print(f"[警告] 无法读取配置文件 {config_path}（{exc}），已回退到默认配置。")
        return Config(root_dir=root_dir)

    merged = _merge_with_defaults(raw)
    config = Config(
        root_dir=root_dir,
        site=SiteConfig(**merged["site"]),
        build=BuildConfig(**merged["build"]),
        serve=ServeConfig(**merged["serve"]),
        deploy=DeployConfig(**merged["deploy"]),
        raw=raw,
    )
    print(f"[信息] 配置加载完成：主题={config.build.theme}，内容目录={config.build.content_dir}。")
    return config