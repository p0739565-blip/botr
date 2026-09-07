# Компактные кнопки действий в строках таблиц

## Что было

На "Пользователях" уже стояли компактные "⋯" вместо крупных кнопок, а
на остальных страницах со списками — всё ещё старые большие заливные
кнопки на каждую строку ("Открыть", "Изменить цену"), а на VPN-ссылках
вообще по три штуки в ряд ("Изменить"/"Выключить"/"Удалить") — вот это
и правда выглядело тяжело, особенно когда строк много.

## Что изменилось

- **Рассылки, Тикеты, Тарифы** — "Открыть"/"Изменить цену" заменены на
  такую же компактную "⋯", как на Пользователях (просто ссылка на ту
  же страницу, действие одно — крупная кнопка была не нужна).
- **Обращения в поддержку** — заодно и фильтр вкладок "Открытые/
  Закрытые/Все" переведён на тот же лёгкий `.filter-btn`, что и на
  Пользователях (был на обычных bootstrap-кнопках, смотрелся тяжелее
  остального интерфейса).
- **VPN-ссылки** — тут действий реально три, одной "⋯"-ссылкой не
  обойтись, поэтому это теперь настоящее выпадающее меню (клик по "⋯"
  → Изменить / Выключить-Включить / — разделитель — / Удалить).
  Технически это стандартный Bootstrap dropdown (JS для него уже
  подключён в проекте, ничего нового тянуть не пришлось) — только
  перекрашен в тёмную тему, потому что по умолчанию он белый.
- Заодно оба select рядом с кнопками очистки/удаления (там, где они
  есть на этих страницах) — той же высоты, что кнопка рядом, чтобы не
  повторить историю с "Пользователями", где это тоже приходилось
  чинить отдельно.

Ничего в логике/бэкенде не менялось — только вёрстка и стили, все
ссылки/формы ведут туда же, куда и раньше.

## Файлы

- `app/admin/templates/broadcast_list.html`
- `app/admin/templates/support_list.html`
- `app/admin/templates/tariffs.html`
- `app/admin/templates/vless_links.html`
- `app/admin/static/style.css` — новые классы `.dropdown-admin`
  (тёмное меню) + мелкая правка `.row-menu-btn` для кнопок (не только
  ссылок).
- `app/admin/templates/base.html` — без изменений в этом патче,
  включён для целостности архива.

## Как накатить

```bash
scp app/admin/templates/broadcast_list.html  user@your-vm:/opt/vpn-bot/app/admin/templates/broadcast_list.html
scp app/admin/templates/support_list.html    user@your-vm:/opt/vpn-bot/app/admin/templates/support_list.html
scp app/admin/templates/tariffs.html         user@your-vm:/opt/vpn-bot/app/admin/templates/tariffs.html
scp app/admin/templates/vless_links.html     user@your-vm:/opt/vpn-bot/app/admin/templates/vless_links.html
scp app/admin/static/style.css               user@your-vm:/opt/vpn-bot/app/admin/static/style.css

sudo systemctl restart vpnapi.service
sudo systemctl status vpnapi.service --no-pager
```
