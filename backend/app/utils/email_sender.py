import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import Dict, List, Optional
from backend.app.utils.logger import logger


def _attach_file_to_message(msg: MIMEMultipart, filename: str, content: str, mime_type: str):
    try:
        main_type, sub_type = mime_type.split("/", 1)
    except ValueError:
        main_type, sub_type = "application", "octet-stream"

    if main_type == "text":
        part = MIMEText(content, _subtype=sub_type, _charset="utf-8")
    else:
        part = MIMEApplication(content, _subtype=sub_type)

    part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
    msg.attach(part)


def send_email(
        config: Dict,
        subject: str,
        content: str,
        recipients: List[str],
        attachments: Optional[List[tuple]] = None
) -> bool:
    """
    发送邮件
    config: 来自 Config.EMAIL_CONFIG
    """
    try:
        msg = MIMEMultipart()
        sender = config.get("sender")
        if not sender:
            # 兼容 config 字典键名不一致的情况
            sender = config.get("from_addr", "monitor@example.com")

        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject

        msg.attach(MIMEText(content, "plain", "utf-8"))

        if attachments:
            for filename, file_content, mime_type in attachments:
                _attach_file_to_message(msg, filename, file_content, mime_type)

        with smtplib.SMTP(config["smtp_server"], config.get("smtp_port", 587)) as server:
            if config.get("use_tls", True):
                server.starttls()
            server.login(sender, config["password"])
            server.send_message(msg)

        logger.info(f"邮件发送成功: {subject}")
        return True

    except Exception as e:
        logger.error(f"发送邮件失败: {e}", exc_info=True)
        return False