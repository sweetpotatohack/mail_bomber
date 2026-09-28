# mail_bomber

Python-скрипт для массовой рассылки email с keep-alive, HTML-шаблонами и вложениями (doc, pdf, zip). Поддерживает SMTP через SSL (465), STARTTLS (587), plain open-relay на порту 25 (как `swaks` без `--tls`), автоподбор MX-хоста и переподключение при обрывах.

## Возможности

- **Keep-alive** — NOOP-пинги во время задержки между письмами
- **Порты** — `465` (SMTPS), `587` (STARTTLS по умолчанию), `25` (plain без STARTTLS по умолчанию)
- **Open-relay / misconfig** — отправка без `-u`/`-p`, режим как у swaks на `:25`
- **TLS** — `--starttls` / `--no-starttls` для ручного управления
- **MX fallback** — если на apex-домене (например `example.com:25`) connection refused, скрипт пробует MX и `mail.<домен>` (нужен `dig`)

## Usage

```
    ╔══════════════════════════════════════╗
    ║     akuma0xdead Email Bomber v3.0    ║
    ║   "Keep-alive like a hacker boss!"   ║
    ╚══════════════════════════════════════╝

usage: mail_bomber.py [-h] -e EMAILS -d DELAY -s SMTP_SERVER [--port PORT]
                      [--starttls | --no-starttls] [-u USER] [-p PASSWORD]
                      -f MAIL_FROM -t TEMPLATE [--subject SUBJECT]
                      [-a ATTACHMENTS]

options:
  -e, --emails          Файл с email адресами
  -d, --delay           Задержка между отправками (секунды)
  -s, --smtp-server     SMTP (host или host:port)
  --port                Порт, если не указан в -s (465=SSL, 587=STARTTLS, 25=plain)
  --starttls            Принудительно STARTTLS
  --no-starttls         Без STARTTLS (open-relay, как swaks без --tls)
  -u, --user            SMTP логин (для relay не нужен)
  -p, --password        SMTP пароль
  -f, --mail-from       Email отправителя
  -t, --template        HTML шаблон
  --subject             Тема письма
  -a, --attach          Вложение (можно несколько раз)
```

## Примеры

### IP / lab (порт 25)

```bash
python3 mail_bomber.py -e emails.txt -d 3 -s 10.124.5.11:25 \
  -f agent@x.stf -t letter.html -a payload.doc --subject "Важная информация"
```

### Домен с MX (apex → автоматически `mail.` / MX)

```bash
python3 mail_bomber.py -e mail.txt -d 3 -s mkkfinpost.ru:25 \
  -f support@mkkfinpost.ru -t template.html --subject "Важная информация"
```

Ожидаемый фрагмент лога при fallback:

```
[~] Варианты SMTP-хоста: mkkfinpost.ru, mail.mkkfinpost.ru
[+] Подключаемся к mkkfinpost.ru:25...
[~] mkkfinpost.ru:25 — Connection refused, пробуем mail.mkkfinpost.ru...
[~] Plain SMTP без STARTTLS (порт 25, как swaks на :25)
[+] Используем SMTP-host mail.mkkfinpost.ru (в -s был mkkfinpost.ru)
```

Явный хост почты:

```bash
python3 mail_bomber.py ... -s mail.mkkfinpost.ru:25 ...
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
- `dig` (bind9-dnsutils) — для MX fallback

## Disclaimer

Используй только там, где у тебя есть явное разрешение (CTF, lab, pentest scope). Несанкционированная массовая рассылка незаконна.
