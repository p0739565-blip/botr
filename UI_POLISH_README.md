# Визуальный апгрейд админки

## Что внутри

Распакуйте архив поверх `vpn-bot/` (пути внутри совпадают со структурой
репозитория) — заменит:

- `app/admin/static/style.css` — добавлены компоненты: шапка страницы
  (`page-header`), пустые состояния (`empty-state`), стилизованная
  confirm-модалка, визуал журнала действий (`audit-*`).
- `app/admin/templates/base.html` — добавлена общая confirm-модалка +
  JS, перехватывающий отправку форм с атрибутом `data-confirm` (замена
  нативного `window.confirm()`).
- `app/admin/templates/audit.html` — полностью переработан: иконка и
  человекочитаемая подпись на каждый тип действия, группировка по дням,
  пустое состояние.
- Остальные 16 шаблонов — точечные правки: замена `onsubmit="return
  confirm(...)"` на `data-confirm="..."` (12 мест) + единый `page-header`
  вместо разномастных `d-flex justify-content-between` (users, payments,
  support_list, broadcast_list, admins, vless_links, tariffs, referrals)
  + красивые пустые состояния вместо голого текста (users, payments,
  support_list, broadcast_list).

Все 20 шаблонов проверены на валидность синтаксиса Jinja2 перед сборкой
архива. Ни один route/py-файл не тронут — это чисто визуальный патч.

## Что не менялось и почему

Полный редизайн не потребовался — дизайн-система (`card-soft`,
`stat-card`, `table-admin`, `badge-*`) уже была одинаково применена на
всех страницах, не только на дашборде. Патч точечно устраняет
конкретные слабые места (нативные confirm-окна, голые пустые
состояния, нечитаемый журнал), а не переписывает то, что уже хорошо
работало.

## Как накатить

Просто скопировать файлы и перезапустить панель — бот трогать не
нужно, все правки только в `app/admin/`:

```bash
scp -r app/admin/static/style.css      user@your-vm:/opt/vpn-bot/app/admin/static/style.css
scp -r app/admin/templates/*.html      user@your-vm:/opt/vpn-bot/app/admin/templates/

sudo systemctl restart vpnapi.service
sudo systemctl status vpnapi.service --no-pager
```

Если что-то не так — `journalctl -u vpnapi.service -n 50 --no-pager`.
