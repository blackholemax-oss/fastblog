"""演示插件：展示 on_init / before_generate / after_generate 三个钩子的调用时机。

放置于项目根目录 ``plugins/`` 下，由引擎通过 ``importlib`` 按文件路径动态加载。
删除本文件即可移除演示行为。
"""

from pathlib import Path

from fastblog.plugins import Plugin, PluginContext


class HelloPlugin(Plugin):
    """极简演示插件，验证钩子触发顺序并输出日志。"""

    name = "hello-demo"

    def on_init(self, context: PluginContext) -> None:
        """插件加载后、内容解析前触发。"""
        print(f"[插件] {self.name}.on_init：已加载，当前文章数={len(context.posts)}")

    def before_generate(self, context: PluginContext) -> None:
        """文章解析完成后、渲染开始前触发。"""
        print(f"[插件] {self.name}.before_generate：即将渲染 {len(context.posts)} 篇文章")

    def after_generate(self, context: PluginContext) -> None:
        """渲染与静态资源处理完成后触发。"""
        note = Path(context.output_path) / "plugin-demo.txt"
        try:
            note.write_text("hello from plugin", encoding="utf-8")
        except OSError as exc:
            print(f"[插件] {self.name}.after_generate 写入文件失败（{exc}）。")
            return
        print(f"[插件] {self.name}.after_generate：已生成 {note.name}")