class FlowLabError(RuntimeError):
    pass


class FlowLabNotInitialized(FlowLabError):
    def __init__(self) -> None:
        super().__init__("No FlowLab application has been initialized; create one with FlowLab(...) first")


class FlowLabAlreadyInitialized(FlowLabError):
    def __init__(self) -> None:
        super().__init__("A FlowLab application already exists; use FlowLab.instance() to reach it")


class NotConnected(FlowLabError):
    def __init__(self, resource: str) -> None:
        super().__init__(f"The {resource} is not connected; use it inside app.lifespan() or a running app")


class AuthNotEnabled(FlowLabError):
    def __init__(self) -> None:
        super().__init__("Auth is not enabled; pass auth_settings=AuthSettings() to FlowLab(...)")


class SchemaMismatch(FlowLabError):
    def __init__(self, module: str, missing: list[str], hint: str | None = None) -> None:
        self.missing = missing
        hint = hint or f"Run `{module}:install` to add its migrations, then `migrations:up`"
        super().__init__(f"The {module} module needs {', '.join(missing)}. {hint}")
