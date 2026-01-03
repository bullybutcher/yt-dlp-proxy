"""
Example usage of yt-dlp-proxy as a Python import.

This demonstrates how to use yt-dlp-proxy in your Telegram bot or other Python scripts.

IMPORTANT: yt-dlp requires ffmpeg as an external binary (not a Python package).
Make sure ffmpeg is installed on your system and accessible in PATH, or specify
its location using the ffmpeg_location parameter.
"""

from main import download_with_proxy, update_proxies, get_proxy, load_proxies, check_ffmpeg_available

# Example 1: Check ffmpeg availability
def example_check_ffmpeg():
    """Check if ffmpeg is available."""
    if check_ffmpeg_available():
        print("✓ ffmpeg is available")
    else:
        print("✗ ffmpeg not found in PATH. Install ffmpeg or specify its location.")


# Example 2: Simple download with automatic proxy selection
def example_simple_download():
    """Download a video with automatic proxy selection."""
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    # Simple download - will automatically select a proxy
    success = download_with_proxy(
        urls=url,
        yt_dlp_options={
            'format': 'best',
            'outtmpl': 'downloads/%(title)s.%(ext)s'
        }
    )
    
    if success:
        print("Download successful!")
    else:
        print("Download failed after retries")


# Example 2b: Download with custom ffmpeg location
def example_download_with_custom_ffmpeg():
    """Download with custom ffmpeg path (if not in PATH)."""
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    # If ffmpeg is not in PATH, specify its location
    success = download_with_proxy(
        urls=url,
        yt_dlp_options={
            'format': 'bestvideo+bestaudio/best',
            'merge_output_format': 'mp4',  # Requires ffmpeg
            'outtmpl': 'downloads/%(title)s.%(ext)s'
        },
        ffmpeg_location='/usr/bin/ffmpeg'  # or 'C:\\ffmpeg\\bin\\ffmpeg.exe' on Windows
    )
    
    return success


# Example 3: Download with specific options (for Telegram bot)
def example_telegram_bot_download(url, chat_id):
    """Example function for Telegram bot integration."""
    try:
        # Download with custom options
        success = download_with_proxy(
            urls=url,
            yt_dlp_options={
                'format': 'bestvideo+bestaudio/best',
                'merge_output_format': 'mp4',
                'outtmpl': f'downloads/{chat_id}/%(title)s.%(ext)s',
                'quiet': False,  # Set to True to suppress output
            },
            verbose=True  # Set to False in production to reduce logs
        )
        
        return success
    except Exception as e:
        print(f"Error: {e}")
        return False


# Example 4: Update proxies programmatically
def example_update_proxies():
    """Update the proxy list."""
    proxies = update_proxies(
        max_workers=4,
        verbose=True  # Set to False to suppress output
    )
    print(f"Updated {len(proxies)} proxies")
    return proxies


# Example 5: Get a specific proxy and use it
def example_use_specific_proxy():
    """Use a specific proxy for multiple downloads."""
    proxy = get_proxy()
    if proxy:
        print(f"Using proxy: {proxy['host']}:{proxy['port']}")
        
        # Use the same proxy for multiple downloads
        urls = [
            "https://www.youtube.com/watch?v=video1",
            "https://www.youtube.com/watch?v=video2",
        ]
        
        for url in urls:
            download_with_proxy(
                urls=url,
                proxy=proxy,  # Reuse the same proxy
                yt_dlp_options={'format': 'best'},
                verbose=False
            )


# Example 6: Load and inspect proxies
def example_inspect_proxies():
    """Load and inspect available proxies."""
    proxies = load_proxies()
    print(f"Total proxies available: {len(proxies)}")
    
    for i, proxy in enumerate(proxies[:3], 1):  # Show first 3
        print(f"\nProxy {i}:")
        print(f"  Host: {proxy.get('host')}:{proxy.get('port')}")
        print(f"  Location: {proxy.get('city')}, {proxy.get('country')}")
        print(f"  Speed: {proxy.get('time')}s")


if __name__ == "__main__":
    # Check ffmpeg first
    example_check_ffmpeg()
    
    # Uncomment to test:
    # example_simple_download()
    # example_update_proxies()
    # example_inspect_proxies()
    pass

