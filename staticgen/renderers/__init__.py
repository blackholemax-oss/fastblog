"""主题渲染子包。

对外暴露 :class:`JinjaRenderer`、主题链解析函数
:func:`resolve_theme_chain` 与站点上下文构造函数 :func:`build_site_context`。
"""

from staticgen.renderers.jinja_renderer import (
    JinjaRenderer,
    build_site_context,
    resolve_theme_chain,
)

__all__ = ["JinjaRenderer", "resolve_theme_chain", "build_site_context"]