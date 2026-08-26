import datetime
import enum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class AdminRole(str, enum.Enum):
    """Пресет прав, применяемый одним кликом при создании админа.
    Реальная проверка прав всегда идёт через Permission/AdminPermission,
    роль — это только удобный ярлык + значение по умолчанию для UI."""

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    OBSERVER = "observer"
    SUPPORT = "support"


class Permission(str, enum.Enum):
    """Полный справочник прав в системе. Хранится как строка в БД
    (через AdminPermission), а не как отдельная таблица-справочник —
    добавление нового права не требует миграции данных, только новое
    значение enum."""

    # Просмотр (доступно даже наблюдателю)
    VIEW_DASHBOARD = "view_dashboard"
    VIEW_USERS = "view_users"
    VIEW_SUBSCRIPTIONS = "view_subscriptions"
    VIEW_PAYMENTS = "view_payments"

    # Управление пользователями/подписками (базовый админ)
    ISSUE_SUBSCRIPTION = "issue_subscription"      # ручная выдача/продление
    REVOKE_SUBSCRIPTION = "revoke_subscription"     # ручной отзыв/активация
    MANAGE_USER_BALANCE = "manage_user_balance"     # ручная выдача/списание бонусного баланса

    # Удаление записей подписок (ручное и массовое по периоду) —
    # НЕ делегируемое право: жёстко доступно только роли SUPER_ADMIN
    # (см. require_super_admin в auth.py), в списке чекбоксов не
    # показывается вообще.

    # Техподдержка
    VIEW_SUPPORT_TICKETS = "view_support_tickets"
    MANAGE_SUPPORT_TICKETS = "manage_support_tickets"  # отвечать/закрывать/удалять

    # Тарифы и рассылки (обычно только супер-админ, но право отдельное —
    # можно выдать и обычному админу точечно)
    MANAGE_TARIFFS = "manage_tariffs"
    BROADCAST_MESSAGE = "broadcast_message"
    MANAGE_REFERRALS = "manage_referrals"

    # Управление списком vless/hy2-ссылок, которые сервер отдаёт в
    # подписке (пул рабочих + запасные/dead-ссылки)
    MANAGE_VLESS_LINKS = "manage_vless_links"

    # Только супер-админ
    MANAGE_ADMINS = "manage_admins"
    VIEW_AUDIT_LOG = "view_audit_log"
    MANAGE_SERVER_SETTINGS = "manage_server_settings"  # задел на будущее


# Пресеты: какие права получает админ при выборе роли в UI.
# Дальше супер-админ может донастроить вручную — это только стартовый набор.
ROLE_DEFAULT_PERMISSIONS: dict[AdminRole, set[Permission]] = {
    AdminRole.OBSERVER: {
        Permission.VIEW_DASHBOARD,
        Permission.VIEW_USERS,
        Permission.VIEW_SUBSCRIPTIONS,
        Permission.VIEW_PAYMENTS,
    },
    AdminRole.ADMIN: {
        Permission.VIEW_DASHBOARD,
        Permission.VIEW_USERS,
        Permission.VIEW_SUBSCRIPTIONS,
        Permission.VIEW_PAYMENTS,
        Permission.ISSUE_SUBSCRIPTION,
        Permission.REVOKE_SUBSCRIPTION,
        Permission.VIEW_SUPPORT_TICKETS,
        Permission.MANAGE_SUPPORT_TICKETS,
    },
    AdminRole.SUPPORT: {
        Permission.VIEW_DASHBOARD,
        Permission.VIEW_SUPPORT_TICKETS,
        Permission.MANAGE_SUPPORT_TICKETS,
    },
    AdminRole.SUPER_ADMIN: set(Permission),  # вообще все права
}


# Иерархия ролей: чем больше число, тем выше ранг. Используется ТОЛЬКО для
# решений "кто кем может управлять" (создание/редактирование/деактивация
# админов) — обычные Permission по-прежнему решают доступ к остальным
# разделам панели. Это отдельная ось, потому что Permission — плоский набор
# флагов и сам по себе не знает про "выше/ниже/равно".
ROLE_RANK: dict[AdminRole, int] = {
    AdminRole.OBSERVER: 0,
    AdminRole.SUPPORT: 1,
    AdminRole.ADMIN: 2,
    AdminRole.SUPER_ADMIN: 3,
}


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True)

    login: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))

    role: Mapped[AdminRole] = mapped_column(Enum(AdminRole))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Деактивация вместо удаления — чтобы не терять audit log по этому
    # админу (FK на удалённую строку сломает историю действий).

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(), default=datetime.datetime.now
    )
    last_login_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(), nullable=True
    )

    permissions: Mapped[list["AdminPermission"]] = relationship(
        back_populates="admin",
        cascade="all, delete-orphan",
    )

    def has_permission(self, permission: Permission) -> bool:
        if not self.is_active:
            return False
        return any(p.permission == permission for p in self.permissions)

    # ------------------------------------------------------------------
    # Иерархия ролей: кто кем может управлять в разделе "Админы".
    # Единственное место, где принимается это решение — не дублировать
    # эту логику по роутам, а всегда вызывать эти методы.
    # ------------------------------------------------------------------

    def outranks(self, other: "AdminUser") -> bool:
        """Строго выше по рангу, чем other."""
        return ROLE_RANK[self.role] > ROLE_RANK[other.role]

    def can_manage(self, target: "AdminUser") -> bool:
        """Может редактировать/деактивировать учётку target.

        Супер-админ управляет всеми, включая других супер-админов —
        это единственная роль, которой намеренно доверяем полностью.
        Все остальные роли могут управлять только строго нижестоящими
        по рангу — не собой и не равными/старшими себе. Это закрывает
        и горизонтальную (тот же ранг), и вертикальную (ранг выше)
        эскалацию прав через редактирование чужой учётки.
        """
        if self.role == AdminRole.SUPER_ADMIN:
            return True
        return self.outranks(target)

    def can_grant_role(self, role: "AdminRole") -> bool:
        """Может назначить эту роль (при создании или редактировании).

        Правило то же: супер-админ может назначить любую роль, остальные —
        только строго ниже своей собственной. Так обычный admin не может
        создать второго admin (тот же ранг) или super_admin (ранг выше).
        """
        if self.role == AdminRole.SUPER_ADMIN:
            return True
        return ROLE_RANK[role] < ROLE_RANK[self.role]

    def can_grant_permission(self, permission: Permission) -> bool:
        """Нельзя выдать другому право, которого не имеешь сам —
        иначе можно обойти собственные ограничения, выдав его кому-то
        подконтрольному (или самому себе на другом аккаунте)."""
        if self.role == AdminRole.SUPER_ADMIN:
            return True
        return self.has_permission(permission)


class AdminPermission(Base):
    """Конкретное право, выданное конкретному админу.
    many-to-many между AdminUser и Permission, но через явную таблицу
    (а не association table) — чтобы потом можно было добавить, например,
    granted_by/granted_at без миграции структуры."""

    __tablename__ = "admin_permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("admin_users.id"), index=True)

    permission: Mapped[Permission] = mapped_column(Enum(Permission))

    admin: Mapped["AdminUser"] = relationship(back_populates="permissions")


class AuditLog(Base):
    """Журнал действий админов. Пишется на каждое изменяющее действие
    (не на просмотр — иначе таблица разрастётся без пользы)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("admin_users.id"), index=True)

    action: Mapped[str] = mapped_column(String(64))
    # например: "issue_subscription", "delete_user", "create_admin"

    target: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # что именно изменили, например "user_id=123" или "admin login=ivan"

    details: Mapped[str | None] = mapped_column(Text(), nullable=True)
    # произвольный JSON/текст с деталями (было/стало), если нужно

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(), default=datetime.datetime.now
    )

    admin: Mapped["AdminUser"] = relationship()


class BroadcastStatus(str, enum.Enum):
    DRAFT = "draft"          # настроена, но ещё не отправляется — можно править/удалить
    SENDING = "sending"      # фоновая задача рассылки сейчас идёт
    COMPLETED = "completed"  # отправка завершена (успешно или частично, см. failed_count)


class BroadcastAudience(str, enum.Enum):
    """Базовый сегмент получателей. Комбинируется с необязательными
    доп.фильтрами (tariff_filter, registered_from/to) через AND —
    так из небольшого набора примитивов собирается гибкая аудитория,
    не разрастаясь в отдельный конструктор запросов."""

    ALL = "all"                                  # все пользователи бота
    ACTIVE_SUBSCRIPTION = "active_subscription"   # подписка сейчас действует
    NO_ACTIVE_SUBSCRIPTION = "no_active_subscription"  # истекла или не было
    NEVER_SUBSCRIBED = "never_subscribed"          # вообще ни разу не оформляли
    PAYING = "paying"                              # хотя бы раз реально платили


class Broadcast(Base):
    """Одна рассылка: настройки аудитории/сообщения + прогресс отправки.
    Черновик можно донастраивать и удалить; после запуска — только
    смотреть прогресс и результат, история сохраняется."""

    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("admin_users.id"), index=True)

    # --- содержимое сообщения ---
    text: Mapped[str] = mapped_column(Text())
    parse_mode: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # "HTML" — форматирование включено, None — как есть (без разметки)

    photo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # имя файла в BROADCAST_MEDIA_DIR, если к сообщению приложено фото

    button_text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    button_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # необязательная одна инлайн-кнопка под сообщением

    # --- аудитория ---
    audience: Mapped[BroadcastAudience] = mapped_column(Enum(BroadcastAudience))
    tariff_filter: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # доп.фильтр: только те, у кого была оплата с этим tariff_key (см.
    # app.settings.tariffs.TARIFFS); None — без фильтра по тарифу
    registered_from: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(), nullable=True
    )
    registered_to: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(), nullable=True
    )

    # --- статус/прогресс ---
    status: Mapped[BroadcastStatus] = mapped_column(
        Enum(BroadcastStatus), default=BroadcastStatus.DRAFT
    )
    total_recipients: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(), default=datetime.datetime.now
    )
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(), nullable=True
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(), nullable=True
    )

    admin: Mapped["AdminUser"] = relationship()

    @property
    def progress_percent(self) -> int:
        if not self.total_recipients:
            return 0
        done = self.sent_count + self.failed_count
        return min(100, round(done * 100 / self.total_recipients))
