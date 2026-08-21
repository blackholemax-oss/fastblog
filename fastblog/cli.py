"""命令行入口。

通过 ``argparse`` 提供 ``build`` 与 ``serve`` 两个子命令：

- ``build``：加载配置并触发静态站点生成（内容引擎在后续阶段接入）。
- ``serve``：启动本地 HTTP 服务预览 ``output`` 目录。

示例::

    python -m fastblog.cli build
    python -m fastblog.cli serve --port 9000
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fastblog.config import load_config
from fastblog.deploy import GitHubDeployer
from fastblog.engine import BlogGenerator


def _build_site(config) -> int:
    """仅生成静态站点，不触发自动部署。

    Args:
        config: 全局配置对象。

    Returns:
        int: 生成的文章数量。
    """
    return BlogGenerator(config).generate()


def _build(args: argparse.Namespace) -> int:
    """执行站点构建流程。

    构建完成后，若 ``deploy.enabled`` 开启则自动推送部署。

    Args:
        args: 解析后的命令行参数（含 ``--config``）。

    Returns:
        int: 进程退出码，0 表示成功。
    """
    config = load_config(Path(args.config) if args.config else None)

    try:
        count = _build_site(config)
        if config.deploy.enabled:
            GitHubDeployer(config).deploy()
    except RuntimeError as exc:
        print(f"[错误] 构建失败：{exc}")
        return 1
    print(f"[信息] 构建完成：共生成 {count} 篇文章到 {config.output_path()}。")
    return 0


def _deploy(args: argparse.Namespace) -> int:
    """构建站点并推送到远程 GitHub 仓库。

    构建后自动恢复 Pages 工作流（``output/.github/workflows/pages.yml``），
    提交全部变更并强制推送到配置的远程分支（``deploy.branch``），
    由 GitHub Actions 完成线上发布。

    Args:
        args: 解析后的命令行参数（含 ``--config``、``--message``）。

    Returns:
        int: 进程退出码，0 表示成功。
    """
    config = load_config(Path(args.config) if args.config else None)

    try:
        count = BlogGenerator(config).generate()
        GitHubDeployer(config).deploy(args.message)
    except RuntimeError as exc:
        print(f"[错误] 部署失败：{exc}")
        return 1
    print(f"[信息] 部署完成：{count} 篇文章已同步至远端。")
    return 0


def _serve_static(config, host: str, port: int, args: argparse.Namespace) -> int:
    """以纯静态方式启动本地预览服务。

    Args:
        config: 全局配置对象。
        host: 监听地址。
        port: 监听端口。
        args: 解析后的命令行参数（用于 ``--no-browser``）。

    Returns:
        int: 进程退出码，0 表示成功。
    """
    directory = config.output_path()

    if not directory.exists():
        print(f"[错误] 输出目录不存在：{directory}，请先运行 build 生成站点。")
        return 1

    class Handler(SimpleHTTPRequestHandler):
        """绑定输出目录的静态文件处理器。"""

        def __init__(self, *handler_args, **handler_kwargs) -> None:
            super().__init__(*handler_args, directory=str(directory), **handler_kwargs)

        def log_message(self, fmt: str, *fmt_args) -> None:  # noqa: A003
            """精简访问日志输出。"""
            print(f"[请求] {self.address_string()} {fmt % fmt_args}")

    try:
        server = ThreadingHTTPServer((host, port), Handler)
    except OSError as exc:
        print(f"[错误] 无法在 {host}:{port} 启动服务（{exc}），请检查端口是否被占用。")
        return 1

    url = f"http://{host}:{port}/"
    print(f"[信息] 预览服务已启动：{url} （Ctrl+C 停止）")
    if config.serve.open_browser and not args.no_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[信息] 预览服务已停止。")
    finally:
        server.server_close()
    return 0


def _serve_watch(config, host: str, port: int, args: argparse.Namespace) -> int:
    """以热部署方式启动本地预览服务。

    使用 livereload 监听 ``content`` / ``themes`` / ``plugins`` /
    ``config.yaml`` 变更，文件变化后自动重新构建并刷新浏览器。

    Args:
        config: 全局配置对象。
        host: 监听地址。
        port: 监听端口。
        args: 解析后的命令行参数（用于 ``--no-browser``）。

    Returns:
        int: 进程退出码，0 表示成功。
    """
    try:
        from livereload import Server
    except ImportError:
        print(
            "[错误] 热部署需要 livereload 依赖，"
            "请先执行：pip install -r requirements.txt"
        )
        return 1

    directory = config.output_path()
    try:
        count = _build_site(config)
        print(f"[信息] 初始构建完成：共生成 {count} 篇文章到 {directory}。")
    except RuntimeError as exc:
        print(f"[错误] 初始构建失败：{exc}")
        return 1

    server = Server()
    root = config.root_dir

    def rebuild() -> None:
        """文件变更后的构建回调。"""
        try:
            count = _build_site(config)
        except RuntimeError as exc:
            print(f"[警告] 自动构建失败：{exc}")
            return
        print(f"[信息] 检测到变更，已自动构建：共生成 {count} 篇文章到 {directory}。")

    watch_paths = [
        config.content_path(),
        root / "themes",
        root / "plugins",
        root / "config.yaml",
    ]
    for path in watch_paths:
        if path.exists():
            server.watch(str(path), rebuild)

    url = f"http://{host}:{port}/"
    print(
        f"[信息] 热部署预览服务已启动：{url} "
        "（文件变更后自动构建并刷新浏览器，Ctrl+C 停止）"
    )
    try:
        server.serve(
            port=port,
            host=host,
            root=str(directory),
            open_url_delay=1 if (config.serve.open_browser and not args.no_browser) else None,
        )
    except KeyboardInterrupt:
        print("\n[信息] 热部署预览服务已停止。")
    except OSError as exc:
        print(f"[错误] 无法在 {host}:{port} 启动服务（{exc}），请检查端口是否被占用。")
        return 1
    return 0


def _serve(args: argparse.Namespace) -> int:
    """启动本地预览服务。

    Args:
        args: 解析后的命令行参数（含 ``--config``、``--host``、``--port``、
            ``--watch``）。

    Returns:
        int: 进程退出码，0 表示成功。
    """
    config = load_config(Path(args.config) if args.config else None)

    host = args.host or config.serve.host
    port = args.port or config.serve.port

    if args.watch:
        return _serve_watch(config, host, port, args)
    return _serve_static(config, host, port, args)


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。

    Returns:
        argparse.ArgumentParser: 配置完成的解析器。
    """
    parser = argparse.ArgumentParser(
        prog="fastblog",
        description="fastblog —— 将 Markdown 渲染为静态 HTML 网站的生成器。",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="配置文件路径（默认自动查找项目根目录 config.yaml）。",
    )
    parser.add_argument("--version", action="version", version="fastblog 0.1.0")

    subparsers = parser.add_subparsers(dest="command", required=True, help="可用子命令")

    build_parser_ = subparsers.add_parser("build", help="生成静态站点到 output 目录")
    build_parser_.set_defaults(func=_build)

    serve_parser = subparsers.add_parser("serve", help="本地预览生成的站点")
    serve_parser.add_argument("--host", default=None, help="监听地址（默认取配置）")
    serve_parser.add_argument("--port", type=int, default=None, help="监听端口（默认取配置）")
    serve_parser.add_argument(
        "--watch",
        action="store_true",
        help="启用热部署：监听 content/themes/plugins/config.yaml，变更后自动构建并刷新浏览器",
    )
    serve_parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    serve_parser.set_defaults(func=_serve)

    deploy_parser = subparsers.add_parser("deploy", help="构建并强制推送到远程 GitHub 仓库")
    deploy_parser.add_argument("--message", default=None, help="自定义提交信息")
    deploy_parser.set_defaults(func=_deploy)

    return parser


def main(argv: list[str] | None = None) -> int:
    """命令行主入口。

    Args:
        argv: 命令行参数列表，为 ``None`` 时取 ``sys.argv[1:]``。

    Returns:
        int: 进程退出码。
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())