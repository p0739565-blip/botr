"""
Разбор человекочитаемого имени сервера, зашитого в саму ссылку-конфиг.

У vless://.../hy2://... ссылок есть фрагмент (часть после #) — именно
он показывается как имя сервера в клиентских VPN-приложениях (v2rayNG,
Happ, Shadowrocket и т.п.). Раньше в админке вместо этого показывался
обрезанный кусок сырой ссылки — не читается и не даёт понять, какой
это сервер, пока не откроешь на редактирование.

Формат ссылок не привязан к конкретному протоколу (vless://, hy2://,
trojan:// и т.п.), но urlsplit разбирает scheme://userinfo@host:port
?query#fragment одинаково для любой схемы — не только для http(s).
"""

from urllib.parse import quote, urlsplit, urlunsplit, unquote


def extract_link_name(url: str) -> str:
    """Человекочитаемое имя — декодированный фрагмент ссылки. Если
    фрагмента нет (в старых ссылках без имени) — возвращает хост, чтобы
    в списке всё равно было на что смотреть, а не пустую строку."""

    parts = urlsplit(url)

    if parts.fragment:
        return unquote(parts.fragment)

    return parts.hostname or url


def set_link_name(url: str, name: str) -> str:
    """Возвращает ссылку с заменённым фрагментом (именем), остальные
    части (протокол, uuid, хост, параметры) остаются без изменений."""

    parts = urlsplit(url)

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            parts.query,
            quote(name.strip(), safe=""),
        )
    )


def strip_link_name(url: str) -> str:
    """Возвращает ссылку без фрагмента (имени) — именно это нужно
    показывать в поле «Ссылка-конфиг» при редактировании, чтобы админ
    не мог случайно испортить имя, редактируя параметры подключения
    (или наоборот)."""

    parts = urlsplit(url)

    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
