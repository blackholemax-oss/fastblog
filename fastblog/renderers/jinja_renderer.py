"""Jinja2 模板渲染器。

封装 Jinja2 环境，支持从任意主题目录加载模板，并通过主题继承链
（``theme.yaml`` 的 ``parent`` 字段）实现父子主题模板覆盖：

- 子主题与父主题模板同名时，子主题优先（ChoiceLoader 顺序覆盖）。
- 配置的主题目录缺失时，自动回退到内置 ``default`` 主题。

模板中可用的全局变量与过滤器：

- ``site``：站点全局配置（title / description / author / language）。
- ``now``：构建时刻的 ``datetime`` 对象。
- ``url_for(name)``：生成站点内资源绝对路径（如 ``/static/css/style.css``）。
- ``dateformat(value)``：将日期对象格式化为字符串。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, TemplateNotFound

from fastblog.config import Config

DEFAULT_THEME_NAME = "default"


def _dateformat(value: Optional[Any], fmt: str = "%Y-%m-%d") -> str:
    """将日期值格式化为字符串。

    Args:
        value: 日期对象或 ``None``。
        fmt: 输出格式，默认为 ``%Y-%m-%d``。

    Returns:
        str: 格式化后的日期字符串；值为空时返回空字符串。
    """
    if value is None:
        return ""
    return value.strftime(fmt)


def _url_for(name: str) -> str:
    """生成站点内资源的绝对路径。

    Args:
        name: 相对站点根目录的资源名（如 ``index.html``）。

    Returns:
        str: 以 ``/`` 开头的绝对路径。
    """
    return f"/{name.lstrip('/')}"


def build_site_context(config: Config) -> Dict[str, Any]:
    """构造注入模板的站点全局上下文。

    Args:
        config: 全局配置对象。

    Returns:
        Dict[str, Any]: 含 ``site`` 键的上下文字典。
    """
    return {
        "site": {
            "title": config.site.title,
            "description": config.site.description,
            "author": config.site.author,
            "language": config.site.language,
        }
    }


def _read_parent(theme_yaml: Path) -> Optional[str]:
    """读取主题元数据中的父主题名。

    Args:
        theme_yaml: 主题的 ``theme.yaml`` 文件路径。

    Returns:
        Optional[str]: 父主题名；元数据缺失、读取失败或无父级时返回 ``None``。
    """
    if not theme_yaml.exists():
        print(f"[警告] 主题元数据缺失：{theme_yaml}，按无父级处理。")
        return None
    try:
        with open(theme_yaml, "r", encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as exc:
        print(f"[警告] 主题元数据解析失败 {theme_yaml}（{exc}），按无父级处理。")
        return None
    parent = meta.get("parent")
    return str(parent) if parent else None


def resolve_theme_chain(config: Config) -> List[Path]:
    """解析配置主题的继承链（子在前、父在后）。

    Args:
        config: 全局配置对象。

    Returns:
        List[Path]: 按子级优先排序的主题目录列表；解析失败时回退到
            ``default`` 主题，若 default 也不存在则返回空列表。
    """
    chain: List[Path] = []
    current_name = config.build.theme
    visited: set[str] = set()

    while current_name and current_name not in visited:
        visited.add(current_name)
        theme_dir = (config.root_dir / "themes" / current_name).resolve()
        if not theme_dir.is_dir():
            print(f"[警告] 未找到主题目录 {theme_dir}，已回退到默认主题 {DEFAULT_THEME_NAME}。")
            current_name = DEFAULT_THEME_NAME
            continue
        chain.append(theme_dir)
        current_name = _read_parent(theme_dir / "theme.yaml")

    if not chain:
        default_dir = (config.root_dir / "themes" / DEFAULT_THEME_NAME).resolve()
        print(f"[警告] 主题继承链解析失败，尝试内置默认主题 {default_dir}。")
        if default_dir.is_dir():
            chain = [default_dir]

    if chain:
        names = " -> ".join(p.name for p in chain)
        print(f"[信息] 主题继承链：{names}")
    return chain


class JinjaRenderer:
    """Jinja2 模板渲染器。

    Attributes:
        env: 配置完成的 Jinja2 环境实例。
        theme_paths: 参与模板解析的主题目录列表（子级优先）。
    """

    def __init__(self, theme_paths: Sequence[Path]) -> None:
        """初始化渲染器。

        Args:
            theme_paths: 主题目录列表，顺序为子级优先。

        Raises:
            RuntimeError: 所有主题目录均缺少 ``templates`` 子目录时抛出
                （错误信息为中文，供上层捕获展示）。
        """
        self.theme_paths = list(theme_paths)
        template_dirs = [
            p / "templates" for p in self.theme_paths if (p / "templates").is_dir()
        ]
        if not template_dirs:
            raise RuntimeError(
                "未找到任何主题模板目录，请检查 config.yaml 中 build.theme 配置。"
            )

        self.env = Environment(
            loader=ChoiceLoader([FileSystemLoader(str(d)) for d in template_dirs]),
            autoescape=True,
        )
        self.env.filters["dateformat"] = _dateformat
        self.env.globals["url_for"] = _url_for
        self.env.globals["now"] = datetime.now()

    def render(self, template_name: str, **context: Any) -> str:
        """渲染指定模板。

        Args:
            template_name: 模板名（如 ``index.html``），沿主题链查找。
            **context: 注入模板的上下文变量。

        Returns:
            str: 渲染完成的 HTML 字符串。

        Raises:
            TemplateSyntaxError: 模板存在但语法错误时向上抛出。
        """
        try:
            template = self.env.get_template(template_name)
        except TemplateNotFound:
            print(f"[警告] 主题模板 {template_name} 不存在，已回退渲染为空内容。")
            return ""
        return template.render(**context)

    def site_context(self, config: Config) -> Dict[str, Any]:
        """构造注入模板的站点全局上下文。

        Args:
            config: 全局配置对象。

        Returns:
            Dict[str, Any]: 含 ``site`` 键的上下文字典。
        """
        return build_site_context(config)