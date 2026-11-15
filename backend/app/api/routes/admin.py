import uuid

from fastapi import APIRouter, status

from app.api.deps import AdminSession, AdminUserServiceDep, CsrfSession
from app.api.schemas.admin import AdminUserCreate, AdminUserOut, AdminUserUpdate, PasswordChange

router = APIRouter(prefix="/api/admin/users", tags=["admin"])


@router.get("", response_model=list[AdminUserOut])
async def list_users(_admin: AdminSession, service: AdminUserServiceDep) -> list[AdminUserOut]:
    return [AdminUserOut.model_validate(user) for user in await service.list_users()]


@router.post("", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: AdminUserCreate,
    _admin: AdminSession,
    _csrf: CsrfSession,
    service: AdminUserServiceDep,
) -> AdminUserOut:
    user = await service.create_user(body.email, body.password.get_secret_value(), body.role)
    return AdminUserOut.model_validate(user)


@router.patch("/{user_id}", response_model=AdminUserOut)
async def update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdate,
    admin: AdminSession,
    _csrf: CsrfSession,
    service: AdminUserServiceDep,
) -> AdminUserOut:
    user = await service.update_user(
        admin.user.id, user_id, role=body.role, is_active=body.is_active
    )
    return AdminUserOut.model_validate(user)


@router.put("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    user_id: uuid.UUID,
    body: PasswordChange,
    _admin: AdminSession,
    _csrf: CsrfSession,
    service: AdminUserServiceDep,
) -> None:
    await service.change_password(user_id, body.password.get_secret_value())


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    admin: AdminSession,
    _csrf: CsrfSession,
    service: AdminUserServiceDep,
) -> None:
    await service.delete_user(admin.user.id, user_id)
