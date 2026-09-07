"""
Создание первого супер-админа. Запускать один раз, вручную, на сервере:

    cd /opt/vpn-bot
    .venv/bin/python -m app.admin.seed

Дальше всех остальных админов создаём уже через саму панель — этот
скрипт нужен только для самого первого входа (иначе некому создать
первого админа через веб-интерфейс, который сам требует логина).
"""

import asyncio
import getpass

from sqlalchemy import select

from app.admin.auth import hash_password
from app.admin.models import (
    ROLE_DEFAULT_PERMISSIONS,
    AdminPermission,
    AdminRole,
    AdminUser,
)
from app.db import async_session, init_models


async def main() -> None:
    await init_models()

    print("=== Создание супер-админа Makwin VPN ===")
    login = input("Логин: ").strip()

    if len(login) < 3:
        print("Логин должен быть от 3 символов.")
        return

    password = getpass.getpass("Пароль (не отображается при вводе): ")
    password_confirm = getpass.getpass("Повторите пароль: ")

    if password != password_confirm:
        print("Пароли не совпадают.")
        return

    if len(password) < 8:
        print("Пароль должен быть от 8 символов.")
        return

    async with async_session() as session:
        existing = await session.execute(
            select(AdminUser).where(AdminUser.login == login)
        )
        if existing.scalar_one_or_none() is not None:
            print(f"Админ с логином '{login}' уже существует.")
            return

        admin = AdminUser(
            login=login,
            password_hash=hash_password(password),
            role=AdminRole.SUPER_ADMIN,
        )
        session.add(admin)
        await session.flush()

        for permission in ROLE_DEFAULT_PERMISSIONS[AdminRole.SUPER_ADMIN]:
            session.add(AdminPermission(admin_id=admin.id, permission=permission))

        await session.commit()

    print(f"\nГотово! Супер-админ '{login}' создан.")
    print("Заходите на https://<ваш-домен>/admin/login")


if __name__ == "__main__":
    asyncio.run(main())
