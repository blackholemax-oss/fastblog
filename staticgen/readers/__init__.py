"""内容读取与解析子包。

对外暴露 :func:`read_posts` 与 :class:`Post`，供引擎层统一调用。
"""

from staticgen.readers.markdown_reader import Post, read_posts, render_post

__all__ = ["Post", "read_posts", "render_post"]