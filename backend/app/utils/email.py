import smtplib
from email.message import EmailMessage
from app.config import settings

def send_employee_credentials(
    to_email: str,
    employee_id: str,
    temp_password: str,
    employee_name: str
):
    msg = EmailMessage()
    msg["Subject"] = "Your Employee Account Credentials"
    msg["From"] = settings.SMTP_FROM_EMAIL
    msg["To"] = to_email

    msg.set_content(f"""
Hello {employee_name},

Your employee account has been created.

Employee ID: {employee_id}
Temporary Password: {temp_password}

Login here:
{settings.FRONTEND_LOGIN_URL}

⚠️ Please change your password immediately after first login.

If you did not expect this email, contact HR.

Regards,
HR Team
""")

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        server.login(
            settings.SMTP_USERNAME,
            settings.SMTP_PASSWORD
        )
        server.send_message(msg)


def send_password_reset_credentials(
    to_email: str,
    employee_id: str,
    temp_password: str,
    employee_name: str
):
    msg = EmailMessage()
    msg["Subject"] = "Password Reset - HR Workforce Management"
    msg["From"] = settings.SMTP_FROM_EMAIL
    msg["To"] = to_email

    msg.set_content(f"""
Hello {employee_name},

We received a password reset request for your account.

Employee ID: {employee_id}
Temporary Password: {temp_password}

Login here:
{settings.FRONTEND_LOGIN_URL}

Please login and change your password immediately.

If you did not request this, contact HR immediately.

Regards,
HR Team
""")

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        server.login(
            settings.SMTP_USERNAME,
            settings.SMTP_PASSWORD
        )
        server.send_message(msg)
