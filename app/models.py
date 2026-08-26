import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Персональный uuid для xray/reality — один на аккаунт, не меняется
    # между продлениями подписки. Именно по нему сервер отличает
    # пользователей друг от друга и считает устройства.
    vless_uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True)

    # Реферальная программа: кто пригласил этого пользователя (по
    # ссылке вида t.me/bot?start=ref_<tg_id>, см. app.services.referral).
    # NULL — пришёл не по реферальной ссылке (или сам является "корнем").
    referred_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    # Бонус пригласившему начисляется один раз — за первую же успешную
    # оплату этого пользователя (любым способом). Флаг гасится сразу,
    # до выдачи бонуса, чтобы вебхук и фоновая сверка платежей не
    # продлили пригласившему дважды при почти одновременном срабатывании.
    referral_reward_given: Mapped[bool] = mapped_column(Boolean, default=False)

    # Каждый пользователь сам выбирает, в каком виде получать
    # реферальный бонус за СВОИХ приглашённых: "days" — дни к
    # подписке (как раньше), "balance" — процент от суммы оплаты
    # приглашённого на бонусный баланс (см. app.services.referral).
    referral_reward_mode: Mapped[str] = mapped_column(String(16), default="days")

    # Бонусный баланс в рублях — накапливается в режиме "balance".
    # Пока только копится и виден в боте/админке; списание баланса при
    # оплате — отдельная задача, ещё не реализована.
    balance: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(),
        default=datetime.datetime.now,
    )

    subscriptions: Mapped[list["Subscription"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    support_tickets: Mapped[list["SupportTicket"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    expiry: Mapped[datetime.datetime] = mapped_column(DateTime())

    # Лимит устройств для этого тарифа (2-10, задаётся при покупке)
    device_limit: Mapped[int] = mapped_column(Integer, default=3)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(),
        default=datetime.datetime.now,
    )

    user: Mapped["User"] = relationship(back_populates="subscriptions")

    @property
    def is_valid(self) -> bool:
        """Проверка активности подписки."""
        return self.is_active and self.expiry > datetime.datetime.now()


class VlessLink(Base):
    """Одна ссылка-конфиг (vless:// или hy2://), которую сервер отдаёт
    в списке подписки. Раньше эти ссылки лежали прямо в коде
    (app/vless_links.py), и правка требовала редактировать .py-файл на
    сервере и перезапускать процесс — одна опечатка ломала и бота, и
    API. Теперь список живёт в БД и правится через админку без
    перезапуска и без риска синтаксической ошибки.

    is_dead=True — это "запасные"/заглушечные ссылки (аналог DEAD_LINKS):
    отдаются вместо обычного списка, если токен подписки не найден или
    истёк. Обычные и dead-ссылки — раздельные наборы, не смешиваются.
    """

    __tablename__ = "vless_links"

    id: Mapped[int] = mapped_column(primary_key=True)

    url: Mapped[str] = mapped_column(Text())

    # Заметка для админа (например "DE fin6 WiFi") — не показывается
    # пользователю, только в списке в админке для удобства ориентации.
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_dead: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Порядок в списке подписки — меньше значит выше. При добавлении
    # новой ссылки без явной позиции ставится в конец своего набора
    # (обычные/dead считаются отдельно).
    position: Mapped[int] = mapped_column(Integer, default=0)

    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("vless_link_groups.id"),
        nullable=True,
        index=True,
    )

    group: Mapped["VlessLinkGroup | None"] = relationship(
        back_populates="links",
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(), default=datetime.datetime.now
    )


class VlessLinkGroup(Base):
    """Группа VLESS-ссылок."""

    __tablename__ = "vless_link_groups"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(100))

    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    is_dead: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        index=True,
    )

    position: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(),
        default=datetime.datetime.now,
    )

    links: Mapped[list["VlessLink"]] = relationship(
        back_populates="group",
    )


class Payment(Base):
    """История успешных оплат — для админки (раздел «Платежи») и
    статистики на дашборде. Пишется в момент successful_payment,
    отдельно от Subscription: подписка может быть продлена, а платёж —
    это просто зафиксированный факт транзакции."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    tariff_key: Mapped[str] = mapped_column(String(32))
    method: Mapped[str] = mapped_column(String(16))  # "stars" | "card" | "sbp" | "crypto"
    amount: Mapped[int] = mapped_column(Integer)  # в минимальных единицах метода
    days: Mapped[int] = mapped_column(Integer)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(), default=datetime.datetime.now
    )

    user: Mapped["User"] = relationship()


class PlategaPayment(Base):
    """Локальная запись о транзакции в Platega (карта или СБП) —
    заводится сразу при создании транзакции (status=PENDING), чтобы
    потом сопоставить вебхук (app.webhooks.platega) с пользователем и
    тарифом: сам Platega не возвращает наш payload в колбэке, только
    id транзакции.

    method: "card" | "sbp" — каким способом оплаты создана транзакция
    (разные paymentMethod в Platega, см. app.config), нужно чтобы
    вебхук записал правильный Payment.method и админка/статистика
    могли их различать."""

    __tablename__ = "platega_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)

    transaction_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    tariff_key: Mapped[str] = mapped_column(String(32))
    method: Mapped[str] = mapped_column(String(16), default="card")  # "card" | "sbp"

    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(), default=datetime.datetime.now
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(), default=datetime.datetime.now, onupdate=datetime.datetime.now
    )

    user: Mapped["User"] = relationship()


class SupportTicket(Base):
    """Обращение в поддержку. status: 'open' | 'closed'. Одно активное
    (open) обращение на пользователя за раз — новое можно создать после
    закрытия текущего. Сообщения (текст/вложения) живут отдельно в
    SupportMessage — это позволяет вести переписку внутри одного тикета."""

    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    status: Mapped[str] = mapped_column(String(16), default="open", index=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(), default=datetime.datetime.now
    )
    closed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="support_tickets")
    messages: Mapped[list["SupportMessage"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="SupportMessage.created_at",
    )

    @property
    def is_open(self) -> bool:
        return self.status == "open"


class SupportMessage(Base):
    """Одно сообщение внутри обращения. sender_type: 'user' | 'admin'.
    admin_id заполнен только для sender_type='admin'."""

    __tablename__ = "support_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("support_tickets.id"), index=True
    )

    sender_type: Mapped[str] = mapped_column(String(8))  # "user" | "admin"
    admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id"), nullable=True
    )

    text: Mapped[str | None] = mapped_column(String(4000), nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(), default=datetime.datetime.now
    )

    ticket: Mapped["SupportTicket"] = relationship(back_populates="messages")
    admin: Mapped["AdminUser | None"] = relationship()
    attachments: Mapped[list["SupportAttachment"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
    )


class SupportAttachment(Base):
    """Фото/видео, приложенные к сообщению. Файл скачивается ботом на
    диск (app/data/support_media/) сразу при получении — админ-панель
    отдаёт его со своего диска, без обращения к Telegram API."""

    __tablename__ = "support_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("support_messages.id"), index=True
    )

    media_type: Mapped[str] = mapped_column(String(8))  # "photo" | "video"
    file_path: Mapped[str] = mapped_column(String(255))  # относительный путь на диске

    message: Mapped["SupportMessage"] = relationship(back_populates="attachments")


class TariffPrice(Base):
    """Переопределение цены тарифа поверх статического значения из
    app.settings.tariffs.TARIFFS. NULL в card_price/stars_price —
    "не переопределено, использовать значение по умолчанию из кода";
    так админ может точечно вернуть тариф к дефолтной цене, просто
    очистив поле в форме, не трогая остальные тарифы.

    tariff_key — сам PK (а не отдельный id): на тариф ровно одна строка
    переопределения, отдельный id только добавил бы лишний JOIN."""

    __tablename__ = "tariff_prices"

    tariff_key: Mapped[str] = mapped_column(String(32), primary_key=True)

    card_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stars_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # NULL — цена при оплате бонусным балансом не переопределена,
    # используется card_price (эффективный, с учётом его же
    # переопределения). См. app.services.tariffs.get_tariffs().
    balance_price: Mapped[int | None] = mapped_column(Integer, nullable=True)

    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(), default=datetime.datetime.now, onupdate=datetime.datetime.now
    )


class AppSetting(Base):
    """Простой key-value справочник для мелких настроек, которые не
    заслуживают отдельной таблицы (например, размер реферального
    бонуса). См. app.services.settings."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))


class ReferralReward(Base):
    """Лог начисленных реферальных бонусов — по одной записи на
    вознаграждённого пригласившего (см. app.services.referral.
    maybe_reward_referrer, который срабатывает один раз на приглашённого
    пользователя — при его первой успешной оплате).

    reward_type фиксирует, В КАКОМ РЕЖИМЕ был начислен именно этот
    бонус (режим мог быть переключён пригласившим до или после этого
    начисления — история не должна "переезжать" вслед за текущей
    настройкой). При reward_type="days" заполнен bonus_days, при
    "balance" — bonus_balance; второе поле в обоих случаях NULL/0."""

    __tablename__ = "referral_rewards"

    id: Mapped[int] = mapped_column(primary_key=True)

    referrer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    referred_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    reward_type: Mapped[str] = mapped_column(String(16), default="days")  # "days" | "balance"
    bonus_days: Mapped[int] = mapped_column(Integer, default=0)
    bonus_balance: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(), default=datetime.datetime.now
    )

    referrer: Mapped["User"] = relationship(foreign_keys=[referrer_id])
    referred_user: Mapped["User"] = relationship(foreign_keys=[referred_user_id])
