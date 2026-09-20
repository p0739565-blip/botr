# Хотфикс: выручка с баланса + одноразовая реферальная программа

## Что внутри

Замените этими файлами одноимённые в репозитории (пути совпадают с
структурой репо — просто распакуйте архив поверх `vpn-bot/`, подтвердив
перезапись):

- `app/admin/routes/dashboard.py`
  Баланс исключён из RUB_METHODS — оплата бонусным балансом больше не
  учитывается в "выручке" на дашборде (revenue_today/week/total, график
  за 7 дней).

- `app/services/referral.py`
  Реферальный бонус теперь начисляется на КАЖДУЮ оплату приглашённого
  реальными деньгами (а не только один раз при первой покупке).
  `get_referral_stats()` тоже поправлен — paid_invited считается по
  логу начислений (ReferralReward), а не по снятому флагу.

- `app/handlers/payment.py`
  Из хендлера оплаты бонусным балансом (`buy_balance`) убран вызов
  `maybe_reward_referrer` — оплата с баланса больше не даёт
  пригласившему бонус (это не реальные деньги).

## Что НЕ менялось (и почему можно не трогать)

`User.referral_reward_given` в `app/models.py` остаётся в схеме
неиспользуемой колонкой — код её больше нигде не читает и не пишет.
Раз в проекте `create_all` вместо Alembic-миграций, удалять колонку
руками через `ALTER TABLE` не обязательно — лишняя колонка ни на что
не влияет.

## Как накатить на VM

```bash
# 1. Скопировать файлы (например через scp с локальной машины,
#    из корня распакованного архива):
scp -r app/admin/routes/dashboard.py  user@your-vm:/path/to/vpn-bot/app/admin/routes/dashboard.py
scp -r app/services/referral.py       user@your-vm:/path/to/vpn-bot/app/services/referral.py
scp -r app/handlers/payment.py        user@your-vm:/path/to/vpn-bot/app/handlers/payment.py

# 2. На самой VM — перезапустить оба процесса (bot и api берут
#    изменённый код только после рестарта):
sudo systemctl restart vpnapi.service
sudo systemctl restart vpnbot.service

# 3. Проверить, что оба процесса поднялись без ошибок:
sudo systemctl status vpnapi.service --no-pager
sudo systemctl status vpnbot.service --no-pager

# Если что-то не так — смотреть логи:
journalctl -u vpnapi.service -n 50 --no-pager
journalctl -u vpnbot.service -n 50 --no-pager
```

Если вместо прямого доступа к VM работаете через git — просто закоммитьте
эти 3 файла в репозиторий, сделайте `git pull` на VM, затем те же две
команды `systemctl restart` из шага 2.
