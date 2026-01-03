## yt-dlp-proxy Guide

yt-dlp-proxy is a script designed to help you avoid throttling and bans by automatically selecting the best proxy for yt-dlp. 

## Quick Start

### Option 1: Use the Python Script (Development)
```bash
python3 main.py
```

### Option 2: Build and install binary (Recommended)

```bash
make build
make install
```

## Usage

#### Update proxy list
```bash
yt-dlp-proxy update
```

This will also perform a speed test for each free proxy and select the best one available.

By default, yt-dlp-proxy uses only two parallel threads to test the proxy, but using the `--max-workers` parameter, you can set the desired number of worker threads to speed up proxy testing. Before setting this parameter, make sure that your Internet bandwidth allows you to do this.

```bash
yt-dlp-proxy update --max-workers 10
```

#### Download with yt-dlp-proxy
Use yt-dlp-proxy just like you would use yt-dlp! Pass all the arguments to yt-dlp-proxy instead.
Example:

```bash
yt-dlp-proxy --format bv[vcodec^=avc!]+ba https://www.youtube.com/watch?v=bQB0_4BG-9F
```

If the proxy becomes slow over time, rerun the update command to refresh the proxy selection.

## Using as a Python Import

yt-dlp-proxy can be imported and used programmatically in your Python scripts (e.g., Telegram bots, web applications).

### Important: FFmpeg Requirement

**yt-dlp requires ffmpeg as an external binary** (not a Python package). Even though yt-dlp-proxy is written in Python, yt-dlp calls ffmpeg as a subprocess for operations like:
- Merging separate video and audio streams
- Converting formats
- Post-processing operations

**Installation:**
- **Linux/Ubuntu:** `sudo apt install ffmpeg`
- **macOS:** `brew install ffmpeg`
- **Windows:** Download from [ffmpeg.org](https://ffmpeg.org/download.html) or use `choco install ffmpeg`

**Verification:**
```bash
ffmpeg -version
```

If ffmpeg is not in your PATH, you can specify its location:
```python
download_with_proxy(
    urls="...",
    yt_dlp_options={'ffmpeg_location': '/path/to/ffmpeg'},
    # or use the ffmpeg_location parameter directly
    ffmpeg_location='/path/to/ffmpeg'
)
```

### Basic Usage

```python
from main import download_with_proxy, update_proxies, get_proxy

# Download a video with automatic proxy selection
success = download_with_proxy(
    urls="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    yt_dlp_options={
        'format': 'best',
        'outtmpl': 'downloads/%(title)s.%(ext)s'
    }
)
```

### API Reference

#### `download_with_proxy(urls, yt_dlp_options=None, proxy=None, proxy_file="proxy.json", max_retries=10, verbose=True)`

Download using yt-dlp with a proxy.

**Parameters:**
- `urls`: URL string or list of URLs to download
- `yt_dlp_options`: Dictionary of yt-dlp options (e.g., `{'format': 'best', 'outtmpl': 'video.%(ext)s'}`)
- `proxy`: Proxy dictionary to use. If `None`, a random proxy will be selected from `proxy_file`
- `proxy_file`: Name of the proxy file to load proxies from (default: `"proxy.json"`)
- `max_retries`: Maximum number of retries with different proxies on error (default: `10`)
- `verbose`: Whether to print status messages (default: `True`)

**Returns:** `True` if successful, `False` if failed after max_retries

**Raises:** `FileNotFoundError` if proxy_file doesn't exist, `yt_dlp.utils.DownloadError` for non-retryable errors

#### `update_proxies(max_workers=2, filename="proxy.json", verbose=True)`

Update the proxies list and save the best ones.

**Parameters:**
- `max_workers`: Number of concurrent threads for testing proxies (default: `2`)
- `filename`: Name of the proxy file to save (default: `"proxy.json"`)
- `verbose`: Whether to print progress messages (default: `True`)

**Returns:** List of best proxies

#### `get_proxy(filename="proxy.json")`

Get a random proxy from the proxy file.

**Parameters:**
- `filename`: Name of the proxy file (default: `"proxy.json"`)

**Returns:** Proxy dictionary or `None` if file not found

#### `load_proxies(filename="proxy.json")`

Load proxies from a JSON file.

**Parameters:**
- `filename`: Name of the proxy file (default: `"proxy.json"`)

**Returns:** List of proxy dictionaries

### Example: Telegram Bot Integration

```python
from main import download_with_proxy

def handle_download_command(url, chat_id):
    """Handle download command in Telegram bot."""
    try:
        success = download_with_proxy(
            urls=url,
            yt_dlp_options={
                'format': 'bestvideo+bestaudio/best',
                'merge_output_format': 'mp4',
                'outtmpl': f'downloads/{chat_id}/%(title)s.%(ext)s',
            },
            verbose=False  # Set to False to reduce logs in production
        )
        return success
    except Exception as e:
        print(f"Error: {e}")
        return False
```

See `example_usage.py` for more examples.


### Creating custom proxy providers

First you need to create new py module in proxy_providers directory using this code template:
```
import requests
from proxy_provider import ProxyProvider

class SomeProxyProvider(ProxyProvider):
    """
    Someproxy provider
    """
    PROXIES_LIST_URL = "https://goodproxies.net/list.json"

    def fetch_proxies(self):
        """Fetch proxies from goodproxies.net"""
        response = requests.get(self.PROXIES_LIST_URL, timeout=5)
        response.raise_for_status()
        response_json = response.json()
        return_list = []
        for server in response_json["data"]["servers"]["10501"]["proxies"]:
            return_list.append(
                {
                    "city": "Unknown city",
                    "country": server["country"].upper(),
                    "host": server["proxy"].split(":")[0],
                    "port": server["proxy"].split(":")[1],
                    "username": response_json["data"]["servers"]["10501"]["credentials"]["username"],
                    "password": response_json["data"]["servers"]["10501"]["credentials"]["password"]
                }
            )
        return return_list
```
As you can see, this script uses one json structure for all providers. In example code we've "converted" json response from server to python dictionary, compatible with yt-dlp-proxy. Here is basic example of json structure yt-dlp-proxy uses:
```
[
  {
    "city": "City1",
    "country": "Country1",
    "host": "0.0.0.0",
    "password": "password123",
    "port": "proxy_port",
    "username": "squid_username"
  }
]
```
Please note that all proxy providers are loaded automatically and you don't need to import them manually in ```main.py```

