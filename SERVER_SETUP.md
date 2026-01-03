# Server Setup Workflow for Telegram Bot

This guide walks you through setting up the yt-dlp-proxy Telegram bot on a server, starting from git clone.

## Prerequisites

- Server with Linux/Ubuntu (or similar)
- Python 3.7+ installed
- Git installed
- Root/sudo access (for installing system packages)

## Step-by-Step Workflow

### 1. Clone the Repository (Telegram Branch)

```bash
# Clone the repository
git clone <repository-url>

# Navigate to the project directory
cd yt-dlp-proxy

# Switch to the telegram branch (if it exists)
git checkout telegram
# OR if the branch doesn't exist yet, you may need to create it or use main/master
```

### 2. Install System Dependencies

```bash
# Update package list
sudo apt update

# Install Python 3 and pip (if not already installed)
sudo apt install -y python3 python3-pip python3-venv

# Install FFmpeg (required for yt-dlp video/audio merging)
sudo apt install -y ffmpeg

# Verify FFmpeg installation
ffmpeg -version
```

### 3. Create Virtual Environment

```bash
# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate
```

### 4. Install Python Dependencies

```bash
# Upgrade pip
pip install --upgrade pip

# Install project dependencies
pip install -r requirements.txt

# Install python-telegram-bot (required for Telegram bot)
pip install python-telegram-bot

# Install FastAPI and uvicorn (for webhook server)
pip install fastapi uvicorn
```

### 5. Set Up Environment Variables

Create a `.env` file in the project root:

```bash
# Create .env file
nano .env
```

Add your Telegram bot token:

```
BOT_TOKEN=your_telegram_bot_token_here
```

**To get a bot token:**
1. Open Telegram and search for `@BotFather`
2. Send `/newbot` and follow the instructions
3. Copy the token provided by BotFather
4. Paste it in the `.env` file

### 6. Initialize Proxy List

Before running the bot, you need to update the proxy list:

```bash
# Make sure you're in the virtual environment
source venv/bin/activate

# Update proxy list (this may take a few minutes)
python3 main.py update --max-workers 4
```

This will:
- Fetch proxies from all configured providers
- Test each proxy for speed
- Save the best 5 proxies to `proxy.json`

### 7. Create Your Telegram Bot Script

The `telegram_bot_example.py` file contains example code. You'll need to create a proper bot script using FastAPI and webhooks.

Create `bot.py`:

```python
from main import download_to_telegram
import os
from telegram.ext import Application, MessageHandler, filters
from telegram import Update
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import Response
import uvicorn

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', 'your-secret-token-here')
WEBHOOK_PATH = os.getenv('WEBHOOK_PATH', '/webhook')
HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', '8000'))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not set in .env file")

# Create FastAPI app
app = FastAPI()

# Create Telegram application
application = Application.builder().token(BOT_TOKEN).build()

async def handle_youtube_download(update: Update, context):
    """Handle YouTube URL from user and send video to Telegram."""
    url = update.message.text
    
    # Send "Downloading..." message
    status_msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="📥 Downloading video... Please wait."
    )
    
    try:
        # Download video to temporary file
        result = download_to_telegram(
            urls=url,
            yt_dlp_options={
                'format': 'bestvideo+bestaudio/best',
                'merge_output_format': 'mp4',
                'quiet': True,
            },
            verbose=False,
        )
        
        if not result['success']:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status_msg.message_id,
                text="❌ Download failed. Please try again."
            )
            return
        
        file_path = result['file_path']
        title = result['title']
        duration = result['duration']
        
        # Check file size (Telegram has a 50MB limit for bots)
        file_size = os.path.getsize(file_path) / (1024 * 1024)  # Size in MB
        
        if file_size > 50:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status_msg.message_id,
                text=f"❌ File too large ({file_size:.1f}MB). Telegram limit is 50MB."
            )
            result['cleanup']()
            return
        
        # Update status
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=status_msg.message_id,
            text=f"📤 Uploading: {title}"
        )
        
        # Send video to Telegram
        with open(file_path, 'rb') as video_file:
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=video_file,
                caption=f"🎬 {title}",
                duration=duration,
                supports_streaming=True,
            )
        
        # Delete status message
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=status_msg.message_id
        )
        
        # Clean up temporary file
        result['cleanup']()
        
    except Exception as e:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=status_msg.message_id,
            text=f"❌ Error: {str(e)}"
        )
        if 'result' in locals() and result.get('cleanup'):
            result['cleanup']()

# Register handlers
application.add_handler(
    MessageHandler(
        filters.Regex(r'(youtube\.com|youtu\.be)'),
        handle_youtube_download
    )
)

@app.post(WEBHOOK_PATH)
async def webhook(request: Request):
    """Handle incoming webhook requests from Telegram."""
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return Response()

@app.on_event("startup")
async def startup():
    """Initialize bot on startup."""
    await application.initialize()
    await application.start()
    await application.updater.start_webhook(
        listen=HOST,
        port=PORT,
        url_path=WEBHOOK_PATH,
        webhook_url=f"https://your-domain.com{WEBHOOK_PATH}",  # Update with your domain
        secret_token=WEBHOOK_SECRET,
    )
    print(f"🤖 Bot webhook started on {HOST}:{PORT}{WEBHOOK_PATH}")

@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    await application.updater.stop()
    await application.stop()
    await application.shutdown()

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "bot": "running"}

if __name__ == '__main__':
    uvicorn.run(app, host=HOST, port=PORT)
```

**Update your `.env` file to include webhook settings:**

```bash
nano .env
```

Add these lines:

```
BOT_TOKEN=your_telegram_bot_token_here
WEBHOOK_SECRET=your-random-secret-token-here
WEBHOOK_PATH=/webhook
HOST=0.0.0.0
PORT=8000
```

**Explanation of webhook settings:**
- **WEBHOOK_PATH** (required): The URL path where Telegram will send updates (e.g., `/webhook`). This must match the endpoint in your FastAPI app. You can use any path, but `/webhook` is standard.
- **WEBHOOK_SECRET** (optional but recommended): A secret token for security. Telegram will include this in the `X-Telegram-Bot-Api-Secret-Token` header. This helps verify requests are from Telegram, not attackers. **You generate this yourself** (see below).
- **HOST** and **PORT**: Where uvicorn will listen. `0.0.0.0` means listen on all interfaces.

**How to generate WEBHOOK_SECRET:**

The webhook secret is **not provided by Telegram** - you create it yourself. It's just a random string that you generate and then tell Telegram about when setting the webhook.

**Option 1: Using OpenSSL (recommended)**
```bash
openssl rand -hex 32
```
This will output something like: `a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6`

**Option 2: Using Python**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

**Option 3: Using online generator**
Visit https://randomkeygen.com/ and use a "Fort Knox Password" or generate a random hex string.

**Option 4: Just use any random string**
You can literally use any random string you want, like `my-super-secret-token-12345`, but a cryptographically random string is more secure.

Once you generate it, add it to your `.env` file and use the same value when setting the webhook with Telegram (see step 8 below).

**Important:** Replace `your-domain.com` in the bot.py file with your actual domain name or public IP address where the bot will be accessible.

### 8. Set Up Webhook URL (Required for Production)

Before running the bot, you need to set up the webhook URL with Telegram. You have two options:

**Option A: Using ngrok (for local testing)**

```bash
# Install ngrok (if not already installed)
# Download from https://ngrok.com/download

# Start ngrok tunnel
ngrok http 8000

# Copy the HTTPS URL (e.g., https://abc123.ngrok.io)
# Update the webhook_url in bot.py with this URL
```

**Option B: Using your server's public IP/domain**

If your server has a public IP or domain:
1. Make sure port 8000 (or your chosen port) is open in your firewall
2. Update the `webhook_url` in `bot.py` with your domain/IP
3. Ensure you have SSL/TLS (HTTPS) - Telegram requires HTTPS for webhooks

**Set the webhook manually (alternative):**

```bash
# Generate a secret token first (if you haven't already)
openssl rand -hex 32

# Set webhook using curl (replace with your actual values)
# Use the same secret_token you put in your .env file
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-domain.com/webhook", "secret_token": "your-generated-secret-here"}'
```

**Note:** The `secret_token` in the curl command must match the `WEBHOOK_SECRET` value in your `.env` file. If you don't want to use a secret token, you can omit the `secret_token` field from the curl command and leave `WEBHOOK_SECRET` empty in your `.env` file.

### 9. Test the Bot Locally

```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Run the bot with uvicorn (specify host and port)
uvicorn bot:app --host 0.0.0.0 --port 8000

# Or use the default settings from .env
python3 bot.py
```

**Or run with custom host/port directly:**

```bash
uvicorn bot:app --host 127.0.0.1 --port 8080
```

Test by sending a YouTube URL to your bot on Telegram.

### 10. Set Up as a System Service (Optional - for Production)

Create a systemd service file for running the bot in the background:

```bash
sudo nano /etc/systemd/system/yt-dlp-bot.service
```

Add the following content (adjust paths as needed):

```ini
[Unit]
Description=yt-dlp-proxy Telegram Bot
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/yt-dlp-proxy
Environment="PATH=/path/to/yt-dlp-proxy/venv/bin"
# Using uvicorn with custom host and port
ExecStart=/path/to/yt-dlp-proxy/venv/bin/uvicorn bot:app --host 0.0.0.0 --port 8000
# Or use environment variables from .env
# ExecStart=/path/to/yt-dlp-proxy/venv/bin/python3 /path/to/yt-dlp-proxy/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Alternative: Using environment variables in systemd**

You can also pass environment variables directly in the service file:

```ini
[Unit]
Description=yt-dlp-proxy Telegram Bot
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/yt-dlp-proxy
Environment="PATH=/path/to/yt-dlp-proxy/venv/bin"
EnvironmentFile=/path/to/yt-dlp-proxy/.env
ExecStart=/path/to/yt-dlp-proxy/venv/bin/uvicorn bot:app --host ${HOST} --port ${PORT}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable yt-dlp-bot

# Start the service
sudo systemctl start yt-dlp-bot

# Check status
sudo systemctl status yt-dlp-bot

# View logs
sudo journalctl -u yt-dlp-bot -f
```

### 11. Maintenance Commands

```bash
# Update proxy list (run periodically)
source venv/bin/activate
python3 main.py update --max-workers 4

# Restart the bot service (if using systemd)
sudo systemctl restart yt-dlp-bot

# View recent logs
sudo journalctl -u yt-dlp-bot -n 50
```

## Troubleshooting

### Bot not responding
- Check if the bot is running: `sudo systemctl status yt-dlp-bot`
- Check logs: `sudo journalctl -u yt-dlp-bot -f`
- Verify BOT_TOKEN is correct in `.env`

### Downloads failing
- Update proxy list: `python3 main.py update`
- Check FFmpeg: `ffmpeg -version`
- Check disk space: `df -h`

### Proxy errors
- Run proxy update: `python3 main.py update --max-workers 4`
- Check internet connectivity
- Verify proxy.json exists: `ls -la proxy.json`

## Quick Reference

```bash
# Full setup (one-time)
git clone <repo-url> && cd yt-dlp-proxy
git checkout telegram  # if branch exists
sudo apt update && sudo apt install -y python3 python3-pip python3-venv ffmpeg
python3 -m venv venv && source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt python-telegram-bot fastapi uvicorn

# Generate webhook secret
WEBHOOK_SECRET=$(openssl rand -hex 32)
echo "Generated secret: $WEBHOOK_SECRET"

# Create .env file
cat > .env << EOF
BOT_TOKEN=your_token
WEBHOOK_SECRET=$WEBHOOK_SECRET
WEBHOOK_PATH=/webhook
HOST=0.0.0.0
PORT=8000
EOF

python3 main.py update

# Run bot with uvicorn
source venv/bin/activate
uvicorn bot:app --host 0.0.0.0 --port 8000

# Or with custom host/port
uvicorn bot:app --host 127.0.0.1 --port 8080

# Generate webhook secret (if needed later)
openssl rand -hex 32
```

