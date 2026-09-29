from app.models import User
from flowlab import AuthSettings, FlowLab
from routes import api, console, mcp

app = FlowLab(auth_settings=AuthSettings(), user_model=User)

app.include_router(api.router)
app.include_router(mcp.router)
app.include_router(console.router)

if __name__ == "__main__":
    app.run()
