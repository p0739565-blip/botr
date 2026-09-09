"""Разбор полного клиентского конфига Xray/v2rayNG/NekoBox (JSON с
разделами inbounds/outbounds/routing/dns и т.п.) и превращение каждого
реального прокси-сервера из его `outbounds` в обычную ссылку-шару
(vless://..., trojan://..., vmess://..., ss://...), которую уже умеет
отдавать /sub/<token> — так же, как ссылки, вставленные вручную.

Такие конфиги обычно содержат НЕСКОЛЬКО outbounds сразу (например,
balancer из 2-3 серверов на резерв/обход) — поэтому парсер возвращает
список, а не одну ссылку. Служебные outbounds (freedom, blackhole,
dns) пропускаются.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from urllib.parse import quote, urlencode

# Протоколы-заглушки, которые не являются реальными серверами и не
# должны попадать в список ссылок.
_SKIP_PROTOCOLS = {"freedom", "blackhole", "dns"}


class ConfigJsonError(ValueError):
    """Не удалось разобрать вставленный JSON как клиентский конфиг."""


@dataclass
class ParsedLink:
    url: str
    name: str
    tag: str


def parse_client_config(raw_text: str) -> list[ParsedLink]:
    """Парсит вставленный текст как JSON клиентского конфига и
    возвращает список найденных серверов в виде готовых ссылок.

    Бросает ConfigJsonError с человекочитаемым сообщением, если это не
    похоже на конфиг (невалидный JSON, нет outbounds, нет ни одного
    поддерживаемого протокола).
    """

    raw_text = raw_text.strip()
    if not raw_text:
        raise ConfigJsonError("Пустой JSON")

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigJsonError(f"Невалидный JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigJsonError("Ожидается JSON-объект (конфиг), а не список/значение")

    outbounds = data.get("outbounds")
    if not isinstance(outbounds, list) or not outbounds:
        raise ConfigJsonError("В конфиге не найден непустой раздел \"outbounds\"")

    base_name = (data.get("remarks") or "").strip()

    results: list[ParsedLink] = []
    for outbound in outbounds:
        if not isinstance(outbound, dict):
            continue
        protocol = (outbound.get("protocol") or "").strip().lower()
        if protocol in _SKIP_PROTOCOLS or not protocol:
            continue

        parsed = _convert_outbound(protocol, outbound)
        if parsed is None:
            continue

        tag = outbound.get("tag") or protocol
        name = base_name
        if base_name and len(outbounds) > 1:
            name = f"{base_name} — {tag}"
        elif not base_name:
            name = tag

        results.append(ParsedLink(url=parsed, name=name, tag=tag))

    if not results:
        raise ConfigJsonError(
            "В outbounds нет ни одного поддерживаемого сервера "
            "(vless/vmess/trojan/shadowsocks)"
        )

    return results


def _convert_outbound(protocol: str, outbound: dict) -> str | None:
    if protocol == "vless":
        return _convert_vless(outbound)
    if protocol == "trojan":
        return _convert_trojan(outbound)
    if protocol == "vmess":
        return _convert_vmess(outbound)
    if protocol in ("shadowsocks", "ss"):
        return _convert_shadowsocks(outbound)
    return None


def _stream_query(stream: dict) -> dict[str, str]:
    """Общая часть query-параметров ссылки-шары, которая одинаково
    строится из streamSettings для vless/trojan (type/security/sni/
    fp/alpn + настройки конкретного транспорта)."""

    q: dict[str, str] = {}

    network = stream.get("network") or "tcp"
    q["type"] = network

    security = stream.get("security") or "none"
    if security and security != "none":
        q["security"] = security

    if security == "tls":
        tls = stream.get("tlsSettings") or {}
        if tls.get("serverName"):
            q["sni"] = tls["serverName"]
        if tls.get("fingerprint"):
            q["fp"] = tls["fingerprint"]
        if tls.get("alpn"):
            q["alpn"] = ",".join(tls["alpn"])

    if security == "reality":
        rs = stream.get("realitySettings") or {}
        if rs.get("serverName"):
            q["sni"] = rs["serverName"]
        if rs.get("fingerprint"):
            q["fp"] = rs["fingerprint"]
        if rs.get("publicKey"):
            q["pbk"] = rs["publicKey"]
        if rs.get("shortId"):
            q["sid"] = rs["shortId"]
        if rs.get("spiderX"):
            q["spx"] = rs["spiderX"]

    if network == "ws":
        ws = stream.get("wsSettings") or {}
        if ws.get("path"):
            q["path"] = ws["path"]
        host = (ws.get("headers") or {}).get("Host")
        if host:
            q["host"] = host

    if network == "grpc":
        grpc = stream.get("grpcSettings") or {}
        if grpc.get("serviceName"):
            q["serviceName"] = grpc["serviceName"]
        if grpc.get("authority"):
            q["authority"] = grpc["authority"]
        q["mode"] = "multi" if grpc.get("multiMode") or grpc.get("mode") else "gun"

    if network == "h2" or network == "http":
        h2 = stream.get("httpSettings") or {}
        if h2.get("path"):
            q["path"] = h2["path"]
        if h2.get("host"):
            hosts = h2["host"]
            q["host"] = ",".join(hosts) if isinstance(hosts, list) else str(hosts)

    if network == "kcp":
        kcp = stream.get("kcpSettings") or {}
        if kcp.get("seed"):
            q["seed"] = kcp["seed"]
        if kcp.get("header", {}).get("type"):
            q["headerType"] = kcp["header"]["type"]

    return q


def _convert_vless(outbound: dict) -> str | None:
    vnext = (outbound.get("settings") or {}).get("vnext") or []
    if not vnext:
        return None
    server = vnext[0]
    users = server.get("users") or []
    if not users:
        return None
    user = users[0]

    address = server.get("address")
    port = server.get("port")
    uid = user.get("id")
    if not address or not port or not uid:
        return None

    stream = outbound.get("streamSettings") or {}
    q = _stream_query(stream)
    q["encryption"] = user.get("encryption") or "none"
    if user.get("flow"):
        q["flow"] = user["flow"]

    query = urlencode(q, safe=",")
    return f"vless://{uid}@{address}:{port}?{query}"


def _convert_trojan(outbound: dict) -> str | None:
    servers = (outbound.get("settings") or {}).get("servers") or []
    if not servers:
        return None
    server = servers[0]

    address = server.get("address")
    port = server.get("port")
    password = server.get("password")
    if not address or not port or not password:
        return None

    stream = outbound.get("streamSettings") or {}
    q = _stream_query(stream)
    # У trojan security по умолчанию де-факто "tls", в отличие от
    # vless/vmess — не убираем его из query, даже если streamSettings
    # его явно не выставляет.
    q.setdefault("security", "tls")

    query = urlencode(q, safe=",")
    return f"trojan://{quote(password, safe='')}@{address}:{port}?{query}"


def _convert_vmess(outbound: dict) -> str | None:
    vnext = (outbound.get("settings") or {}).get("vnext") or []
    if not vnext:
        return None
    server = vnext[0]
    users = server.get("users") or []
    if not users:
        return None
    user = users[0]

    address = server.get("address")
    port = server.get("port")
    uid = user.get("id")
    if not address or not port or not uid:
        return None

    stream = outbound.get("streamSettings") or {}
    network = stream.get("network") or "tcp"
    security = stream.get("security") or "none"

    vmess_obj = {
        "v": "2",
        "ps": outbound.get("tag") or "",
        "add": address,
        "port": port,
        "id": uid,
        "aid": user.get("alterId", 0),
        "scy": user.get("security") or "auto",
        "net": network,
        "type": "none",
        "tls": security if security in ("tls", "reality") else "",
    }

    if network == "ws":
        ws = stream.get("wsSettings") or {}
        vmess_obj["path"] = ws.get("path", "")
        vmess_obj["host"] = (ws.get("headers") or {}).get("Host", "")

    if security == "tls":
        tls = stream.get("tlsSettings") or {}
        if tls.get("serverName"):
            vmess_obj["sni"] = tls["serverName"]
        if tls.get("fingerprint"):
            vmess_obj["fp"] = tls["fingerprint"]

    encoded = base64.b64encode(json.dumps(vmess_obj).encode()).decode()
    return f"vmess://{encoded}"


def _convert_shadowsocks(outbound: dict) -> str | None:
    servers = (outbound.get("settings") or {}).get("servers") or []
    if not servers:
        return None
    server = servers[0]

    address = server.get("address")
    port = server.get("port")
    method = server.get("method")
    password = server.get("password")
    if not address or not port or not method or not password:
        return None

    userinfo = base64.urlsafe_b64encode(f"{method}:{password}".encode()).decode().rstrip("=")
    return f"ss://{userinfo}@{address}:{port}"
