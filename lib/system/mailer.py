"""
Send e-mail through the SMTP server set in Administration -> Settings.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Any, Dict, Iterable, List, Optional

TIMEOUT_SECONDS = 20


class MailError(RuntimeError):
    """The e-mail could not be sent; the message says why in plain words."""


def addresses(values: Iterable[str]) -> List[str]:
    """Distinct, plausible e-mail addresses (comma, semicolon or space separated)."""

    found: List[str] = []
    for value in values:
        for part in str(value).replace(";", ",").replace(" ", ",").split(","):
            part = part.strip()
            if part and "@" in part and "." in part.rsplit("@", 1)[-1] and part not in found:
                found.append(part)
    return found


def send_mail(
    smtp: Dict[str, Any],
    to: List[str],
    subject: str,
    text: str,
    html: Optional[str] = None,
) -> None:
    """Send one message; raises MailError with a readable reason."""

    if not smtp.get("enabled"):
        raise MailError("E-mail is not set up: Administration -> Settings -> E-mail.")
    recipients = addresses(to)
    if not recipients:
        raise MailError("No valid recipient address.")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((smtp.get("from_name") or "Entropy", smtp["from_address"]))
    message["To"] = ", ".join(recipients)
    message["Message-ID"] = make_msgid(domain=smtp["from_address"].rsplit("@", 1)[-1])
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")

    context = ssl.create_default_context()
    if not smtp.get("verify_tls", True):
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    host, port = smtp["host"], int(smtp["port"])
    try:
        if smtp.get("security") == "ssl":
            client = smtplib.SMTP_SSL(host, port, timeout=TIMEOUT_SECONDS, context=context)
        else:
            client = smtplib.SMTP(host, port, timeout=TIMEOUT_SECONDS)
        with client:
            client.ehlo()
            if smtp.get("security") == "starttls":
                client.starttls(context=context)
                client.ehlo()
            if smtp.get("username"):
                client.login(smtp["username"], smtp.get("password") or "")
            client.send_message(message)
    except smtplib.SMTPAuthenticationError:
        raise MailError("The SMTP server refused the user name or password.") from None
    except smtplib.SMTPRecipientsRefused as exc:
        raise MailError(f"The SMTP server refused the recipients: {exc.recipients}.") from None
    except smtplib.SMTPNotSupportedError:
        raise MailError("The server does not support STARTTLS; choose SSL or none.") from None
    except ssl.SSLError as exc:
        raise MailError(f"TLS failed ({exc.reason}); check the security mode and port.") from None
    except (OSError, smtplib.SMTPException) as exc:
        raise MailError(f"Could not send through {host}:{port}: {exc}") from None
