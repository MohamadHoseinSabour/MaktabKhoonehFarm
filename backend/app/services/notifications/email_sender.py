import smtplib
from email.mime.text import MIMEText


class EmailNotifier:
    def send(self, smtp_host: str, smtp_port: int, username: str, password: str, to_email: str, subject: str, body: str) -> bool:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = username
        msg['To'] = to_email

        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(username, password)
            server.sendmail(username, [to_email], msg.as_string())
        return True