import os
import requests
import random
from urllib.parse import urlencode
from typing import List
from loguru import logger
from moviepy import VideoFileClip
from bs4 import BeautifulSoup

from app.models.schema import MaterialInfo, VideoAspect
from app.config import config
from app.utils import utils

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _get_tls_verify():
    return config.app.get("verify_ssl", True)

def get_api_key(key_name: str):
    keys = config.app.get(key_name, [])
    if not keys:
        return ""
    return random.choice(keys)

# ─────────────────────────────────────────────
# PEXELS - HD & Aspect-Aware Logic
# ─────────────────────────────────────────────
def search_videos_pexels(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    aspect = VideoAspect(video_aspect)
    video_width, video_height = aspect.to_resolution()
    api_key = get_api_key("pexels_api_keys")
    
    if not api_key:
        logger.warning("[pexels] No API key found in config")
        return []

    headers = {"Authorization": api_key}
    # Per_page increased to 40 to ensure we find high-quality candidates
    params = {
        "query": search_term, 
        "per_page": 40, 
        "orientation": "portrait" if aspect == VideoAspect.portrait else "landscape"
    }
    query_url = f"https://api.pexels.com/videos/search?{urlencode(params)}"
    
    try:
        r = requests.get(query_url, headers=headers, verify=_get_tls_verify(), timeout=30)
        response = r.json()
        video_items = []
        
        for v in response.get("videos", []):
            if v["duration"] < minimum_duration: 
                continue
            
            # Sort by width descending to find 4K/HD versions first
            sorted_files = sorted(v["video_files"], key=lambda x: x["width"], reverse=True)
            
            for video in sorted_files:
                # We prioritize files that meet our resolution threshold (at least 720p)
                if video["width"] >= 720 or video["height"] >= 720:
                    item = MaterialInfo()
                    item.provider = "pexels"
                    item.url = video["link"]
                    item.duration = v["duration"]
                    video_items.append(item)
                    break 
        return video_items
    except Exception as e:
        logger.error(f"[pexels] HD search failed: {str(e)}")
    return []

# ─────────────────────────────────────────────
# MIXKIT - HD Scraper Logic
# ─────────────────────────────────────────────
def search_videos_mixkit(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    search_url = f"https://mixkit.co/free-stock-video/{search_term.replace(' ', '-')}/"
    
    try:
        r = requests.get(search_url, verify=_get_tls_verify(), timeout=30)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        video_items = []
        candidate_urls = set()
        
        # Scrape and look for HD-specific attributes
        for tag in soup.find_all(["video", "source", "a"]):
            for attr in ("data-hd-url", "data-video-url", "href", "src"):
                val = tag.get(attr, "")
                if val and ".mp4" in val:
                    # HEURISTIC: Skip URLs that are clearly low-res thumbnails or previews
                    if any(x in val.lower() for x in ["preview", "thumb", "small", "low"]):
                        continue
                    candidate_urls.add(val)

        for url in candidate_urls:
            # Standardize URL
            if url.startswith("//"): url = "https:" + url
            elif url.startswith("/"): url = "https://mixkit.co" + url
            
            item = MaterialInfo()
            item.provider = "mixkit"
            item.url = url
            item.duration = minimum_duration + 1
            video_items.append(item)
            
        return video_items
    except Exception as e:
        logger.error(f"[mixkit] HD search failed: {str(e)}")
    return []

# ─────────────────────────────────────────────
# SAVE_VIDEO - With Resolution Validation
# ─────────────────────────────────────────────
def save_video(video_url: str, save_dir: str = "") -> str:
    if not save_dir:
        save_dir = utils.temp_dir()
        
    video_id = utils.get_uuid()
    video_path = os.path.join(save_dir, f"{video_id}.mp4")
    
    try:
        # Download the file
        r = requests.get(video_url, stream=True, verify=_get_tls_verify(), timeout=60)
        with open(video_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024*1024):
                if chunk:
                    f.write(chunk)
                    
        if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
            clip = None
            try:
                clip = VideoFileClip(video_path)
                w, h = clip.size
                
                # REJECTION LOGIC: If the video is lower than 720p, we delete it
                # to prevent blurry final exports.
                if w < 720 and h < 720:
                    logger.warning(f"Clip {video_id} is low quality ({w}x{h}). Skipping.")
                    clip.close()
                    if os.path.exists(video_path):
                        os.remove(video_path)
                    return ""
                
                logger.info(f"Verified HD Clip: {w}x{h}")
                return video_path
            except Exception as e:
                logger.error(f"Failed to validate video resolution: {e}")
                return ""
            finally:
                if clip:
                    clip.close() # CRITICAL: Releases file handle and RAM
        
    except Exception as e:
        logger.error(f"Failed to download video: {str(e)}")
        if os.path.exists(video_path):
            os.remove(video_path)
            
    return ""
