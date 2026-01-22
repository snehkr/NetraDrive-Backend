import resend
from datetime import datetime
from pydantic import EmailStr
from app.config import settings

resend.api_key = settings.resend_api_key


async def send_verification_email(email: EmailStr, username: str, token: str):
    verification_link = f"{settings.base_url}/verify-email?token={token}"

    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="margin:0; padding:0; background:#f4f6f8; font-family:Arial, Helvetica, sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td align="center" style="padding:24px;">
            <table width="600" style="background:#ffffff; border-radius:8px;">
              <tr>
                <td style="background:#0d6efd; padding:24px; text-align:center; color:#fff;">
                  <h1>NetraDrive</h1>
                </td>
              </tr>
              <tr>
                <td style="padding:32px;">
                  <h2>Welcome, {username} 👋</h2>
                  <p>Please verify your email to complete registration.</p>

                  <p style="text-align:center; margin:32px 0;">
                    <a href="{verification_link}"
                       style="background:#0d6efd; color:#fff; padding:14px 28px;
                              text-decoration:none; border-radius:6px; font-weight:bold;">
                      Verify Email Address
                    </a>
                  </p>

                  <p style="font-size:13px; word-break:break-all;">
                    {verification_link}
                  </p>

                  <p style="font-size:12px; color:#777;">
                    This link expires in 30 minutes.
                  </p>
                </td>
              </tr>
              <tr>
                <td style="background:#f4f6f8; padding:16px; text-align:center; font-size:12px;">
                  © NetraDrive {datetime.now().year}
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """

    resend.Emails.send(
        {
            "from": "NetraDrive <verify@mail.netradrive.snehkr.in>",
            "to": [email],
            "subject": "Verify your NetraDrive Account",
            "html": html,
        }
    )


async def send_reset_password_email(email: EmailStr, username: str, token: str):
    reset_link = f"{settings.base_url}/reset-password?token={token}"

    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="margin:0; padding:0; background:#f4f6f8; font-family:Arial, Helvetica, sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td align="center" style="padding:24px;">
            <table width="600" style="background:#ffffff; border-radius:8px;">
              <tr>
                <td style="background:#dc3545; padding:24px; text-align:center; color:#fff;">
                  <h1>NetraDrive</h1>
                </td>
              </tr>
              <tr>
                <td style="padding:32px;">
                  <h2>Password Reset</h2>
                  <p>Hello <strong>{username}</strong>,</p>

                  <p>Click the button below to reset your password.</p>

                  <p style="text-align:center; margin:32px 0;">
                    <a href="{reset_link}"
                       style="background:#dc3545; color:#fff; padding:14px 28px;
                              text-decoration:none; border-radius:6px; font-weight:bold;">
                      Reset Password
                    </a>
                  </p>

                  <p style="font-size:13px; word-break:break-all;">
                    {reset_link}
                  </p>

                  <p style="font-size:12px; color:#777;">
                    This link expires in 15 minutes.
                  </p>
                </td>
              </tr>
              <tr>
                <td style="background:#f4f6f8; padding:16px; text-align:center; font-size:12px;">
                  © NetraDrive {datetime.now().year}
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """

    resend.Emails.send(
        {
            "from": "NetraDrive <reset@mail.netradrive.snehkr.in>",
            "to": [email],
            "subject": "Reset Your NetraDrive Password",
            "html": html,
        }
    )
