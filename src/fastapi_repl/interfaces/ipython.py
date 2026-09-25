"""IPython interface with ``await`` running on the session loop."""

from __future__ import annotations

from typing import Any

from fastapi_repl.interfaces.base import Interface


class IPythonInterface(Interface):
    """IPython with ``autoawait`` wired to the shared event loop.

    IPython normally runs top-level ``await`` on its own private loop. We
    replace its ``loop_runner`` so every cell runs on the session loop, the
    same one that owns your database connections.
    """

    name = "ipython"
    display_name = "IPython"
    package = "IPython"
    distribution = "ipython"

    def build_app(self) -> Any:
        from IPython.terminal.ipapp import TerminalIPythonApp
        from traitlets.config import Config

        runtime = self.context.runtime

        def report(result: Any) -> None:
            if result.error_in_exec is not None:
                runtime.report_error(result.error_in_exec)

        class App(TerminalIPythonApp):
            # The runner must be in place before initialize() runs startup
            # files, exec_lines and -c code.
            def init_shell(self) -> None:
                super().init_shell()
                self.shell.autoawait = True
                self.shell.loop_runner = runtime.run
                self.shell.events.register("post_run_cell", report)

        config = Config()
        config.TerminalIPythonApp.display_banner = False
        config.InteractiveShell.autoawait = True
        app = App.instance(config=config, user_ns=self.context.namespace)
        app.initialize(list(self.context.loaded.config.ipython_arguments))
        return app

    def start(self) -> None:
        from IPython.terminal.ipapp import TerminalIPythonApp

        app = self.build_app()
        try:
            app.start()
        finally:
            shell_cls = type(app.shell) if app.shell is not None else None
            type(app).clear_instance()
            TerminalIPythonApp.clear_instance()
            if shell_cls is not None:
                shell_cls.clear_instance()
