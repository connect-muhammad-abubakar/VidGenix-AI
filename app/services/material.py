# ─────────────────────────────────────────────
# PEXELS - HD Logic
# ─────────────────────────────────────────────
def search_videos_pexels(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    aspect = VideoAspect(video_aspect)
    video_width, video_height = aspect.to_resolution()
    api_key = get_api_key("pexels_api_keys")
    
    headers = {"Authorization": api_key}
    # We increase per_page to have more HD candidates to choose from
    params = {"query": search_term, "per_page": 40, "orientation": aspect.name}
    query_url = f"https://api.pexels.com/videos/search?{urlencode(params)}"
    
    try:
        r = requests.get(query_url, headers=headers, proxies=config.proxy, verify=_get_tls_verify(), timeout=30)
        response = r.json()
        video_items = []
        for v in response.get("videos", []):
            if v["duration"] < minimum_duration: continue
            
            # Sort files by width descending to find the highest quality (HD/4K)
            sorted_files = sorted(v["video_files"], key=lambda x: x["width"], reverse=True)
            
            for video in sorted_files:
                # Prioritize exact aspect match OR high-res versions
                if video["width"] >= video_width:
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
    # ... (BeautifulSoup setup as before) ...
    
    try:
        # Mixkit usually puts high-res links in data-hd-url or data-video-url
        # We will filter candidate_urls to prioritize HD strings
        video_items = []
        candidate_urls = set()
        
        # Scrape and look for HD-specific attributes
        for tag in soup.find_all(["video", "source", "a"]):
            for attr in ("data-hd-url", "data-video-url", "href", "src"):
                val = tag.get(attr, "")
                if val and ".mp4" in val:
                    # HEURISTIC: Skip URLs that contain 'preview' or 'small'
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
# MODIFIED SAVE_VIDEO (Resolution Validation)
# ─────────────────────────────────────────────
def save_video(video_url: str, save_dir: str = "") -> str:
    # ... (standard path and download logic as before) ...
    
    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        clip = None
        try:
            clip = VideoFileClip(video_path)
            w, h = clip.size
            
            # REJECTION LOGIC: If the video is lower than 720p, we delete it 
            # and return "" so the loop picks a better one.
            if w < 720 and h < 720:
                logger.warning(f"Clip {video_id} is low quality ({w}x{h}). Deleting and skipping.")
                clip.close()
                os.remove(video_path)
                return ""
                
            logger.info(f"HD Clip Verified: {w}x{h}")
            return video_path
        except Exception as e:
            # ... (error handling) ...
            pass
    return ""
