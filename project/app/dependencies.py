from typing import Annotated

from app.models import User
from flowlab import Depends
from flowlab.modules.auth import get_session_user, get_user

CurrentUser = Annotated[User, Depends(get_user)]

SessionUser = Annotated[User, Depends(get_session_user)]
