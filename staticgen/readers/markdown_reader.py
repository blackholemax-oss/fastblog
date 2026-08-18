"""Markdown 内容解析引擎。

负责递归扫描 ``content`` 目录，解析 Frontmatter（YAML/TOML）元数据，
并通过 Python-Markdown 扩展（Tables / CodeHilite / TOC）将正文渲染为
HTML，最终产出 :class:`Post` dataclass 对象列表。

解析失败的文件会被跳过并打印中文警告，保证单篇文章损坏不影响整体构建。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import frontmatter
import markdown

MARKDOWN_EXTENSIONS = ("extra", "codehilite", "toc")

EXTENSION_CONFIGS = {
    "codehilite": {
        "guess_lang": False,
        "css_class": "highlight",
        "use_pygments": True,
    },
    "toc": {
        "permalink": False,
    },
}

MARKDOWN_SUFFIXES = (".md", ".markdown", ".mdown")

_SLUG_RE = re.compile(r"[^a-zA-Z0-9\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+")


def _slugify(value: str, fallback: str) -> str:
    """将标题转换为 URL 友好的 slug，中文按原样保留。

    Args:
        value: 待转换的原始标题。
        fallback: 转换结果为空时使用的回退值（通常为文件名）。

    Returns:
        str: 转换后的 slug。
    """
    slug = _SLUG_RE.sub("-", value.strip()).strip("-")
    return slug or fallback


def _parse_date(value: Any) -> Optional[date]:
    """将 Frontmatter 中的日期字段解析为 ``date`` 对象。

    支持 ``datetime`` / ``date`` 实例及多种常见字符串格式，
    解析失败时返回 ``None``（不阻断构建）。

    Args:
        value: 原始日期值。

    Returns:
        Optional[date]: 解析成功返回日期对象，否则返回 ``None``。
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for fmt in (
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y%m%d",
        ):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
    return None


def _create_markdown() -> markdown.Markdown:
    """创建配置完成的 Markdown 转换器实例。

    Returns:
        markdown.Markdown: 已启用 Tables / CodeHilite / TOC 扩展的转换器。
    """
    return markdown.Markdown(
        extensions=list(MARKDOWN_EXTENSIONS),
        extension_configs=EXTENSION_CONFIGS,
    )


@dataclass
class Post:
    """一篇博客文章的解析结果。

    Attributes:
        title: 文章标题（取自 Frontmatter，缺失时回退为文件名）。
        slug: URL 标识（取自 Frontmatter，缺失时由标题生成）。
        source_path: 源 Markdown 文件的绝对路径。
        relative_path: 相对内容目录的路径（POSIX 风格）。
        date: 发布日期，无法解析时为 ``None``。
        tags: 标签列表。
        summary: 摘要（Frontmatter 的 summary/description）。
        html: 渲染后的 HTML 正文。
        toc: TOC 扩展生成的目录 HTML。
        raw_content: 去除 Frontmatter 后的原始 Markdown 正文。
        meta: 完整的原始元数据字典。
    """

    title: str
    slug: str
    source_path: Path
    relative_path: str
    date: Optional[date] = None
    tags: List[str] = field(default_factory=list)
    summary: str = ""
    html: str = ""
    toc: str = ""
    raw_content: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)


def scan_content(content_dir: Path) -> List[Path]:
    """递归扫描内容目录，收集全部 Markdown 文件。

    Args:
        content_dir: 内容目录绝对路径。

    Returns:
        List[Path]: 按路径排序的 Markdown 文件列表；目录不存在或
            扫描失败时返回空列表并打印中文警告。
    """
    if not content_dir.exists():
        print(f"[警告] 内容目录不存在：{content_dir}，本次扫描结果为空。")
        return []
    try:
        return sorted(
            p
            for p in content_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in MARKDOWN_SUFFIXES
        )
    except OSError as exc:
        print(f"[警告] 扫描内容目录失败（{exc}），本次扫描结果为空。")
        return []


def parse_post(source: Path, content_dir: Path) -> Optional[Post]:
    """解析单个 Markdown 文件为 :class:`Post` 对象。

    使用 ``python-frontmatter`` 提取 YAML/TOML 元数据，
    元数据缺失的字段全部回退到合理默认值。

    Args:
        source: 源 Markdown 文件路径。
        content_dir: 内容目录绝对路径（用于计算相对路径）。

    Returns:
        Optional[Post]: 解析成功返回文章对象；文件无法读取或
            格式损坏时打印中文警告并返回 ``None``。
    """
    try:
        with open(source, "r", encoding="utf-8") as f:
            fm = frontmatter.load(f)
    except (OSError, ValueError) as exc:
        print(f"[警告] 跳过无法解析的文件 {source}：{exc}")
        return None

    meta: Dict[str, Any] = dict(fm.metadata) if fm.metadata else {}
    title = str(meta.get("title") or source.stem)
    slug = str(meta.get("slug") or _slugify(title, source.stem))

    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    try:
        rel = source.resolve().relative_to(content_dir.resolve())
    except ValueError:
        rel = Path(source.name)
    rel_str = str(rel).replace("\\", "/")

    return Post(
        title=title,
        slug=slug,
        source_path=source.resolve(),
        relative_path=rel_str,
        date=_parse_date(meta.get("date")),
        tags=[str(t) for t in tags],
        summary=str(meta.get("summary") or meta.get("description") or ""),
        raw_content=fm.content,
        meta=meta,
    )


def render_post(post: Post) -> Post:
    """将文章正文渲染为 HTML（表格 / 代码高亮 / 目录）。

    Args:
        post: 待渲染的文章对象（原地修改其 ``html`` 与 ``toc`` 字段）。

    Returns:
        Post: 渲染完成后的文章对象。
    """
    md = _create_markdown()
    try:
        post.html = md.convert(post.raw_content)
        post.toc = str(getattr(md, "toc", "") or "")
    except Exception as exc:
        print(f"[警告] 渲染文章《{post.title}》失败（{exc}），HTML 内容为空。")
        post.html = ""
        post.toc = ""
    return post


def read_posts(content_dir: Path) -> List[Post]:
    """读取内容目录下的全部文章。

    依次执行扫描、解析与渲染，并按日期降序排列（无日期的文章排最后）。

    Args:
        content_dir: 内容目录绝对路径。

    Returns:
        List[Post]: 按日期降序排列的文章列表。
    """
    posts: List[Post] = []
    for path in scan_content(content_dir):
        post = parse_post(path, content_dir)
        if post is None:
            continue
        render_post(post)
        posts.append(post)
    posts.sort(key=lambda p: p.date or date.min, reverse=True)
    return posts