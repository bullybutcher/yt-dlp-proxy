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
    import shutil
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


def download_to_telegram(urls, yt_dlp_options=None, proxy=None, proxy_file="proxy.json", max_retries=10, verbose=True, ffmpeg_location=None):
    """Download using yt-dlp with a proxy and return file path for Telegram upload.
    
    This function is designed for Telegram bots - it downloads to a temporary file
    and returns the file path and metadata. The file can be sent to Telegram and
    optionally cleaned up afterward.
    
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
        cleanup: (Deprecated) This parameter is ignored. Always call cleanup() manually after sending to Telegram.
        
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
    
    # Default options optimized for Telegram (best quality, merged, mp4)
    if yt_dlp_options is None:
        yt_dlp_options = {
            'format': 'bestvideo+bestaudio/best',
            'merge_output_format': 'mp4',
            'quiet': not verbose,
            'no_warnings': not verbose,
        }
    
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
