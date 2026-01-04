import requests
import random
import os
import io
import time
import sys
import json
import importlib
import inspect
import tempfile
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from proxy_provider import ProxyProvider
from proxy_providers import *
from tqdm import tqdm
import yt_dlp

SPEEDTEST_URL = "http://212.183.159.230/5MB.zip"

if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
elif __file__:
    application_path = os.path.dirname(__file__)

def is_valid_proxy(proxy):
    """Check if the proxy is valid."""
    return proxy.get("host") is not None and proxy.get("country") != "Russia" and proxy.get("country") != "RU"


def construct_proxy_string(proxy):
    """Construct a proxy string from the proxy dictionary."""
    if proxy.get("username"):
        return (
            f'{proxy["username"]}:{proxy["password"]}@{proxy["host"]}:{proxy["port"]}'
        )
    return f'{proxy["host"]}:{proxy["port"]}'


def test_proxy(proxy):
    """Test the proxy by measuring the download time."""
    proxy_str = construct_proxy_string(proxy)
    start_time = time.perf_counter()
    try:
        response = requests.get(
            SPEEDTEST_URL,
            stream=True,
            proxies={"http": f"http://{proxy_str}"},
            timeout=5,
        )
        response.raise_for_status()  # Ensure we raise an error for bad responses

        total_length = response.headers.get("content-length")
        if total_length is None or int(total_length) != 5242880:
            return None

        with io.BytesIO() as f:
            download_time, _ = download_with_progress(
                response, f, total_length, start_time
            )
            return {"time": download_time, **proxy}  # Include original proxy info
    except requests.RequestException:
        return None


def download_with_progress(response, f, total_length, start_time):
    """Download content from the response with progress tracking."""
    downloaded_bytes = 0
    for chunk in response.iter_content(1024):
        downloaded_bytes += len(chunk)
        f.write(chunk)
        done = int(30 * downloaded_bytes / int(total_length))
        if done == 6:
            break
        if (
            done > 3
            and (downloaded_bytes // (time.perf_counter() - start_time) / 100000) < 1.0
        ):
            return float("inf"), downloaded_bytes
    return round(time.perf_counter() - start_time, 2), downloaded_bytes


def get_proxy_file_path(filename="proxy.json"):
    """Get the full path to the proxy file."""
    return os.path.join(os.path.split(application_path)[0], filename)


def save_proxies_to_file(proxies, filename="proxy.json", verbose=True):
    """Save the best proxies to a JSON file."""
    json_path = get_proxy_file_path(filename)
    with open(json_path, "w") as f:
        json.dump(proxies, f, indent=4)
    if verbose:
        print(f"proxy.json saved to {json_path}")


def load_proxies(filename="proxy.json"):
    """Load proxies from a JSON file."""
    json_path = get_proxy_file_path(filename)
    with open(json_path, "r") as f:
        return json.load(f)


def get_best_proxies(providers, max_workers):
    """Return the top five proxies based on speed from all providers."""
    all_proxies = []
    proxies = None
    for provider in providers:
        try:
            print(f"Fetching proxies from {provider.__class__.__name__}")
            proxies = provider.fetch_proxies()
            all_proxies.extend([proxy for proxy in proxies if is_valid_proxy(proxy)])
        except Exception as e:
            print(f"Failed to fetch proxies from {provider.__class__.__name__}: {e}")

    best_proxies = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(test_proxy, proxy): proxy for proxy in all_proxies}
        for future in tqdm(as_completed(futures), total=len(futures), desc="Testing proxies", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_noinv_fmt}]", unit=' proxies', unit_scale=True, ncols=80):
            result = future.result()
            if result is not None:
                best_proxies.append(result)
    return sorted(best_proxies, key=lambda x: x["time"])[:5]


def update_proxies(max_workers=2, filename="proxy.json", verbose=True):
    """Update the proxies list and save the best ones.
    
    Args:
        max_workers: Number of concurrent threads for testing proxies
        filename: Name of the proxy file to save
        verbose: Whether to print progress messages
    
    Returns:
        List of best proxies
    """
    providers = []
    for filename_provider in os.listdir(os.path.join(os.path.dirname(__file__), "proxy_providers")):
        # Check if the file is a Python module
        if filename_provider.endswith(".py") and filename_provider != "__init__.py":
            module_name = filename_provider[:-3]  # Remove the '.py' suffix
            module_path = f'{"proxy_providers"}.{module_name}'
            module = importlib.import_module(module_path)
            classes = inspect.getmembers(module, inspect.isclass)
            providers.append(
                [classs[-1]() for classs in classes if classs[0] != "ProxyProvider"][0]
            )
    if verbose:
        print(f"Using up to {max_workers} concurrent threads")    
    best_proxies = get_best_proxies(providers, max_workers)
    save_proxies_to_file(best_proxies, filename, verbose)
    if verbose:
        print("All done.")
    return best_proxies


def get_proxy(filename="proxy.json"):
    """Get a random proxy from the proxy file.
    
    Args:
        filename: Name of the proxy file
        
    Returns:
        Proxy dictionary or None if file not found
    """
    try:
        proxies = load_proxies(filename)
        return random.choice(proxies)
    except FileNotFoundError:
        return None


def check_ffmpeg_available():
    """Check if ffmpeg is available in the system PATH.
    
    Returns:
        True if ffmpeg is available, False otherwise
    """
    return shutil.which('ffmpeg') is not None


def download_with_proxy(urls, yt_dlp_options=None, proxy=None, proxy_file="proxy.json", max_retries=10, verbose=True, ffmpeg_location=None):
    """Download using yt-dlp with a proxy (programmatic API).
    
    Note: yt-dlp uses ffmpeg as an external binary (not a Python package). 
    ffmpeg must be installed separately on your system. If ffmpeg is not in your PATH,
    you can specify its location using the ffmpeg_location parameter or in yt_dlp_options.
    
    Args:
        urls: URL or list of URLs to download
        yt_dlp_options: Dictionary of yt-dlp options (e.g., {'format': 'best', 'outtmpl': 'video.%(ext)s'})
        proxy: Proxy dictionary to use. If None, a random proxy will be selected from proxy_file
        proxy_file: Name of the proxy file to load proxies from
        max_retries: Maximum number of retries with different proxies on error
        verbose: Whether to print status messages
        ffmpeg_location: Path to ffmpeg executable (optional). If None, yt-dlp will search PATH.
                        You can also set this in yt_dlp_options as 'ffmpeg_location'.
        
    Returns:
        True if successful, False if failed after max_retries
        
    Raises:
        FileNotFoundError: If proxy_file doesn't exist and proxy is None
        yt_dlp.utils.DownloadError: For download errors that aren't retryable
    """
    if isinstance(urls, str):
        urls = [urls]
    
    if yt_dlp_options is None:
        yt_dlp_options = {}
    
    # Add ffmpeg location if specified
    if ffmpeg_location and 'ffmpeg_location' not in yt_dlp_options:
        yt_dlp_options['ffmpeg_location'] = ffmpeg_location
    
    # Configure JavaScript runtime (deno) if not already set
    if 'js_runtime' not in yt_dlp_options:
        # Try to find deno in PATH
        deno_path = shutil.which('deno')
        if deno_path:
            yt_dlp_options['js_runtime'] = f'deno:{deno_path}'
        else:
            # Fallback: just use 'deno' and let yt-dlp find it
            yt_dlp_options['js_runtime'] = 'deno'
    
    retries = 0
    used_proxies = set()
    
    while retries < max_retries:
        try:
            # Get proxy
            if proxy is None:
                proxies = load_proxies(proxy_file)
                # Try to avoid using the same proxy if we've used it before
                # Track by host:port to avoid duplicates
                available_proxies = [
                    p for p in proxies 
                    if f"{p.get('host')}:{p.get('port')}" not in used_proxies
                ]
                if not available_proxies:
                    available_proxies = proxies  # Reset if we've used all
                    used_proxies.clear()
                proxy = random.choice(available_proxies)
                used_proxies.add(f"{proxy.get('host')}:{proxy.get('port')}")
            
            proxy_str = construct_proxy_string(proxy)
            if verbose:
                city = proxy.get('city', 'Unknown')
                country = proxy.get('country', 'Unknown')
                print(f"Using proxy from {city}, {country}")
            
            # Prepare options
            opts = yt_dlp_options.copy()
            opts['proxy'] = f'http://{proxy_str}'
            
            # Create YoutubeDL instance and download
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download(urls)
            
            return True
            
        except FileNotFoundError:
            if verbose:
                print(f"'{proxy_file}' not found. Starting proxy list update...")
            update_proxies(filename=proxy_file, verbose=verbose)
            proxy = None  # Reset to get a new proxy
            retries += 1
            
        except (yt_dlp.utils.DownloadError, Exception) as e:
            error_msg = str(e)
            # Check for the specific errors we want to retry on
            if "Sign in to" in error_msg or "403" in error_msg:
                if verbose:
                    print("Got 'Sign in to confirm' or '403' error. Trying again with another proxy...")
                proxy = None  # Get a new proxy
                retries += 1
                continue
            # Re-raise other exceptions
            raise
    
    return False


def get_video_info_with_proxy(url, proxy=None, proxy_file="proxy.json", verbose=True):
    """Get video information without downloading to estimate file size.
    
    Args:
        url: URL to get info for
        proxy: Proxy dictionary to use. If None, a random proxy will be selected
        proxy_file: Name of the proxy file to load proxies from
        verbose: Whether to print status messages
        
    Returns:
        Dictionary with video info including filesize_approx, or None if failed
    """
    try:
        if proxy is None:
            proxies = load_proxies(proxy_file)
            proxy = random.choice(proxies)
        
        proxy_str = construct_proxy_string(proxy)
        opts = {
            'proxy': f'http://{proxy_str}',
            'quiet': not verbose,
            'no_warnings': not verbose,
        }
        
        # Configure JavaScript runtime (deno) if not already set
        deno_path = shutil.which('deno')
        if deno_path:
            opts['js_runtime'] = f'deno:{deno_path}'
        else:
            opts['js_runtime'] = 'deno'
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info
    except Exception as e:
        if verbose:
            print(f"Error getting video info: {e}")
        return None


def select_appropriate_format(info, max_size_mb=50, verbose=True):
    """Select an appropriate format based on expected file size.
    
    Analyzes available formats to find the best quality that fits within the size limit.
    Uses actual format information rather than simple heuristics.
    
    Args:
        info: Video info dictionary from yt-dlp (can be None)
        max_size_mb: Maximum file size in MB (default 50MB for Telegram)
        verbose: Whether to print status messages
        
    Returns:
        Format string for yt-dlp
    """
    # Handle None info
    if info is None:
        if verbose:
            print("No video info available, using safe default format")
        # Safe default: prefer MP4, avoid MKV, reasonable quality
        return 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio/best[ext=mp4]/bestvideo+bestaudio[ext=m4a]/bestvideo+bestaudio/best'
    
    max_size_bytes = max_size_mb * 1024 * 1024
    duration = info.get('duration', 0)
    formats = info.get('formats', [])
    
    # Quick check: if best format fits, use it
    filesize_approx = info.get('filesize_approx') or info.get('filesize')
    if filesize_approx and filesize_approx <= max_size_bytes:
        if verbose:
            print(f"Best quality fits ({filesize_approx/(1024*1024):.1f}MB <= {max_size_mb}MB), using best quality")
        # Best quality fits, but still prefer MP4 for mobile compatibility
        return 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio/best[ext=mp4]/bestvideo+bestaudio[ext=m4a]/bestvideo+bestaudio/best'
    
    if not formats:
        # No format list available, use fallback selector
        if verbose:
            print("No format list available, using fallback selector")
        return 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480][ext=mp4]+bestaudio/best[ext=mp4]/best'
    
    # Analyze available formats to find best quality that fits
    if verbose:
        print(f"Analyzing {len(formats)} available formats to find best quality within {max_size_mb}MB limit...")
    
    # Separate video-only, audio-only, and combined formats
    video_formats = []
    audio_formats = []
    combined_formats = []
    
    for fmt in formats:
        vcodec = fmt.get('vcodec', 'none')
        acodec = fmt.get('acodec', 'none')
        has_video = vcodec != 'none'
        has_audio = acodec != 'none'
        
        # Check if format is MP4-compatible
        ext = fmt.get('ext', '').lower()
        container = fmt.get('container', '').lower()
        is_mp4_compatible = ext in ['mp4', 'm4v'] or container in ['mp4', 'm4v', 'm4a']
        
        # Skip formats that aren't MP4-compatible for mobile
        if not is_mp4_compatible:
            continue
        
        if has_video and has_audio:
            combined_formats.append(fmt)
        elif has_video:
            video_formats.append(fmt)
        elif has_audio:
            audio_formats.append(fmt)
    
    # Function to estimate file size for a format
    def estimate_format_size(fmt):
        """Estimate total file size for a format."""
        filesize = fmt.get('filesize') or fmt.get('filesize_approx')
        if filesize:
            return filesize
        
        # Estimate from bitrate and duration
        tbr = fmt.get('tbr')  # Total bitrate
        vbr = fmt.get('vbr')  # Video bitrate
        abr = fmt.get('abr')  # Audio bitrate
        
        if tbr and duration:
            # Total bitrate in kbps * duration in seconds / 8 = bytes
            return (tbr * 1000 * duration) / 8
        elif vbr and abr and duration:
            # Video + audio bitrates
            return ((vbr + abr) * 1000 * duration) / 8
        elif vbr and duration:
            # Video only, estimate audio at 128kbps
            return ((vbr + 128) * 1000 * duration) / 8
        elif abr and duration:
            # Audio only
            return (abr * 1000 * duration) / 8
        
        return None
    
    # Function to calculate quality score
    def quality_score(fmt):
        """Calculate quality score for a format (higher is better)."""
        height = fmt.get('height', 0) or 0
        width = fmt.get('width', 0) or 0
        fps = fmt.get('fps', 0) or 0
        tbr = fmt.get('tbr') or fmt.get('vbr') or 0
        
        # Score based on resolution, fps, and bitrate
        return (height * width) + (fps * 100) + (tbr * 10)
    
    # Check combined formats first (simpler, no merging needed)
    suitable_combined = []
    for fmt in combined_formats:
        size = estimate_format_size(fmt)
        if size and size <= max_size_bytes:
            suitable_combined.append({
                'format_id': fmt.get('format_id'),
                'quality_score': quality_score(fmt),
                'filesize': size,
                'height': fmt.get('height', 0),
                'width': fmt.get('width', 0),
            })
    
    if suitable_combined:
        # Sort by quality (highest first) and pick the best
        suitable_combined.sort(key=lambda x: x['quality_score'], reverse=True)
        best = suitable_combined[0]
        if verbose:
            print(f"Selected combined format: {best['width']}x{best['height']}, "
                  f"estimated size: {best['filesize']/(1024*1024):.1f}MB")
        return best['format_id']
    
    # Try video+audio combinations
    suitable_combinations = []
    
    # Sort video formats by quality (highest first)
    video_formats.sort(key=lambda x: quality_score(x), reverse=True)
    # Sort audio formats by quality (highest first)
    audio_formats.sort(key=lambda x: quality_score(x), reverse=True)
    
    # Try combinations of video + audio formats
    for vfmt in video_formats[:10]:  # Limit to top 10 video formats to avoid too many combinations
        v_size = estimate_format_size(vfmt)
        if not v_size:
            continue
        
        # Find best audio that fits with this video
        for afmt in audio_formats[:5]:  # Limit to top 5 audio formats
            a_size = estimate_format_size(afmt)
            if not a_size:
                continue
            
            total_size = v_size + a_size
            if total_size <= max_size_bytes:
                # Check if both are MP4-compatible
                v_ext = vfmt.get('ext', '').lower()
                a_ext = afmt.get('ext', '').lower()
                v_mp4 = v_ext in ['mp4', 'm4v']
                a_mp4 = a_ext in ['m4a', 'mp4', 'aac']
                
                if v_mp4 and a_mp4:
                    suitable_combinations.append({
                        'video_id': vfmt.get('format_id'),
                        'audio_id': afmt.get('format_id'),
                        'quality_score': quality_score(vfmt) + (quality_score(afmt) * 0.1),  # Video quality is more important
                        'filesize': total_size,
                        'height': vfmt.get('height', 0),
                        'width': vfmt.get('width', 0),
                    })
                    break  # Found best audio for this video, move to next video
    
    if suitable_combinations:
        # Sort by quality and pick the best
        suitable_combinations.sort(key=lambda x: x['quality_score'], reverse=True)
        best = suitable_combinations[0]
        if verbose:
            print(f"Selected video+audio combination: {best['width']}x{best['height']}, "
                  f"estimated size: {best['filesize']/(1024*1024):.1f}MB")
        return f"{best['video_id']}+{best['audio_id']}"
    
    # Fallback: use resolution-based selector (will try progressively lower resolutions)
    if verbose:
        print("No suitable format found in analysis, using fallback resolution-based selector")
    return 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720][ext=mp4]+bestaudio/bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480][ext=mp4]+bestaudio/best[ext=mp4]/best'


def download_to_telegram(urls, yt_dlp_options=None, proxy=None, proxy_file="proxy.json", max_retries=10, verbose=True, ffmpeg_location=None, max_file_size_mb=50):
    """Download using yt-dlp with a proxy and return file path for Telegram upload.
    
    This function is designed for Telegram bots - it downloads to a temporary file
    and returns the file path and metadata. The file can be sent to Telegram and
    optionally cleaned up afterward.
    
    The function automatically selects appropriate quality based on expected file size
    to stay within Telegram's 50MB limit, and ensures MP4 format for mobile compatibility.
    
    Note: yt-dlp uses ffmpeg as an external binary (not a Python package). 
    ffmpeg must be installed separately on your system.
    
    Args:
        urls: URL or list of URLs to download (only first URL is used)
        yt_dlp_options: Dictionary of yt-dlp options. Defaults to best quality video+audio merged.
        proxy: Proxy dictionary to use. If None, a random proxy will be selected from proxy_file
        proxy_file: Name of the proxy file to load proxies from
        max_retries: Maximum number of retries with different proxies on error
        verbose: Whether to print status messages
        ffmpeg_location: Path to ffmpeg executable (optional)
        max_file_size_mb: Maximum file size in MB (default 50MB for Telegram)
        
    Returns:
        Dictionary with keys:
            - 'success': bool - Whether download was successful
            - 'file_path': str - Path to downloaded file (None if failed)
            - 'title': str - Video title (None if failed)
            - 'ext': str - File extension (None if failed)
            - 'duration': int - Video duration in seconds (None if failed)
            - 'cleanup': callable - Function to delete the file manually if cleanup=False
        
    Raises:
        FileNotFoundError: If proxy_file doesn't exist and proxy is None
        yt_dlp.utils.DownloadError: For download errors that aren't retryable
    """
    if isinstance(urls, str):
        urls = [urls]
    
    # Use first URL only
    url = urls[0] if urls else None
    if not url:
        return {'success': False, 'file_path': None, 'title': None, 'ext': None, 'duration': None, 'cleanup': None}
    
    # Get video info first to estimate file size and select appropriate format
    if verbose:
        print("Getting video information...")
    video_info = get_video_info_with_proxy(url, proxy=proxy, proxy_file=proxy_file, verbose=verbose)
    
    # Select appropriate format based on file size
    # If video_info is None, use a safe default format (MP4, mobile-compatible)
    if video_info:
        selected_format = select_appropriate_format(video_info, max_size_mb=max_file_size_mb, verbose=verbose)
    else:
        if verbose:
            print("Could not get video info, using safe default format (MP4, mobile-compatible)")
        # Safe default: prefer MP4, avoid MKV, reasonable quality
        selected_format = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio/best[ext=mp4]/bestvideo+bestaudio[ext=m4a]/bestvideo+bestaudio/best'
    
    # Default options optimized for Telegram (mobile-friendly MP4 format)
    if yt_dlp_options is None:
        yt_dlp_options = {
            'format': selected_format,
            'merge_output_format': 'mp4',  # Always merge to MP4 for mobile compatibility
            'quiet': not verbose,
            'no_warnings': not verbose,
        }
    else:
        # Ensure merge_output_format is always mp4 for mobile compatibility
        if 'merge_output_format' not in yt_dlp_options:
            yt_dlp_options['merge_output_format'] = 'mp4'
        # Override format if not explicitly set to allow size-based selection
        if 'format' not in yt_dlp_options:
            yt_dlp_options['format'] = selected_format
    
    # Create temporary directory for download
    temp_dir = tempfile.mkdtemp(prefix='yt_dlp_telegram_')
    # Use a simple filename template in the temp directory
    temp_file_template = os.path.join(temp_dir, 'video.%(ext)s')
    
    # Add output template to options
    opts = yt_dlp_options.copy()
    opts['outtmpl'] = temp_file_template
    
    # Add ffmpeg location if specified
    if ffmpeg_location and 'ffmpeg_location' not in opts:
        opts['ffmpeg_location'] = ffmpeg_location
    
    # Configure JavaScript runtime (deno) if not already set
    if 'js_runtime' not in opts:
        # Try to find deno in PATH
        deno_path = shutil.which('deno')
        if deno_path:
            opts['js_runtime'] = f'deno:{deno_path}'
        else:
            # Fallback: just use 'deno' and let yt-dlp find it
            opts['js_runtime'] = 'deno'
    
    # Store info for return
    info_dict = {}
    
    def progress_hook(d):
        """Hook to capture video info during download."""
        if d['status'] == 'finished':
            info_dict.update(d.get('info_dict', {}))
    
    opts['progress_hooks'] = [progress_hook]
    
    retries = 0
    used_proxies = set()
    downloaded_file_path = None
    
    while retries < max_retries:
        try:
            # Get proxy
            if proxy is None:
                proxies = load_proxies(proxy_file)
                available_proxies = [
                    p for p in proxies 
                    if f"{p.get('host')}:{p.get('port')}" not in used_proxies
                ]
                if not available_proxies:
                    available_proxies = proxies
                    used_proxies.clear()
                proxy = random.choice(available_proxies)
                used_proxies.add(f"{proxy.get('host')}:{proxy.get('port')}")
            
            proxy_str = construct_proxy_string(proxy)
            if verbose:
                city = proxy.get('city', 'Unknown')
                country = proxy.get('country', 'Unknown')
                print(f"Using proxy from {city}, {country}")
            
            # Add proxy to options
            opts['proxy'] = f'http://{proxy_str}'
            
            # Create YoutubeDL instance and download
            with yt_dlp.YoutubeDL(opts) as ydl:
                # Extract info first to get title
                info = ydl.extract_info(url, download=False)
                info_dict.update(info)
                
                # Download the video
                ydl.download([url])
            
            # Find the downloaded file - yt-dlp may have added extension
            downloaded_file_path = None
            for file in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, file)
                if os.path.isfile(file_path) and not file.endswith('.part'):
                    downloaded_file_path = file_path
                    break
            
            if not downloaded_file_path or not os.path.exists(downloaded_file_path):
                # Try to find any file in the directory
                files = [f for f in os.listdir(temp_dir) if os.path.isfile(os.path.join(temp_dir, f))]
                if files:
                    downloaded_file_path = os.path.join(temp_dir, files[0])
                else:
                    raise Exception("Downloaded file not found")
            
            # Get file info
            title = info_dict.get('title', 'Unknown')
            ext = info_dict.get('ext', os.path.splitext(downloaded_file_path)[1].lstrip('.'))
            duration = info_dict.get('duration')
            
            # Ensure file extension is mp4 (for mobile compatibility)
            # If it's not mp4, we should have used merge_output_format='mp4', but double-check
            if ext and ext.lower() not in ['mp4', 'm4v']:
                if verbose:
                    print(f"Warning: File format is {ext}, expected MP4. This may not play well on mobile.")
            
            # Create cleanup function
            def cleanup_file():
                """Delete the temporary file and directory."""
                try:
                    if downloaded_file_path and os.path.exists(downloaded_file_path):
                        os.remove(downloaded_file_path)
                    if os.path.exists(temp_dir):
                        os.rmdir(temp_dir)
                except Exception as e:
                    if verbose:
                        print(f"Warning: Could not cleanup temp file: {e}")
            
            result = {
                'success': True,
                'file_path': downloaded_file_path,
                'title': title,
                'ext': ext,
                'duration': duration,
                'cleanup': cleanup_file  # Call this after sending to Telegram
            }
            
            return result
            
        except FileNotFoundError:
            if verbose:
                print(f"'{proxy_file}' not found. Starting proxy list update...")
            update_proxies(filename=proxy_file, verbose=verbose)
            proxy = None
            retries += 1
            
        except (yt_dlp.utils.DownloadError, Exception) as e:
            error_msg = str(e)
            if "Sign in to" in error_msg or "403" in error_msg:
                if verbose:
                    print("Got 'Sign in to confirm' or '403' error. Trying again with another proxy...")
                proxy = None
                retries += 1
                continue
            # Cleanup on error
            try:
                if downloaded_file_path and os.path.exists(downloaded_file_path):
                    os.remove(downloaded_file_path)
                if os.path.exists(temp_dir):
                    os.rmdir(temp_dir)
            except:
                pass
            raise
    
    # Cleanup on failure
    try:
        if downloaded_file_path and os.path.exists(downloaded_file_path):
            os.remove(downloaded_file_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)
    except:
        pass
    
    return {'success': False, 'file_path': None, 'title': None, 'ext': None, 'duration': None, 'cleanup': None}


def run_yt_dlp():
    """Run yt-dlp with a randomly selected proxy (CLI wrapper)."""
    # Parse command-line arguments (sys.argv already has script name removed by main())
    parser, opts, args = yt_dlp.parse_options(sys.argv)
    
    # Convert opts dict to yt_dlp_options format
    yt_dlp_options = opts
    
    # Download with proxy
    download_with_proxy(args, yt_dlp_options=yt_dlp_options, verbose=True)




def main():
    """Main function to handle script arguments and execute the appropriate command."""
    try:
        if "update" in sys.argv:
            if "--max-workers" in sys.argv:
                max_workers = int(sys.argv[sys.argv.index("--max-workers")+1])
            else:
                max_workers = 2
            update_proxies(max_workers)
        elif len(sys.argv) < 2:
            print(
                "usage: main.py update [--max-workers NUM] | <yt-dlp args>\n" \
           "Script for starting yt-dlp with best free proxy\n\n" \
           "Commands:\n" \
           "  update   Update best proxy [--max-workers NUM]"
            )
        else:
            sys.argv.pop(0)
            run_yt_dlp()
    except KeyboardInterrupt:
        print("Canceled by user")


if __name__ == "__main__":
    main()
