from app.dependencies import CurrentUser
from flowlab import APIRouter

router = APIRouter()


@router.get("/")
def welcome() -> dict[str, str]:
    return {"message": "Hello world"}


@router.get("/me")
def dashboard(user: CurrentUser) -> dict[str, str]:
    return {"email": user.email}
