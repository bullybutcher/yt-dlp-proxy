"""
Example Telegram bot integration using yt-dlp-proxy.

This example shows how to download YouTube videos and send them directly to Telegram
without storing them permanently on disk.

Setup:
1. Set BOT_TOKEN environment variable:
   export BOT_TOKEN="your_bot_token_here"
   
   Or create a .env file:
   BOT_TOKEN=your_bot_token_here

2. Install python-telegram-bot:
   pip install python-telegram-bot
"""

from main import download_to_telegram
import os
import asyncio
from telegram import Bot
from telegram.error import TelegramError

# Try to load from .env file (optional - requires python-dotenv)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, skip .env loading

# Get bot token from environment variable
BOT_TOKEN = os.getenv('BOT_TOKEN')

if not BOT_TOKEN:
    raise ValueError(
        "BOT_TOKEN environment variable is not set. "
        "Please set it using: export BOT_TOKEN='your_token_here' "
        "or create a .env file with BOT_TOKEN=your_token_here"
    )


async def handle_youtube_download(update, context):
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
        import os
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


async def handle_audio_download(update, context):
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


# Example usage with python-telegram-bot library
"""
from telegram.ext import Application, MessageHandler, filters

def main():
    # BOT_TOKEN is loaded from environment variable (see top of file)
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Handle YouTube URLs
    application.add_handler(
        MessageHandler(
            filters.Regex(r'(youtube\.com|youtu\.be)'),
            handle_youtube_download
        )
    )
    
    application.run_polling()

if __name__ == '__main__':
    main()
"""

