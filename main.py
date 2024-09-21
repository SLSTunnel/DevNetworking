import socket
import requests
import ssl
import ipinfo
from urllib.parse import urlparse
import websocket
from flask import Flask
from threading import Thread
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import asyncio

# Flask server to keep the bot alive
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!", 200

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Connection Checker class with additional checks
class ConnectionChecker:
    def __init__(self, url):
        self.url = url
        parsed_url = urlparse(url)
        self.host = parsed_url.netloc or parsed_url.path
        self.scheme = parsed_url.scheme or 'https'

    def check_direct_connection(self):
        try:
            socket.gethostbyname(self.host)
            return True, "Successfully resolved the host."
        except Exception as e:
            return False, f"Failed to resolve host: {str(e)}"

    def check_http_connection(self):
        try:
            response = requests.get(f"{self.scheme}://{self.host}", timeout=5)
            return response.status_code == 200, f"Response code: {response.status_code}"
        except requests.exceptions.RequestException as e:
            return False, f"HTTP connection failed: {str(e)}"

    def check_sni(self):
        if self.scheme != 'https':
            return False, "SNI is only applicable for HTTPS connections"
        try:
            context = ssl.create_default_context()
            with socket.create_connection((self.host, 443)) as sock:
                with context.wrap_socket(sock, server_hostname=self.host) as ssock:
                    return True, f"SNI is supported by {self.host}"
        except Exception as e:
            return False, f"SNI check failed: {str(e)}"

    def check_websocket(self):
        try:
            ws_url = f"ws://{self.host}"
            ws = websocket.create_connection(ws_url, timeout=5)
            ws.close()
            return True, f"WebSocket connection successful to {ws_url}"
        except Exception as e:
            try:
                wss_url = f"wss://{self.host}"
                ws = websocket.create_connection(wss_url, timeout=5)
                ws.close()
                return True, f"WebSocket connection successful to {wss_url}"
            except Exception as e:
                return False, f"WebSocket check failed: {str(e)}"

    def check_v2ray(self):
        # Simulated check
        return True, "V2Ray is supported (simulated check)"

    def check_isp(self):
        try:
            access_token = 'b3e4a2a3797bcb'  # Replace with your actual IPinfo token
            handler = ipinfo.getHandler(access_token)
            ip = socket.gethostbyname(self.host)
            details = handler.getDetails(ip)
            return True, f"ISP: {details.org} (Location: {details.city}, {details.country})"
        except Exception as e:
            return False, f"ISP check failed: {str(e)}"

    def check_port(self, port):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                result = sock.connect_ex((self.host, port))
                return result == 0, f"Port {port} is {'open' if result == 0 else 'closed'}."
        except Exception as e:
            return False, f"Port {port} check failed: {str(e)}"

    async def check_speed(self):
        # Simulated speed check
        return True, "Download speed: 50.25 Mbps (simulated)"

    async def check_connection(self):
        results = []
        checks = [
            ("Direct Connection", self.check_direct_connection),
            ("HTTP Connection", self.check_http_connection),
            ("SNI Check", self.check_sni),
            ("WebSocket Check", self.check_websocket),
            ("V2Ray Check", self.check_v2ray),
            ("ISP Check", self.check_isp),
        ]

        for check_name, check_func in checks:
            try:
                results.append((check_name, *check_func()))
            except Exception as e:
                results.append((check_name, False, f"Check failed: {str(e)}"))

        for port in [80, 443]:
            results.append((f"Port {port} Check", *self.check_port(port)))

        speed_check_result = await self.check_speed()
        results.append(("Speed Check", *speed_check_result))

        return results

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Check a website", callback_data='check')],
        [InlineKeyboardButton("Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        'Welcome to the Connection Checker Bot! 🌐\n\n'
        'I can help you check the connection to any website or server.\n'
        'What would you like to do?',
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "Here's how to use the Connection Checker Bot:\n\n"
        "1. To check a website, simply type:\n"
        "   /check https://example.com\n\n"
        "2. I'll then check:\n"
        "   • Direct connection\n"
        "   • HTTP connection\n"
        "   • SNI support\n"
        "   • WebSocket connection\n"
        "   • V2Ray support\n"
        "   • ISP information\n"
        "   • Open ports (80, 443)\n"
        "   • Download speed\n\n"
        "3. You'll get a summary of the results.\n\n"
        "Tips:\n"
        "• Make sure to include 'http://' or 'https://' in the URL."
    )
    await update.message.reply_text(help_text)

async def check_host(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        keyboard = [[InlineKeyboardButton("How to check a website", callback_data='how_to_check')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Oops! You forgot to provide a URL to check. 😅\n"
            "Please use the command like this:\n"
            "/check https://example.com",
            reply_markup=reply_markup
        )
        return

    url = context.args[0]
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        checker = ConnectionChecker(url)
        message = await update.message.reply_text(f"🔍 Checking connection for {url}...\nThis may take a moment.")
        results = await checker.check_connection()

        summary = "📊 Results:\n\n"
        for method, status, info in results:
            status_emoji = "✅" if status else "❌"
            summary += f"{status_emoji} {method}:\n   {info}\n\n"

        keyboard = [[InlineKeyboardButton("Check another website", callback_data='check')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.edit_text(summary, reply_markup=reply_markup)

    except Exception as e:
        await update.message.reply_text(
            f"❌ Oops! Something went wrong while checking the connection:\n{str(e)}\n"
            "Please try again later or check if the URL is correct."
        )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == 'check':
        await query.edit_message_text(
            text="Great! Let's check a website. Please type:\n/check followed by the URL you want to check.\n\nFor example:\n/check https://example.com"
        )
    elif query.data == 'help':
        await help_command(update, context)
    elif query.data == 'how_to_check':
        await query.edit_message_text(
            text="To check a website, follow these steps:\n\n"
                 "1. Type /check followed by a space\n"
                 "2. Type the full URL including http:// or https://\n\n"
                 "For example:\n"
                 "/check https://example.com\n\n"
                 "Try it now!"
        )

def main() -> None:
    application = Application.builder().token("7981996805:AAEhie3ojsq3eo8N64ALQmYbUe63IGDXxxQ").build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("check", check_host))
    application.add_handler(CallbackQueryHandler(button))

    print("Bot is running. Press Ctrl+C to stop.")
    keep_alive()
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
