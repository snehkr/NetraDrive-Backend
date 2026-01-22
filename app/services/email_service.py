from datetime import datetime
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr
from app.config import settings

# Configuration for Gmail SMTP
conf = ConnectionConfig(
    MAIL_USERNAME=settings.mail_username,
    MAIL_PASSWORD=settings.mail_password,
    MAIL_FROM=settings.mail_from,
    MAIL_PORT=settings.mail_port,
    MAIL_SERVER=settings.mail_server,
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True,
)


# --- SEND VERIFICATION EMAIL ---
async def send_verification_email(email: EmailStr, username: str, token: str):
    """
    Sends a verification email with a link to verify the account.
    """
    verification_link = f"{settings.base_url}/verify-email?token={token}"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Verify Your Email</title>
    </head>
    <body style="margin:0; padding:0; background-color:#f4f6f8; font-family:Arial, Helvetica, sans-serif;">

      <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
        <tr>
          <td align="center" style="padding:24px 12px;">
            <table width="100%" max-width="600" cellpadding="0" cellspacing="0" role="presentation"
                  style="max-width:600px; background:#ffffff; border-radius:8px; overflow:hidden;">
              <tr>
                <td style="background:#0d6efd; padding:24px; text-align:center;">
                  <h1 style="margin:0; font-size:22px; color:#ffffff;">
                    NetraDrive
                  </h1>
                </td>
              </tr>
              <tr>
                <td style="padding:32px 24px; color:#333333;">

                  <h2 style="margin-top:0; font-size:20px;">
                    Welcome, {username} 👋
                  </h2>

                  <p style="font-size:15px; line-height:1.6; margin-bottom:24px;">
                    Thank you for creating your NetraDrive account.  
                    To complete your registration, please verify your email address.
                  </p>
                  
                  <table cellpadding="0" cellspacing="0" role="presentation" align="center">
                    <tr>
                      <td align="center">
                        <a href="{verification_link}"
                          style="
                          display:inline-block;
                          padding:14px 28px;
                          background-color:#0d6efd;
                          color:#ffffff;
                          text-decoration:none;
                          font-size:16px;
                          font-weight:bold;
                          border-radius:6px;
                          ">
                          Verify Email Address
                        </a>
                      </td>
                    </tr>
                  </table>

                  <p style="font-size:14px; line-height:1.6; margin-top:28px;">
                    If the button doesn’t work, copy and paste this link into your browser:
                  </p>

                  <p style="font-size:13px; word-break:break-all; color:#0d6efd;">
                    {verification_link}
                  </p>

                  <p style="font-size:13px; color:#666666; margin-top:24px;">
                    ⏳ This verification link expires in <strong>30 minutes</strong>.
                  </p>

                </td>
              </tr>
              <tr>
                <td style="background:#f4f6f8; padding:16px; text-align:center; font-size:12px; color:#888888;">
                  <p style="margin:4px 0;">
                    If you didn’t create this account, you can safely ignore this email.
                  </p>
                  <p style="margin:4px 0;">
                    © NetraDrive {datetime.now().year} — All rights reserved
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>

    </body>
    </html>
    """

    message = MessageSchema(
        subject="Verify your NetraDrive Account",
        recipients=[email],
        body=html,
        subtype=MessageType.html,
    )

    fm = FastMail(conf)
    await fm.send_message(message)


# --- SEND RESET PASSWORD EMAIL ---
async def send_reset_password_email(email: EmailStr, username: str, token: str):
    """
    Sends an email with a link to reset the password.
    """
    # Assuming your frontend handles the reset page at /reset-password?token=...
    reset_link = f"{settings.base_url}/reset-password?token={token}"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Reset Your Password</title>
    </head>
    <body style="margin:0; padding:0; background-color:#f4f6f8; font-family:Arial, Helvetica, sans-serif;">

      <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
        <tr>
          <td align="center" style="padding:24px 12px;">
            <table width="100%" max-width="600" cellpadding="0" cellspacing="0" role="presentation"
                  style="max-width:600px; background:#ffffff; border-radius:8px; overflow:hidden;">

              <tr>
                <td style="background:#dc3545; padding:24px; text-align:center;">
                  <h1 style="margin:0; font-size:22px; color:#ffffff;">
                    NetraDrive
                  </h1>
                </td>
              </tr>
              <tr>
                <td style="padding:32px 24px; color:#333333;">

                  <h2 style="margin-top:0; font-size:20px;">
                    Password Reset Request
                  </h2>

                  <p style="font-size:15px; line-height:1.6;">
                    Hello <strong>{username}</strong>,
                  </p>

                  <p style="font-size:15px; line-height:1.6; margin-bottom:24px;">
                    We received a request to reset your NetraDrive password.  
                    You can securely set a new password using the button below.
                  </p>

                  <table cellpadding="0" cellspacing="0" role="presentation" align="center">
                    <tr>
                      <td align="center">
                        <a href="{reset_link}"
                          style="
                          display:inline-block;
                          padding:14px 28px;
                          background-color:#dc3545;
                          color:#ffffff;
                          text-decoration:none;
                          font-size:16px;
                          font-weight:bold;
                          border-radius:6px;
                          ">
                          Reset Password
                        </a>
                      </td>
                    </tr>
                  </table>

                  <p style="font-size:14px; line-height:1.6; margin-top:28px;">
                    If the button does not work, copy and paste this link into your browser:
                  </p>

                  <p style="font-size:13px; word-break:break-all; color:#dc3545;">
                    {reset_link}
                  </p>

                  <p style="font-size:13px; color:#666666; margin-top:24px;">
                    ⏳ This link expires in <strong>15 minutes</strong>.
                  </p>

                  <p style="font-size:13px; color:#666666; margin-top:16px;">
                    If you did not request a password reset, please ignore this email.
                    Your account remains secure.
                  </p>

                </td>
              </tr>
              <tr>
                <td style="background:#f4f6f8; padding:16px; text-align:center; font-size:12px; color:#888888;">
                  <p style="margin:4px 0;">
                    Need help? Contact NetraDrive support.
                  </p>
                  <p style="margin:4px 0;">
                    © NetraDrive {datetime.now().year} — All rights reserved
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>

    </body>
    </html>
    """

    message = MessageSchema(
        subject="Reset Your NetraDrive Password",
        recipients=[email],
        body=html,
        subtype=MessageType.html,
    )

    fm = FastMail(conf)
    await fm.send_message(message)
