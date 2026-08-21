"""核心生成器。

:class:`BlogGenerator` 编排完整的站点生成流程：

1. 解析内容目录中的全部 Markdown 文章；
2. 解析主题继承链并初始化 Jinja2 渲染器；
3. 清空输出目录（保证幂等），渲染首页与各文章页；
4. 拷贝主题静态资源（CSS/JS）至输出目录。

所有文件 IO 均包裹异常处理并输出用户友好的中文提示。
"""

from __future__ import annotations

import shutil
from importlib import util as importlib_util
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastblog.config import Config
from fastblog.plugins import Plugin, PluginContext
from fastblog.readers import Post, read_posts
from fastblog.renderers import JinjaRenderer, resolve_theme_chain, build_site_context


class BlogGenerator:
    """静态站点生成器。

    Attributes:
        config: 全局配置对象。
        plugins: 已加载的插件实例列表（Phase 4 接入动态加载）。
    """

    def __init__(self, config: Config) -> None:
        """初始化生成器。

        Args:
            config: 全局配置对象。
        """
        self.config = config
        self.plugins: List[Any] = []

    def _clean_output(self) -> None:
        """清空并重建输出目录，保证每次构建产物纯净（幂等性）。

        保留 ``.git`` 目录，避免破坏部署仓库的历史与远程配置。
        """
        output = self.config.output_path()
        try:
            if output.exists():
                for child in output.iterdir():
                    if child.name == ".git":
                        continue
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink()
            else:
                output.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RuntimeError(f"无法重置输出目录 {output}（{exc}）。") from exc

    def _write(self, target: Path, content: str) -> None:
        """以 UTF-8 写入文件，自动创建父目录。

        Args:
            target: 目标文件绝对路径。
            content: 文件内容。
        """
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as exc:
            raise RuntimeError(f"写入文件失败 {target}（{exc}）。") from exc

    def _copy_static(self, theme_paths: List[Path]) -> None:
        """将各主题的 ``static`` 目录合并拷贝到输出目录。

        主题链中子级优先，同名文件由后拷贝者覆盖。
        实现时先拷贝父主题、再拷贝子主题，确保子主题覆盖父主题。

        Args:
            theme_paths: 主题目录列表（子级优先）。
        """
        target = self.config.output_path() / "static"
        copied = 0
        for theme_dir in reversed(theme_paths):
            source = theme_dir / "static"
            if not source.is_dir():
                continue
            try:
                shutil.copytree(source, target, dirs_exist_ok=True)
                copied += 1
            except OSError as exc:
                print(f"[警告] 拷贝主题静态资源失败 {source}（{exc}）。")
        if copied:
            print(f"[信息] 已拷贝 {copied} 个主题的静态资源至 {target}。")

    def _load_plugins(self) -> None:
        """动态加载项目根目录 ``plugins/`` 下的插件。

        通过 ``importlib`` 按文件路径加载每个 ``*.py`` 文件，收集其中
        继承 :class:`Plugin` 的类并实例化。加载或初始化失败的插件
        仅打印中文警告并跳过，不影响其余插件与构建流程。
        """
        plugins_dir = self.config.root_dir / "plugins"
        if not plugins_dir.is_dir():
            print(f"[信息] 未找到插件目录 {plugins_dir}，跳过插件加载。")
            self.plugins = []
            return

        loaded: List[Plugin] = []
        for path in sorted(plugins_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                spec = importlib_util.spec_from_file_location(
                    f"fastblog_user_plugin_{path.stem}", path
                )
                if spec is None or spec.loader is None:
                    print(f"[警告] 无法解析插件文件 {path}，已跳过。")
                    continue
                module = importlib_util.module_from_spec(spec)
                spec.loader.exec_module(module)
            except Exception as exc:
                print(f"[警告] 加载插件文件 {path} 失败（{exc}），已跳过。")
                continue
            for _, obj in vars(module).items():
                if isinstance(obj, type) and issubclass(obj, Plugin) and obj is not Plugin:
                    try:
                        loaded.append(obj())
                    except Exception as exc:
                        print(
                            f"[警告] 初始化插件类 {obj.__name__} 失败（{exc}），已跳过。"
                        )
        self.plugins = loaded
        if loaded:
            names = "、".join(p.name for p in loaded)
            print(f"[信息] 已加载 {len(loaded)} 个插件：{names}")

    def _run_hook(self, hook_name: str, context: PluginContext) -> None:
        """按顺序触发所有已加载插件的指定钩子。

        Args:
            hook_name: 钩子方法名（on_init / before_generate / after_generate）。
            context: 插件上下文。
        """
        for plugin in self.plugins:
            handler = getattr(plugin, hook_name, None)
            if handler is None:
                continue
            try:
                handler(context)
            except Exception as exc:
                print(
                    f"[警告] 插件《{plugin.name}》钩子 {hook_name} 执行失败"
                    f"（{exc}），已忽略。"
                )

    def generate(self) -> int:
        """执行完整构建流程。

        流程：加载插件并触发 ``on_init`` → 解析文章 → 解析主题链 →
        清空输出目录 → 触发 ``before_generate`` → 渲染首页与文章页 →
        拷贝静态资源 → 触发 ``after_generate``。

        Returns:
            int: 生成的文章数量。

        Raises:
            RuntimeError: 主题缺失或输出目录无法写入时抛出中文错误信息。
        """
        self._load_plugins()

        output = self.config.output_path()
        site_dict = build_site_context(self.config)
        context = PluginContext(
            config=self.config,
            posts=[],
            output_path=output,
            site=site_dict["site"],
        )
        self._run_hook("on_init", context)

        posts = read_posts(self.config.content_path())
        context.posts = posts

        theme_paths = resolve_theme_chain(self.config)
        if not theme_paths:
            raise RuntimeError("未找到主题目录，请检查 config.yaml 中 build.theme 配置。")

        self._clean_output()
        renderer = JinjaRenderer(theme_paths)
        context.renderer = renderer

        self._run_hook("before_generate", context)
        posts = context.posts

        template_context = dict(site_dict)
        template_context["posts"] = posts

        self._write(output / "index.html", renderer.render("index.html", **template_context))

        posts_dir = output / "posts"
        for post in posts:
            page = renderer.render("post.html", post=post, **template_context)
            self._write(posts_dir / f"{post.slug}.html", page)

        self._copy_static(theme_paths)
        self._run_hook("after_generate", context)
        return len(posts)