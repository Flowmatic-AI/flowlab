import logging

from app.models import User
from flowlab import get_db
from flowlab.modules.queue import job

logger = logging.getLogger(__name__)


@job(tries=3, backoff=10)
def welcome_user(user_id: int) -> None:
    """Queue it with ``welcome_user.dispatch(user.id)``; a worker (``python main.py queue:work``) runs it."""
    user = get_db().select_models(User).where_equals("id", user_id).fetch_model()

    if user is None:
        return  # deleted before the job ran

    logger.info("Welcome, %s!", user.email)
