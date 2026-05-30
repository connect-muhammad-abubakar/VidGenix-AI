import os
import random
import threading
from typing import List
from urllib.parse import urlencode

import requests
from loguru import logger
from moviepy.video.io.VideoFileClip import VideoFileClip
from bs4 import BeautifulSoup

from app.config import config
from app.models.schema import MaterialInfo, VideoAspect, VideoConcatMode
from app.utils import utils

# Thread-safe counter for API key rotation
_api_key_counter = 0
_api_key_lock = threading.Lock()


def _get_tls_verify() -> bool:
    tls_verify = config.app.get("tls_verify", True)
    if isinstance(tls_verify, str):
        tls_verify = tls_verify.strip().lower() not in ("0", "false", "no", "off")
    if not tls_verify:
        logger.warning(
            "TLS certificate verification is disabled. "
            "Only use this in trusted proxy environments."
        )
    return bool(tls_verify)


def get_api_key(cfg_key: str):
    api_keys = config.app.get(cfg_key)
    if not api_keys:
        raise ValueError(
            f"\n\n##### {cfg_key} is not set #####\n\n"
            f"Please set it in the config.toml file: {config.config_file}\n\n"
        )
    if isinstance(api_keys, str):
        return api_keys
    global _api_key_counter
    with _api_key_lock:
        _api_key_counter += 1
        return api_keys[_api_key_counter % len(api_keys)]


# ─────────────────────────────────────────────
# PEXELS
# ─────────────────────────────────────────────
def search_videos_pexels(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    aspect = VideoAspect(video_aspect)
    video_orientation = aspect.name
    video_width, video_height = aspect.to_resolution()
    api_key = get_api_key("pexels_api_keys")
    headers = {
        "Authorization": api_key,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    params = {
        "query": search_term,
        "per_page": 40,
        "orientation": video_orientation,
    }
    query_url = f"https://api.pexels.com/videos/search?{urlencode(params)}"
    logger.info(f"[pexels] searching: {query_url}")
    try:
        r = requests.get(
            query_url, headers=headers, proxies=config.proxy,
            verify=_get_tls_verify(), timeout=(30, 60),
        )
        response = r.json()
        video_items = []
        if "videos" not in response:
            logger.error(f"[pexels] search failed: {response}")
            return video_items
        for v in response["videos"]:
            duration = v["duration"]
            if duration < minimum_duration:
                continue
            sorted_files = sorted(v["video_files"], key=lambda x: x.get("width", 0), reverse=True)
            for video in sorted_files:
                w = int(video.get("width", 0))
                h = int(video.get("height", 0))
                if w >= 720 or h >= 720:
                    item = MaterialInfo()
                    item.provider = "pexels"
                    item.url = video["link"]
                    item.duration = duration
                    video_items.append(item)
                    break
        return video_items
    except Exception as e:
        logger.error(f"[pexels] search failed: {str(e)}")
    return []


# ─────────────────────────────────────────────
# PIXABAY
# ─────────────────────────────────────────────
def search_videos_pixabay(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    aspect = VideoAspect(video_aspect)
    video_width, video_height = aspect.to_resolution()
    api_key = get_api_key("pixabay_api_keys")
    params = {
        "q": search_term,
        "video_type": "all",
        "per_page": 50,
        "key": api_key,
    }
    query_url = f"https://pixabay.com/api/videos/?{urlencode(params)}"
    logger.info(f"[pixabay] searching: {query_url}")
    try:
        r = requests.get(
            query_url, proxies=config.proxy,
            verify=_get_tls_verify(), timeout=(30, 60),
        )
        response = r.json()
        video_items = []
        if "hits" not in response:
            logger.error(f"[pixabay] search failed: {response}")
            return video_items
        for v in response["hits"]:
            duration = v["duration"]
            if duration < minimum_duration:
                continue
            video_files = v["videos"]
            for video_type in video_files:
                video = video_files[video_type]
                w = int(video.get("width", 0))
                if w >= video_width:
                    item = MaterialInfo()
                    item.provider = "pixabay"
                    item.url = video["url"]
                    item.duration = duration
                    video_items.append(item)
                    break
        return video_items
    except Exception as e:
        logger.error(f"[pixabay] search failed: {str(e)}")
    return []


# ─────────────────────────────────────────────
# COVERR
# Register free at https://coverr.co/developers
# ─────────────────────────────────────────────
def search_videos_coverr(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    aspect = VideoAspect(video_aspect)
    video_width, video_height = aspect.to_resolution()
    is_portrait = video_height > video_width

    try:
        api_key = get_api_key("coverr_api_key")
    except ValueError:
        logger.warning("[coverr] API key not set, skipping coverr search")
        return []

    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    params = {"keywords": search_term, "page_size": 30, "page": 0}
    query_url = f"https://api.coverr.co/videos?{urlencode(params)}"
    logger.info(f"[coverr] searching: {query_url}")

    try:
        r = requests.get(
            query_url, headers=headers, proxies=config.proxy,
            verify=_get_tls_verify(), timeout=(30, 60),
        )
        r.raise_for_status()
        response = r.json()
        video_items = []
        hits = response.get("hits", [])
        if not hits:
            logger.warning(f"[coverr] no results for: {search_term}")
            return video_items
        for v in hits:
            duration = float(v.get("duration", 0))
            if duration < minimum_duration:
                continue
            v_is_portrait = v.get("is_vertical", False)
            if is_portrait != v_is_portrait:
                continue
            urls = v.get("urls", {})
            mp4_url = urls.get("mp4_download") or urls.get("mp4")
            if not mp4_url:
                continue
            mp4_url = mp4_url.replace("?token={token}", "").replace("{token}", "")
            item = MaterialInfo()
            item.provider = "coverr"
            item.url = mp4_url
            item.duration = duration
            video_items.append(item)
        logger.info(f"[coverr] found {len(video_items)} videos for '{search_term}'")
        return video_items
    except requests.HTTPError as e:
        logger.error(f"[coverr] HTTP error: {e.response.status_code}")
    except Exception as e:
        logger.error(f"[coverr] search failed: {str(e)}")
    return []


# ─────────────────────────────────────────────
# MIXKIT  (no official API — scrapes public search)
# ─────────────────────────────────────────────
def search_videos_mixkit(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    slug = search_term.strip().lower().replace(" ", "-")
    search_url = f"https://mixkit.co/free-stock-video/{slug}/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    logger.info(f"[mixkit] searching: {search_url}")

    try:
        r = requests.get(
            search_url, headers=headers, proxies=config.proxy,
            verify=_get_tls_verify(), timeout=(30, 60),
        )
        if r.status_code == 404:
            fallback_url = f"https://mixkit.co/free-stock-video/?q={search_term.replace(' ', '+')}"
            logger.info(f"[mixkit] slug not found, trying fallback: {fallback_url}")
            r = requests.get(
                fallback_url, headers=headers, proxies=config.proxy,
                verify=_get_tls_verify(), timeout=(30, 60),
            )

        soup = BeautifulSoup(r.text, "html.parser")
        candidate_urls = set()

        for tag in soup.find_all("video"):
            for attr in ("src", "data-src", "data-video-url", "data-hd-url"):
                val = tag.get(attr, "")
                if val and ".mp4" in val:
                    if not any(x in val.lower() for x in ["preview", "thumb", "small", "low"]):
                        candidate_urls.add(val)

        for tag in soup.find_all("source", {"type": "video/mp4"}):
            val = tag.get("src", "")
            if val and ".mp4" in val:
                candidate_urls.add(val)

        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            if ".mp4" in href and "mixkit" in href:
                candidate_urls.add(href)

        if not candidate_urls:
            logger.warning(f"[mixkit] no video URLs found for: {search_term}")
            return []

        video_items = []
        for url in candidate_urls:
            if url.startswith("//"):
                url = "https:" + url
            elif url.startswith("/"):
                url = "https://mixkit.co" + url

            item = MaterialInfo()
            item.provider = "mixkit"
            item.url = url
            item.duration = minimum_duration + 1
            video_items.append(item)

        logger.info(f"[mixkit] found {len(video_items)} videos for '{search_term}'")
        return video_items

    except Exception as e:
        logger.error(f"[mixkit] search failed: {str(e)}")
    return []


# ─────────────────────────────────────────────
# SAVE VIDEO
# ─────────────────────────────────────────────
def save_video(video_url: str, save_dir: str = "") -> str:
    if not save_dir:
        save_dir = utils.storage_dir("cache_videos")

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    url_without_query = video_url.split("?")[0]
    url_hash = utils.md5(url_without_query)
    video_id = f"vid-{url_hash}"
    video_path = f"{save_dir}/{video_id}.mp4"

    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        logger.info(f"video already exists: {video_path}")
        return video_path

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }

    try:
        with open(video_path, "wb") as f:
            f.write(
                requests.get(
                    video_url, headers=headers, proxies=config.proxy,
                    verify=_get_tls_verify(), timeout=(60, 240),
                ).content
            )
    except Exception as e:
        logger.error(f"failed to download video: {str(e)}")
        return ""

    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        clip = None
        try:
            clip = VideoFileClip(video_path)
            w, h = clip.size
            duration = clip.duration
            fps = clip.fps
            if w < 720 and h < 720:
                logger.warning(f"low resolution clip: {w}x{h}, skipping")
                clip.close()
                os.remove(video_path)
                return ""
            if duration > 0 and fps > 0:
                logger.info(f"verified clip: {w}x{h}, {duration:.1f}s")
                return video_path
        except Exception as e:
            logger.warning(f"invalid video file: {video_path} => {str(e)}")
            try:
                os.remove(video_path)
            except Exception:
                pass
        finally:
            if clip is not None:
                try:
                    clip.close()
                except Exception:
                    pass
    return ""


# ─────────────────────────────────────────────
# DOWNLOAD VIDEOS — matches task.py call signature
# ─────────────────────────────────────────────
def download_videos(
    task_id: str,
    search_terms: List[str],
    source: str = "pexels",
    video_aspect: VideoAspect = VideoAspect.portrait,
    video_contact_mode: VideoConcatMode = VideoConcatMode.random,
    audio_duration: float = 0.0,
    max_clip_duration: int = 5,
) -> List[str]:

    _source_map = {
        "pexels":  search_videos_pexels,
        "pixabay": search_videos_pixabay,
        "coverr":  search_videos_coverr,
        "mixkit":  search_videos_mixkit,
    }
    search_fn = _source_map.get(source)
    if search_fn is None:
        logger.warning(
            f"unknown video source '{source}', falling back to pexels. "
            f"Available: {list(_source_map.keys())}"
        )
        search_fn = search_videos_pexels

    valid_video_items = []
    valid_video_urls = []
    found_duration = 0.0

    for search_term in search_terms:
        video_items = search_fn(
            search_term=search_term,
            minimum_duration=max_clip_duration,
            video_aspect=video_aspect,
        )
        logger.info(f"[{source}] found {len(video_items)} videos for '{search_term}'")
        for item in video_items:
            if item.url not in valid_video_urls:
                valid_video_items.append(item)
                valid_video_urls.append(item.url)
                found_duration += item.duration

    logger.info(
        f"[{source}] total: {len(valid_video_items)} videos, "
        f"required: {audio_duration}s, found: {found_duration:.1f}s"
    )

    material_directory = config.app.get("material_directory", "").strip()
    if material_directory == "task":
        material_directory = utils.task_dir(task_id)
    elif material_directory and not os.path.isdir(material_directory):
        material_directory = ""

    if video_contact_mode.value == VideoConcatMode.random.value:
        random.shuffle(valid_video_items)

    video_paths = []
    total_duration = 0.0

    for item in valid_video_items:
        try:
            logger.info(f"downloading video: {item.url}")
            saved_video_path = save_video(video_url=item.url, save_dir=material_directory)
            if saved_video_path:
                logger.info(f"video saved: {saved_video_path}")
                video_paths.append(saved_video_path)
                seconds = min(max_clip_duration, item.duration)
                total_duration += seconds
                if total_duration > audio_duration:
                    logger.info(
                        f"total duration: {total_duration:.1f}s >= "
                        f"required: {audio_duration}s — stopping downloads"
                    )
                    break
        except Exception as e:
            logger.error(f"failed to download video: {utils.to_json(item)} => {str(e)}")

    logger.success(f"downloaded {len(video_paths)} videos from [{source}]")
    return video_paths


if __name__ == "__main__":
    download_videos(
        "test123", ["Money Exchange Medium"], audio_duration=100, source="pixabay"
    )
