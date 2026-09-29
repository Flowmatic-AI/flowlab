from app.models import User
from flowlab import MCPRouter
from flowlab.modules.auth import CurrentMCPUser

router = MCPRouter("app")


@router.tool
def greet(name: str) -> str:
    return f"Hello, {name}!"


@router.tool
def dashboard(user: User = CurrentMCPUser()) -> str:
    """Greet the user who owns the calling API key, like GET /me."""
    return f"Hello, {user.email}!"
