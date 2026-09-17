"""手动验证 SMTP 配置：cd backend && uv run python scripts/send_test_email.py"""
import asyncio

from app.services.notify.email import email_enabled, send_email


async def main() -> None:
    if not email_enabled():
        print("未启用：请在 .env 配 SMTP_HOST 和 NOTIFY_EMAIL_TO")
        return
    out = await send_email("[客服 Copilot] SMTP 测试", "如果你收到这封邮件，说明 notify 的 email 通道已就绪。")
    print("已发送:", out)


if __name__ == "__main__":
    asyncio.run(main())
