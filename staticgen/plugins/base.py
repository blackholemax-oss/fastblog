"""插件基类与钩子定义。

插件通过在项目根目录 ``plugins/`` 下编写继承 :class:`Plugin` 的
Python 文件接入生成流程，引擎通过 ``importlib`` 动态加载并实例化。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from staticgen.config import Config
from staticgen.readers import Post
from staticgen.renderers import JinjaRenderer


@dataclass
class PluginContext:
    """插件钩子执行时携带的上下文对象。

    Attributes:
        config: 全局配置对象。
        posts: 当前文章列表；``before_generate`` 钩子可修改该列表，
            引擎在渲染阶段会采用修改后的最终值。
        output_path: 输出目录绝对路径。
        site: 注入模板的站点全局字典。
        renderer: 已初始化的 Jinja2 渲染器；创建前为 ``None``。
        extra: 插件间共享数据的自由存储区。
    """

    config: Config
    posts: List[Post]
    output_path: Path
    site: Dict[str, Any]
    renderer: Optional[JinjaRenderer] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class Plugin:
    """插件基类。

    子类通过重写以下钩子参与生成流程：

    - ``on_init``：插件加载后、内容解析前触发；
    - ``before_generate``：文章解析完成、页面渲染前触发；
    - ``after_generate``：页面渲染与静态资源拷贝完成后触发。

    任意钩子抛出的异常均会被引擎捕获并输出中文警告，不会中断构建。

    Attributes:
        name: 插件显示名，用于日志输出。
    """

    name: str = "anonymous-plugin"

    def on_init(self, context: PluginContext) -> None:
        """插件初始化钩子。

        Args:
            context: 插件上下文。
        """

    def before_generate(self, context: PluginContext) -> None:
        """内容解析完成、渲染开始前的钩子。

        Args:
            context: 插件上下文（可修改 ``context.posts`` 干预渲染）。
        """

    def after_generate(self, context: PluginContext) -> None:
        """渲染与静态资源处理完成后的钩子。

        Args:
            context: 插件上下文。
        """