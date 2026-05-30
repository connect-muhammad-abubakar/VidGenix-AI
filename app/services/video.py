import glob
import itertools
import io
import os
import random
import gc
import shutil
import subprocess
from contextlib import redirect_stdout
from typing import List
from loguru import logger
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    VideoFileClip,
    afx,
)
from moviepy.video.tools.subtitles import SubtitlesClip
from PIL import Image, ImageFont

from app.models import const
from app.models.schema import (
    MaterialInfo,
    VideoAspect,
    VideoConcatMode,
    VideoParams,
    VideoTransitionMode,
)
from app.services.utils import video_effects
from app.utils import utils


class SubClippedVideoClip:
    def __init__(self, file_path, start_time=None, end_time=None, width=None, height=None, duration=None):
        self.file_path = file_path
        self.start_time = start_time
        self.end_time = end_time
        self.width = width
        self.height = height
        if duration is None:
            self.duration = (end_time - start_time) if (start_time is not None and end_time is not None) else 0
        else:
            self.duration = duration

    def __str__(self):
        return f"SubClippedVideoClip(file_path={self.file_path}, duration={self.duration})"


audio_codec = "aac"
audio_bitrate = "192k"
video_codec = "libx264"
fps = 30


def get_ffmpeg_binary():
    configured_ffmpeg = os.environ.get("IMAGEIO_FFMPEG_EXE")
    if configured_ffmpeg:
        return configured_ffmpeg
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    try:
        import imageio_ffmpeg
        bundled_ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled_ffmpeg:
            return bundled_ffmpeg
    except Exception as exc:
        logger.warning(f"failed to resolve bundled ffmpeg binary: {str(exc)}")
    return "ffmpeg"


def _escape_ffmpeg_concat_path(file_path: str) -> str:
    return file_path.replace("'", "'\\''")


def concat_video_clips_with_ffmpeg(
    clip_files: List[str], output_file: str, threads: int, output_dir: str
):
    concat_list_file = os.path.join(output_dir, "ffmpeg-concat-list.txt")
    with open(concat_list_file, "w", encoding="utf-8") as fp:
        for clip_file in clip_files:
            absolute_path = os.path.abspath(clip_file)
            fp.write(f"file '{_escape_ffmpeg_concat_path(absolute_path)}'\n")

    command = [
        get_ffmpeg_binary(),
        "-y", "-f", "concat", "-safe", "0",
        "-i", concat_list_file,
        "-c", "copy",
        "-threads", str(threads or 2),
        output_file,
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            error_message = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(error_message or "ffmpeg concat failed")
    finally:
        delete_files(concat_list_file)


def _sanitize_image_file(image_path: str) -> str:
    image_root, _ = os.path.splitext(image_path)
    sanitized_path = f"{image_root}.sanitized.png"
    with Image.open(image_path) as image:
        image.load()
        cleaned_image = Image.new(image.mode, image.size)
        cleaned_image.putdata(list(image.getdata()))
        cleaned_image.save(sanitized_path)
    return sanitized_path


def _open_image_clip_with_fallback(image_path: str):
    try:
        return ImageClip(image_path), image_path
    except Exception as exc:
        logger.warning(f"failed to open image directly, trying sanitized copy: {image_path}, error: {str(exc)}")
        sanitized_path = _sanitize_image_file(image_path)
        return ImageClip(sanitized_path), sanitized_path


def _open_video_clip_quietly(video_path: str, audio: bool = False) -> VideoFileClip:
    captured_stdout = io.StringIO()
    with redirect_stdout(captured_stdout):
        clip = VideoFileClip(video_path, audio=audio)
    return clip


def close_clip(clip):
    if clip is None:
        return
    try:
        if hasattr(clip, 'close'):
            clip.close()
        if hasattr(clip, 'audio') and clip.audio:
            clip.audio.close()
    except Exception as e:
        logger.error(f"failed to close clip: {str(e)}")
    del clip
    gc.collect()


def delete_files(files: List[str] | str):
    if isinstance(files, str):
        files = [files]
    for file in files:
        try:
            if os.path.exists(file):
                os.remove(file)
        except Exception as e:
            logger.debug(f"failed to delete file {file}: {str(e)}")


def get_bgm_file(bgm_type: str = "random", bgm_file: str = ""):
    if not bgm_type:
        return ""
    if bgm_file and os.path.exists(bgm_file):
        return bgm_file
    if bgm_type == "random":
        suffix = "*.mp3"
        song_dir = utils.song_dir()
        files = glob.glob(os.path.join(song_dir, suffix))
        if not files:
            return ""
        return random.choice(files)
    return ""


def combine_videos(
    combined_video_path: str,
    video_paths: List[str],
    audio_file: str,
    video_aspect: VideoAspect = VideoAspect.portrait,
    video_concat_mode: VideoConcatMode = VideoConcatMode.random,
    video_transition_mode: VideoTransitionMode = None,
    max_clip_duration: int = 5,
    threads: int = 2,
) -> str:
    # Resolve to absolute path to avoid working-directory issues
    audio_file = os.path.abspath(audio_file)
    if not os.path.exists(audio_file):
        logger.error(f"audio file not found: {audio_file}")
        return ""
    audio_clip = AudioFileClip(audio_file)
    audio_duration = audio_clip.duration
    audio_clip.close()

    logger.info(f"audio duration: {audio_duration}s, target aspect: {video_aspect}")

    transition_value = getattr(video_transition_mode, "value", video_transition_mode)
    output_dir = os.path.dirname(combined_video_path)
    aspect = VideoAspect(video_aspect)
    video_width, video_height = aspect.to_resolution()

    subclipped_items = []
    for video_path in video_paths:
        try:
            clip = _open_video_clip_quietly(video_path)
            clip_duration = clip.duration
            clip_w, clip_h = clip.size
            clip.close()

            start_time = 0
            while start_time < clip_duration:
                end_time = min(start_time + max_clip_duration, clip_duration)
                if end_time - start_time > 0.5:
                    subclipped_items.append(
                        SubClippedVideoClip(video_path, start_time, end_time, clip_w, clip_h)
                    )
                start_time = end_time
        except Exception as e:
            logger.error(f"failed to probe {video_path}: {e}")

    if not subclipped_items:
        logger.warning("no subclipped items found, cannot combine videos")
        return ""

    if video_concat_mode.value == VideoConcatMode.random.value:
        random.shuffle(subclipped_items)

    processed_clips = []
    current_video_duration = 0

    item_iterator = itertools.cycle(subclipped_items)
    for i, item in enumerate(item_iterator):
        if current_video_duration >= audio_duration:
            break

        if i > 0 and i % len(subclipped_items) == 0:
            random.shuffle(subclipped_items)

        logger.debug(f"processing clip {i+1}, progress: {current_video_duration:.2f}/{audio_duration:.2f}s")

        try:
            clip = _open_video_clip_quietly(item.file_path).subclipped(item.start_time, item.end_time)

            target_dur = min(clip.duration, max_clip_duration)
            num_frames = int(target_dur * fps)
            exact_duration = num_frames / fps
            clip = clip.subclipped(0, exact_duration)

            if clip.size != (video_width, video_height):
                clip_ratio = clip.w / clip.h
                target_ratio = video_width / video_height
                if abs(clip_ratio - target_ratio) < 0.01:
                    clip = clip.resized(new_size=(video_width, video_height))
                else:
                    scale = min(video_width / clip.w, video_height / clip.h)
                    clip_resized = clip.resized(scale).with_position("center")
                    bg = ColorClip(size=(video_width, video_height), color=(0, 0, 0)).with_duration(clip.duration)
                    clip = CompositeVideoClip([bg, clip_resized])

            shuffle_side = random.choice(["left", "right", "top", "bottom"])
            if transition_value == VideoTransitionMode.fade_in.value:
                clip = video_effects.fadein_transition(clip, 1)
            elif transition_value == VideoTransitionMode.slide_in.value:
                clip = video_effects.slidein_transition(clip, 1, shuffle_side)

            temp_file = os.path.join(output_dir, f"temp-clip-{i}.mp4")
            clip.write_videofile(temp_file, fps=fps, codec=video_codec, audio=False, logger=None)

            processed_clips.append(SubClippedVideoClip(temp_file, duration=exact_duration))
            current_video_duration += exact_duration

            close_clip(clip)
        except Exception as e:
            logger.error(f"process clip error: {e}")

    if not processed_clips:
        return ""

    clip_files = [c.file_path for c in processed_clips]
    concat_video_clips_with_ffmpeg(clip_files, combined_video_path, threads, output_dir)
    delete_files(clip_files)

    return combined_video_path


def wrap_text(text, max_width, font="Arial", fontsize=60):
    font = ImageFont.truetype(font, fontsize)

    def get_text_size(inner_text):
        inner_text = inner_text.strip()
        left, top, right, bottom = font.getbbox(inner_text)
        return right - left, bottom - top

    width, height = get_text_size(text)
    if width <= max_width:
        return text, height

    processed = True
    _wrapped_lines_ = []
    words = text.split(" ")
    _txt_ = ""
    for word in words:
        _before = _txt_
        _txt_ += f"{word} "
        _width, _height = get_text_size(_txt_)
        if _width <= max_width:
            continue
        else:
            if _txt_.strip() == word.strip():
                processed = False
                break
            _wrapped_lines_.append(_before)
            _txt_ = f"{word} "
    _wrapped_lines_.append(_txt_)
    if processed:
        _wrapped_lines_ = [line.strip() for line in _wrapped_lines_]
        result = "\n".join(_wrapped_lines_).strip()
        height = len(_wrapped_lines_) * height
        return result, height

    _wrapped_lines_ = []
    chars = list(text)
    _txt_ = ""
    for word in chars:
        _txt_ += word
        _width, _height = get_text_size(_txt_)
        if _width <= max_width:
            continue
        else:
            _wrapped_lines_.append(_txt_)
            _txt_ = ""
    _wrapped_lines_.append(_txt_)
    result = "\n".join(_wrapped_lines_).strip()
    height = len(_wrapped_lines_) * height
    return result, height


def generate_video(
    video_path: str,
    audio_path: str,
    subtitle_path: str,
    output_file: str,
    params: VideoParams,
):
    aspect = VideoAspect(params.video_aspect)
    video_width, video_height = aspect.to_resolution()

    logger.info(f"generating video: {video_width} x {video_height}")
    logger.info(f"  ① video:    {video_path}")
    logger.info(f"  ② audio:    {audio_path}")
    logger.info(f"  ③ subtitle: {subtitle_path}")
    logger.info(f"  ④ output:   {output_file}")

    output_dir = os.path.dirname(output_file)

    font_path = ""
    if params.subtitle_enabled:
        if not params.font_name:
            params.font_name = "STHeitiMedium.ttc"
        font_path = os.path.join(utils.font_dir(), params.font_name)
        if os.name == "nt":
            font_path = font_path.replace("\\", "/")
        logger.info(f"  ⑤ font: {font_path}")

    def resolve_subtitle_background_color():
        if isinstance(params.text_background_color, bool):
            return "#000000" if params.text_background_color else None
        return params.text_background_color

    def create_text_clip(subtitle_item):
        params.font_size = int(params.font_size)
        params.stroke_width = int(params.stroke_width)
        phrase = subtitle_item[1]
        max_width = video_width * 0.9
        wrapped_txt, txt_height = wrap_text(
            phrase, max_width=max_width, font=font_path, fontsize=params.font_size
        )
        interline = int(params.font_size * 0.25)
        line_count = wrapped_txt.count("\n") + 1
        vertical_padding = int(params.font_size * 0.35)
        size = (
            int(max_width),
            int(txt_height + vertical_padding + (interline * line_count)),
        )
        _clip = TextClip(
            text=wrapped_txt,
            font=font_path,
            font_size=params.font_size,
            color=params.text_fore_color,
            bg_color=resolve_subtitle_background_color(),
            stroke_color=params.stroke_color,
            stroke_width=params.stroke_width,
            interline=interline,
            size=size,
            text_align="center",
        )
        duration = subtitle_item[0][1] - subtitle_item[0][0]
        _clip = _clip.with_start(subtitle_item[0][0])
        _clip = _clip.with_end(subtitle_item[0][1])
        _clip = _clip.with_duration(duration)
        if params.subtitle_position == "bottom":
            _clip = _clip.with_position(("center", video_height * 0.95 - _clip.h))
        elif params.subtitle_position == "top":
            _clip = _clip.with_position(("center", video_height * 0.05))
        elif params.subtitle_position == "custom":
            margin = 10
            max_y = video_height - _clip.h - margin
            min_y = margin
            custom_y = (video_height - _clip.h) * (params.custom_position / 100)
            custom_y = max(min_y, min(custom_y, max_y))
            _clip = _clip.with_position(("center", custom_y))
        else:
            _clip = _clip.with_position(("center", "center"))
        return _clip

    video_path = os.path.abspath(video_path)
    audio_path = os.path.abspath(audio_path)
    video_clip = _open_video_clip_quietly(video_path)
    audio_clip = AudioFileClip(audio_path).with_effects(
        [afx.MultiplyVolume(params.voice_volume)]
    )

    def make_textclip(text):
        return TextClip(
            text=text,
            font=font_path,
            font_size=params.font_size,
        )

    if subtitle_path and os.path.exists(subtitle_path):
        sub = SubtitlesClip(
            subtitles=subtitle_path, encoding="utf-8", make_textclip=make_textclip
        )
        text_clips = []
        for item in sub.subtitles:
            clip = create_text_clip(subtitle_item=item)
            text_clips.append(clip)
        video_clip = CompositeVideoClip([video_clip, *text_clips])

    bgm_file = get_bgm_file(bgm_type=params.bgm_type, bgm_file=params.bgm_file)
    if bgm_file:
        try:
            bgm_clip = AudioFileClip(bgm_file).with_effects(
                [
                    afx.MultiplyVolume(params.bgm_volume),
                    afx.AudioFadeOut(3),
                    afx.AudioLoop(duration=video_clip.duration),
                ]
            )
            audio_clip = CompositeAudioClip([audio_clip, bgm_clip])
        except Exception as e:
            logger.error(f"failed to add bgm: {str(e)}")

    video_clip = video_clip.with_audio(audio_clip)
    output_audio_fps = int(getattr(audio_clip, "fps", 0) or 44100)
    video_clip.write_videofile(
        output_file,
        audio_codec=audio_codec,
        audio_fps=output_audio_fps,
        audio_bitrate=audio_bitrate,
        temp_audiofile_path=output_dir,
        threads=params.n_threads or 2,
        logger=None,
        fps=fps,
    )
    video_clip.close()
    del video_clip


def preprocess_video(materials: List[MaterialInfo], clip_duration=4):
    if not materials:
        return []

    valid_materials = []

    for material in materials:
        if not material.url:
            continue

        ext = utils.parse_extension(material.url)
        material_source_path = material.url
        try:
            if ext in const.FILE_TYPE_IMAGES:
                clip, material_source_path = _open_image_clip_with_fallback(material.url)
            else:
                clip = _open_video_clip_quietly(material.url)
        except Exception:
            try:
                clip, material_source_path = _open_image_clip_with_fallback(material.url)
            except Exception as exc:
                logger.warning(f"skip unreadable local material: {material.url}, error: {str(exc)}")
                continue

        try:
            width = clip.size[0]
            height = clip.size[1]
            if width < 480 or height < 480:
                logger.warning(f"low resolution material: {width}x{height}, minimum 480x480 required")
                close_clip(clip)
                continue

            if ext in const.FILE_TYPE_IMAGES:
                logger.info(f"processing image: {material_source_path}")
                close_clip(clip)
                clip = (
                    ImageClip(material_source_path)
                    .with_duration(clip_duration)
                    .with_position("center")
                )
                zoom_clip = clip.resized(
                    lambda t: 1 + (clip_duration * 0.03) * (t / clip.duration)
                )
                final_clip = CompositeVideoClip([zoom_clip])
                video_file = f"{material_source_path}.mp4"
                final_clip.write_videofile(video_file, fps=30, logger=None)
                close_clip(clip)
                close_clip(final_clip)
                material.url = video_file
                logger.success(f"image processed: {video_file}")
            else:
                close_clip(clip)

        except Exception:
            close_clip(clip)
            raise

        valid_materials.append(material)

    return valid_materials
