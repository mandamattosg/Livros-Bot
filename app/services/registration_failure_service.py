from __future__ import annotations

from sqlalchemy.orm import Session

from app.logging import get_logger
from app.models.registration_failure import RegistrationFailure
from app.models.user import User

logger = get_logger(__name__)

_MAX_TEXT_LENGTH = 500


def _truncate(value: str | None) -> str | None:
    if value is None:
        return None
    return value[:_MAX_TEXT_LENGTH]


def record_registration_failure(
    db: Session,
    telegram_id: str | None,
    reason: str,
    link: str | None = None,
    detail: str | None = None,
) -> None:
    """Registra uma falha de cadastro sem nunca interromper o fluxo do usuário."""

    try:
        user_id = None
        if telegram_id:
            user = db.query(User).filter(User.telegram_id == str(telegram_id)).first()
            user_id = user.id if user else None

        db.add(
            RegistrationFailure(
                user_id=user_id,
                reason=reason,
                link=_truncate(link),
                detail=_truncate(detail),
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Não foi possível registrar a falha de cadastro (%s)", reason)
