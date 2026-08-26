# ЭТОТ ФАЙЛ БОЛЬШЕ НЕ ЧИТАЕТСЯ БОТОМ/API НАПРЯМУЮ.
#
# Ссылки теперь живут в таблице vless_links в БД и правятся через
# админку (/admin/vless-links) — там же теперь и источник истины.
#
# Файл оставлен только как одноразовый seed: списки ниже — то, что
# было тут раньше. Разово перенести их в БД (если таблица ещё пустая):
#
#   python -m app.vless_links_seed
#
# Повторный запуск ничего не сломает — если в БД уже что-то есть,
# скрипт откажется и ничего не тронет.

VLESS_LINK_TEMPLATES: list[str] = [
    "vless://f182edc9-0f53-477b-9496-ec481c983467@vd.freelink.online:443?encryption=none&flow=xtls-rprx-vision&security=reality&sni=vd.freelink.online&fp=firefox&pbk=DrpLWgeVVCQkLvIh6TxJ7qQLxGgEcyNcEvJypSPYX1Y&type=tcp&headerType=none&spx=%2F#🇷🇺%20Youtube%20без%20рекламы,%20Инста%20(WiFi)",
    "vless://f182edc9-0f53-477b-9496-ec481c983467@dutch1.freelink.online:443?encryption=none&flow=xtls-rprx-vision&type=tcp&security=reality&sni=dutch1.freelink.online&fp=firefox&pbk=we-aFs9VY_MApvI4kqHQxHbQcKLD-_fTYGRosHx0CAw&spx=/#%F0%9F%87%B3%F0%9F%87%B1%20%20%F0%9F%87%B3%F0%9F%87%B1%20%D0%9D%D0%B8%D0%B4%D0%B5%D1%80%D0%BB%D0%B0%D0%BD%D0%B4%D1%8B%20%28WiFi%29",
    "vless://f182edc9-0f53-477b-9496-ec481c983467@de10.freelink.online:443?encryption=none&flow=xtls-rprx-vision&type=tcp&security=reality&sni=de10.freelink.online&fp=firefox&pbk=z97armwRYEXFuOLtlU_3pKNWhyGA6ZJZRN0Ncm_eQlY&spx=/#%F0%9F%87%A9%F0%9F%87%AA%20%D0%93%D0%B5%D1%80%D0%BC%D0%B0%D0%BD%D0%B8%D1%8F%20%28WiFi%29",
    "vless://f182edc9-0f53-477b-9496-ec481c983467@swe.freelink.online:443?encryption=none&flow=xtls-rprx-vision&type=tcp&security=reality&sni=swe.freelink.online&fp=firefox&pbk=FTlJ8M-gESBLE6tvfBcgKTI0dEqmEejVBkK9ejSzvgg&spx=/#%F0%9F%87%B8%F0%9F%87%AA%20%D0%A8%D0%B2%D0%B5%D1%86%D0%B8%D1%8F%20%28WiFi%29",
    "vless://f182edc9-0f53-477b-9496-ec481c983467@lat.freelink.online:443?encryption=none&flow=xtls-rprx-vision&type=tcp&security=reality&sni=lat.freelink.online&fp=edge&pbk=mnQJ6-RQXydInjgm4IrZF9fbjSHmpk9cKM0O_FCcz3M&spx=/#%F0%9F%87%B1%F0%9F%87%BB%20%D0%9B%D0%B0%D1%82%D0%B2%D0%B8%D1%8F%20%28WiFi%29",
    "vless://f182edc9-0f53-477b-9496-ec481c983467@fin6.freelink.online:443?encryption=none&flow=xtls-rprx-vision&type=tcp&security=reality&sni=fin6.freelink.online&fp=firefox&pbk=Z_CTQe8qDDF4koR1mj4Qst3nFmMWFS1b6NHMNGXZGmA&spx=/#%F0%9F%87%AB%F0%9F%87%AE%20%20%D0%A4%D0%B8%D0%BD%D0%BB%D1%8F%D0%BD%D0%B4%D0%B8%D1%8F%20%28WiFi%29",
    "vless://f182edc9-0f53-477b-9496-ec481c983467@93.88.206.164:443?encryption=none&flow=xtls-rprx-vision&type=tcp&security=reality&sni=pl.freelink.online&fp=firefox&pbk=we-aFs9VY_MApvI4kqHQxHbQcKLD-_fTYGRosHx0CAw&spx=/#%F0%9F%87%B5%F0%9F%87%B1%20%D0%9F%D0%BE%D0%BB%D1%8C%D1%88%D0%B0%20%28WiFi%29",
    "vless://f182edc9-0f53-477b-9496-ec481c983467@vd.freelink.online:443?encryption=none&flow=xtls-rprx-vision&type=tcp&security=reality&sni=vd.freelink.online&fp=firefox&pbk=DrpLWgeVVCQkLvIh6TxJ7qQLxGgEcyNcEvJypSPYX1Y&spx=/#%F0%9F%87%B7%F0%9F%87%BA%20%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0%20%28WiFi%29",
    "vless://f182edc9-0f53-477b-9496-ec481c983467@pra2.freelink.online:443?encryption=none&flow=xtls-rprx-vision&type=tcp&security=reality&sni=pra2.freelink.online&fp=firefox&pbk=mnQJ6-RQXydInjgm4IrZF9fbjSHmpk9cKM0O_FCcz3M&spx=/#%F0%9F%87%A8%F0%9F%87%BF%20%D0%A7%D0%B5%D1%85%D0%B8%D1%8F%20%28WiFi%29",
    "vless://f182edc9-0f53-477b-9496-ec481c983467@45.11.26.30:443?encryption=none&flow=xtls-rprx-vision&type=tcp&security=reality&sni=media-ru.fl-work.shop&fp=firefox&pbk=HjLnK08_mKtaUa94dpwpxMaX7nbBlMGgk-dNGB_IrF4&spx=/#%F0%9F%87%B7%F0%9F%87%BA%20%D0%9C%D0%BE%D0%B1.%20%D0%BE%D0%BF%D0%B5%D1%80%D0%B0%D1%82%D0%BE%D1%80%D1%8B%200%20%284G/LTE%29",
    "vless://f182edc9-0f53-477b-9496-ec481c983467@fl-work.shop:443?encryption=none&flow=xtls-rprx-vision&type=tcp&security=reality&sni=fl-work.shop&fp=firefox&pbk=KfLHeaqRpA8psMOPYIvObhwDxsaTTjhTXc309XVGFmA&spx=/#%F0%9F%87%B7%F0%9F%87%BA%20%D0%9C%D0%BE%D0%B1.%20%D0%BE%D0%BF%D0%B5%D1%80%D0%B0%D1%82%D0%BE%D1%80%D1%8B%201%20%284G/LTE%29",
    "vless://f182edc9-0f53-477b-9496-ec481c983467@213.226.112.181:443?encryption=none&flow=xtls-rprx-vision&type=tcp&security=reality&sni=fl-work.shop&fp=firefox&pbk=KfLHeaqRpA8psMOPYIvObhwDxsaTTjhTXc309XVGFmA&spx=/#%F0%9F%87%B7%F0%9F%87%BA%20%D0%9C%D0%BE%D0%B1.%20%D0%BE%D0%BF%D0%B5%D1%80%D0%B0%D1%82%D0%BE%D1%80%D1%8B%202%20%284G/LTE%29",
    "vless://f182edc9-0f53-477b-9496-ec481c983467@azu6cjf7vo.a.trbcdn.net:443?encryption=none&type=xhttp&security=tls&sni=azu6cjf7vo.a.trbcdn.net&fp=firefox&alpn=h2,http/1.1#%F0%9F%87%B7%F0%9F%87%BA%20%20%F0%9F%87%B7%F0%9F%87%BA%20%D0%9C%D0%BE%D0%B1.%20%D0%BE%D0%BF%D0%B5%D1%80%D0%B0%D1%82%D0%BE%D1%80%D1%8B%203%20%284G/LTE%29%20",
    "vless://f182edc9-0f53-477b-9496-ec481c983467@fl-work.shop:443?encryption=none&flow=xtls-rprx-vision&type=tcp&security=reality&sni=fl-work.shop&fp=firefox&pbk=KfLHeaqRpA8psMOPYIvObhwDxsaTTjhTXc309XVGFmA&spx=/#%F0%9F%87%B7%F0%9F%87%BA%20%20%F0%9F%87%B7%F0%9F%87%BA%20%D0%9C%D0%BE%D0%B1.%20%D0%BE%D0%BF%D0%B5%D1%80%D0%B0%D1%82%D0%BE%D1%80%D1%8B%204%20%284G/LTE%29%20",
    "hy2://f182edc9-0f53-477b-9496-ec481c983467@de1.freelink.online:443?insecure=0&sni=de1.freelink.online&alpn=h3&pinSHA256=&obfs=&obfs-password=#%F0%9F%87%A9%F0%9F%87%AA%20%D0%93%D0%B5%D1%80%D0%BC%D0%B0%D0%BD%D0%B8%D1%8F%20%28WiFi%29%20%28%D0%B7%D0%B0%D0%BF%D0%B0%D1%81.%29",
    "hy2://f182edc9-0f53-477b-9496-ec481c983467@pra2.freelink.online:443?insecure=0&sni=pra2.freelink.online&alpn=h3&pinSHA256=&obfs=&obfs-password=#%F0%9F%87%A8%F0%9F%87%BF%20%F0%9F%87%A8%F0%9F%87%BF%20%D0%A7%D0%B5%D1%85%D0%B8%D1%8F%20%28WiFi%29%20%28%D0%B7%D0%B0%D0%BF%D0%B0%D1%81.%29",
    "hy2://f182edc9-0f53-477b-9496-ec481c983467@fin6.freelink.online:443?insecure=0&sni=fin6.freelink.online&alpn=h3&pinSHA256=&obfs=&obfs-password=#%F0%9F%87%AB%F0%9F%87%AE%20%F0%9F%87%AB%F0%9F%87%AE%20%D0%A4%D0%B8%D0%BD%D0%BB%D1%8F%D0%BD%D0%B4%D0%B8%D1%8F%20%28WiFi%29%20%28%D0%B7%D0%B0%D0%BF%D0%B0%D1%81.%29",
    "vless://cbcff772-9064-4622-85e8-f97c09ff939f@45.11.27.157:443?encryption=none&flow=xtls-rprx-vision&security=reality&sni=ekb1.etherealvpn.uk&fp=randomized&pbk=GT4MHzP5-UYO0UCIkSfmmsN5seYqpdhbByAc8XQgDkc&sid=12dce06f314d42df&type=tcp#%F0%9F%87%B7%F0%9F%87%BA%20%D0%B1%D0%B5%D0%BB%D1%8B%D0%B5%20%D1%81%D0%BF%D0%B8%D1%81%D0%BA%D0%B8%20%28%D0%BA%D1%80%D0%BE%D0%BC%D0%B5%20%D0%9C%D0%A2%D0%A1%20%7C%20%D0%A2-%D0%BC%D0%BE%D0%B1%29",
    "vless://bd351723-d91d-4607-86f5-391e48899565@bs-bri01.neverspy.tech:443?encryption=none&security=tls&sni=bs-bri01.neverspy.tech&fp=firefox&type=xhttp&path=%2Fapi%2Fv1%2Fsync&mode=packet-up&extra=%7B%22noSSEHeader%22%3Atrue%2C%22uplinkHTTPMethod%22%3A%22GET%22%2C%22xPaddingBytes%22%3A%22100-1000%22%7D#%F0%9F%87%B7%F0%9F%87%BA%20%D0%A0%D0%BE%D1%81%D1%81%D0%B8%D1%8F%20LTE%20%C2%B7%20%D0%9E%D1%81%D1%82%D0%B0%D0%BB%D0%BE%D1%81%D1%8C%205%20%D0%93%D0%91",
    "vless://bd351723-d91d-4607-86f5-391e48899565@bs-po01.neverspy.tech:443?encryption=none&security=tls&sni=bs-po01.neverspy.tech&fp=chrome&type=xhttp&path=%2Fapi%2Fv1%2Fsync&mode=packet-up&extra=%7B%22noSSEHeader%22%3Atrue%2C%22uplinkHTTPMethod%22%3A%22GET%22%2C%22xPaddingBytes%22%3A%22100-1000%22%7D#%F0%9F%87%B5%F0%9F%87%B1%20%D0%9F%D0%BE%D0%BB%D1%8C%D1%88%D0%B0%20LTE%20%C2%B7%20%D0%9E%D1%81%D1%82%D0%B0%D0%BB%D0%BE%D1%81%D1%8C%205%20%D0%93%D0%91",
    "vless://bd351723-d91d-4607-86f5-391e48899565@bs-03.neverspy.tech:443?encryption=none&security=tls&sni=bs-03.neverspy.tech&fp=chrome&type=xhttp&path=%2Fapi%2Fv1%2Fsync&mode=packet-up&extra=%7B%22noSSEHeader%22%3Atrue%2C%22uplinkHTTPMethod%22%3A%22GET%22%2C%22xPaddingBytes%22%3A%22100-1000%22%7D#%F0%9F%87%B8%F0%9F%87%AA%20%D0%A8%D0%B2%D0%B5%D1%86%D0%B8%D1%8F%20LTE%20%C2%B7%20%D0%9E%D1%81%D1%82%D0%B0%D0%BB%D0%BE%D1%81%D1%8C%205%20%D0%93%D0%91",
]

# Ссылки-заглушки, которые отдаются, если подписка истекла или не найдена —
# аналог deadLinks в вашем воркере (например, ведут на неработающий сервер
# с понятным названием "Подписка закончилась")
DEAD_LINKS: list[str] = [
    "vless://00000000-0000-0000-0000-000000000000@240.0.0.1:443?flow=xtls-rprx-vision&"
    "encryption=none&type=tcp&security=reality&fp=firefox&sni=eh.vk.ru&"
    "pbk=AAZjVvbC7AwPKot_1ygO5VMpN7XYifCA7lG0RNR5sEk&sid=0000000000000000"
    "#%E2%9B%94%20Подписка%20закончилась",
]

async def _seed() -> None:
    import asyncio

    from sqlalchemy import select

    from app.db import async_session, init_models
    from app.models import VlessLink

    await init_models()

    async with async_session() as session:
        existing = await session.execute(select(VlessLink.id).limit(1))
        if existing.scalar_one_or_none() is not None:
            print("В таблице vless_links уже есть записи — ничего не делаю. "
                  "Управляйте ссылками через /admin/vless-links.")
            return

        for i, url in enumerate(VLESS_LINK_TEMPLATES):
            session.add(VlessLink(url=url, is_dead=False, position=i))
        for i, url in enumerate(DEAD_LINKS):
            session.add(VlessLink(url=url, is_dead=True, position=i))

        await session.commit()
        print(
            f"Перенёс в БД {len(VLESS_LINK_TEMPLATES)} рабочих и "
            f"{len(DEAD_LINKS)} запасных ссылок."
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(_seed())