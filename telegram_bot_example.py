"""
Example Telegram bot integration using yt-dlp-proxy with FastAPI and uvicorn.

This example shows how to download YouTube videos and send them directly to Telegram
without storing them permanently on disk, using webhooks instead of polling.

Setup:
1. Set environment variables in .env file:
   BOT_TOKEN=your_bot_token_here
   WEBHOOK_SECRET=your-random-secret-token-here  # Optional but recommended for security
   WEBHOOK_PATH=/webhook  # Required: the endpoint path
   HOST=0.0.0.0
   PORT=8000
   WEBHOOK_URL=https://your-domain.com/webhook  # Update with your actual domain
   
   Note: WEBHOOK_SECRET is optional but recommended. Generate with: openssl rand -hex 32

2. Install dependencies:
   pip install python-telegram-bot fastapi uvicorn python-dotenv

3. Run with uvicorn:
   uvicorn telegram_bot_example:app --host 0.0.0.0 --port 8000
   
   Or with custom host/port:
   uvicorn telegram_bot_example:app --host 127.0.0.1 --port 8080
"""

from main import download_to_telegram
import os
from telegram import Update
from telegram.ext import Application, MessageHandler, filters
from fastapi import FastAPI, Request
from fastapi.responses import Response
import uvicorn

# Try to load from .env file (optional - requires python-dotenv)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, skip .env loading

# Get configuration from environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', 'your-secret-token-here')
WEBHOOK_PATH = os.getenv('WEBHOOK_PATH', '/webhook')
HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', '8000'))
WEBHOOK_URL = os.getenv('WEBHOOK_URL', f'https://your-domain.com{WEBHOOK_PATH}')

if not BOT_TOKEN:
    raise ValueError(
        "BOT_TOKEN environment variable is not set. "
        "Please set it in .env file or export BOT_TOKEN='your_token_here'"
    )

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
                'quiet': True,  # Suppress yt-dlp output
            },
            verbose=False,  # Set to True for debugging
            cleanup=False,  # Don't auto-cleanup - we'll do it after sending
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
        
        # Update status
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=status_msg.message_id,
            text=f"📤 Uploading: {title}"
        )
        
        # Check file size (Telegram has a 50MB limit for bots)
        file_size = os.path.getsize(file_path) / (1024 * 1024)  # Size in MB
        
        if file_size > 50:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status_msg.message_id,
                text=f"❌ File too large ({file_size:.1f}MB). Telegram limit is 50MB.\n"
                     f"Consider downloading audio only or using a different format."
            )
            result['cleanup']()  # Clean up the file
            return
        
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
        # Clean up on error
        if 'result' in locals() and result.get('cleanup'):
            result['cleanup']()


async def handle_audio_download(update: Update, context):
    """Download audio only and send as audio file."""
    url = update.message.text
    
    status_msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="📥 Downloading audio... Please wait."
    )
    
    try:
        result = download_to_telegram(
            urls=url,
            yt_dlp_options={
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': True,
            },
            verbose=False,
            cleanup=False,
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
        
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=status_msg.message_id,
            text=f"📤 Uploading: {title}"
        )
        
        # Send audio to Telegram
        with open(file_path, 'rb') as audio_file:
            await context.bot.send_audio(
                chat_id=update.effective_chat.id,
                audio=audio_file,
                title=title,
            )
        
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=status_msg.message_id
        )
        
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

# Optional: Add audio download handler (uncomment if needed)
# application.add_handler(
#     MessageHandler(
#         filters.Regex(r'(youtube\.com|youtu\.be).*audio'),
#         handle_audio_download
#     )
# )

@app.post(WEBHOOK_PATH)
async def webhook(request: Request):
    """Handle incoming webhook requests from Telegram."""
    # Validate secret token if configured (security check)
    if WEBHOOK_SECRET and WEBHOOK_SECRET != 'your-secret-token-here':
        secret_header = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
        if secret_header != WEBHOOK_SECRET:
            return Response(status_code=403)  # Forbidden if secret doesn't match
    
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
        webhook_url=WEBHOOK_URL,
        secret_token=WEBHOOK_SECRET,
    )
    print(f"🤖 Bot webhook started on {HOST}:{PORT}{WEBHOOK_PATH}")
    print(f"📡 Webhook URL: {WEBHOOK_URL}")

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

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}

if __name__ == '__main__':
    uvicorn.run(app, host=HOST, port=PORT)

