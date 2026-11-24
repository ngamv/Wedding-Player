"""Envoi SMTP TLS des relances Wedding validées."""
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid


def smtp_config():
    if os.environ.get("ORION_RECOVERY") == "1":
        return None
    host = os.environ.get("ORION_SMTP_HOST", "").strip()
    sender = os.environ.get("ORION_SMTP_FROM", "").strip()
    user = os.environ.get("ORION_SMTP_USER", "")
    password = os.environ.get("ORION_SMTP_PASSWORD", "")
    if not host or not sender or bool(user) != bool(password):
        return None
    try:
        port = int(os.environ.get("ORION_SMTP_PORT", "465"))
        if not 1 <= port <= 65535:
            return None
        probe = EmailMessage()
        probe["From"] = sender
        addresses = probe["From"].addresses
        if len(addresses) != 1 or not addresses[0].domain or probe["From"].defects:
            return None
    except (ValueError, TypeError):
        return None
    return host, port, sender, user, password


def send_reminder(config, reminder, message_id):
    host, port, sender, user, password = config
    message = EmailMessage()
    message["From"] = sender
    message["To"] = reminder["email"]
    recipients = message["To"].addresses
    if (len(recipients) != 1 or message["To"].defects
            or recipients[0].addr_spec != reminder["email"]):
        return "rejected", "Le destinataire n’a pas une adresse e-mail valide."
    message["Subject"] = reminder["subject"]
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = message_id
    message.set_content(reminder["message"])
    try:
        client = smtplib.SMTP_SSL(host, port, timeout=10, context=ssl.create_default_context())
    except (OSError, smtplib.SMTPException):
        return "rejected", "Connexion SMTP impossible."
    try:
        if user:
            try:
                client.login(user, password)
            except (OSError, smtplib.SMTPException):
                return "rejected", "Authentification SMTP impossible."
        try:
            client.send_message(message)
        except (smtplib.SMTPSenderRefused, smtplib.SMTPRecipientsRefused, smtplib.SMTPDataError):
            return "rejected", "Le serveur SMTP a refusé le message."
        except (OSError, smtplib.SMTPException):
            return "unknown", "Accusé SMTP absent. Vérifiez la messagerie avant toute nouvelle relance."
        return "accepted", "Message accepté par le serveur SMTP."
    finally:
        client.close()


def reminder_message_id():
    return make_msgid(domain="orion.local")
