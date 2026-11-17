from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.config import get_settings
from ...core.security import create_access_token, hash_password, verify_password
from ...db.database import get_db
from ...models import User
from ...schemas import ChangePasswordRequest, LoginRequest, TokenResponse, UserOut
from ...services.audit_service import log_audit
from ..deps import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


@router.post("/login", response_model=TokenResponse)
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    clean_username = credentials.username.strip()

    user = db.scalar(select(User).where(func.lower(User.username) == clean_username.lower()))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    if not verify_password(credentials.password, user.password_hash):
        log_audit(
            db=db,
            action="LOGIN_FAILED",
            entity_type="User",
            actor_username=clean_username,
            details={"reason": "Incorrect password"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Please contact the administrator.",
        )

    # Record last login timestamp (Section 9)
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    access_token = create_access_token(
        subject=user.id,
        role=user.role.value,
        extra_claims={
            "username": user.username,
            "display_name": user.display_name,
        },
    )

    log_audit(
        db=db,
        action="LOGIN_SUCCESS",
        entity_type="User",
        actor_username=user.username,
        actor_id=user.id,
        entity_id=user.id,
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        role=user.role.value,
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        must_change_password=user.must_change_password,
    )


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password verification failed.",
        )

    if len(body.new_password.strip()) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters long.",
        )

    current_user.password_hash = hash_password(body.new_password)
    current_user.must_change_password = False
    db.commit()

    log_audit(
        db=db,
        action="PASSWORD_CHANGED",
        entity_type="User",
        actor_username=current_user.username,
        actor_id=current_user.id,
        entity_id=current_user.id,
    )
    return {"message": "Password updated successfully."}



@router.post("/logout")
def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    log_audit(
        db=db,
        action="LOGOUT",
        entity_type="User",
        actor_username=current_user.username,
        actor_id=current_user.id,
        entity_id=current_user.id,
    )
    return {"message": "Logged out successfully."}


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
