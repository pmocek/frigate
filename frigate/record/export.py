"""Export recordings to storage."""

import datetime
import logging
import os
import threading

from enum import Enum
import subprocess as sp

from frigate.const import EXPORT_DIR, MAX_PLAYLIST_SECONDS

logger = logging.getLogger(__name__)


class PlaybackFactorEnum(str, Enum):
    realtime = "realtime"
    timelapse_25x = "timelapse_25x"


class RecordingExporter(threading.Thread):
    """Exports a specific set of recordings for a camera to storage as a single file."""

    def __init__(
        self,
        camera: str,
        start_time: int,
        end_time: int,
        playback_factor: PlaybackFactorEnum,
    ) -> None:
        threading.Thread.__init__(self)
        self.camera = camera
        self.start_time = start_time
        self.end_time = end_time
        self.playback_factor = playback_factor

    def get_datetime_from_timestamp(self, timestamp: int) -> str:
        """Convenience fun to get a simple date time from timestamp."""
        return datetime.datetime.fromtimestamp(timestamp).strftime("%Y_%m_%d_%I:%M")

    def run(self) -> None:
        logger.debug(
            f"Beginning export for {self.camera} from {self.start_time} to {self.end_time}"
        )
        file_name = f"{EXPORT_DIR}/in_progress.{self.camera}@{self.get_datetime_from_timestamp(self.start_time)}__{self.get_datetime_from_timestamp(self.end_time)}.mp4"
        final_file_name = f"{EXPORT_DIR}/{self.camera}_{self.get_datetime_from_timestamp(self.start_time)}__{self.get_datetime_from_timestamp(self.end_time)}.mp4"

        if (self.end_time - self.start_time) <= MAX_PLAYLIST_SECONDS:
            playlist_lines = f"http://127.0.0.1:5000/vod/{self.camera}/start/{self.start_time}/end/{self.end_time}/index.m3u8"
            ffmpeg_cmd = [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-protocol_whitelist",
                "pipe,file,http,tcp",
                "-i",
                playlist_lines,
            ]
        else:
            playlist_lines = []
            playlist_start = self.start_time

            while playlist_start < self.end_time:
                playlist_lines.append(
                    f"file http://127.0.0.1:5000/vod/{self.camera}/start/{playlist_start}/end/{min(playlist_start + MAX_PLAYLIST_SECONDS, self.end_time)}/index.m3u8"
                )
                playlist_start += MAX_PLAYLIST_SECONDS

            ffmpeg_cmd = [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-protocol_whitelist",
                "pipe,file,http,tcp",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                "/dev/stdin",
            ]

        if self.playback_factor == PlaybackFactorEnum.realtime:
            ffmpeg_cmd.extend(["-c", "copy", file_name])
        elif self.playback_factor == PlaybackFactorEnum.timelapse_25x:
            ffmpeg_cmd.extend(["-vf", "setpts=0.04*PTS", "-r", "30", "-an", file_name])

        p = sp.run(
            ffmpeg_cmd,
            input="\n".join(playlist_lines),
            encoding="ascii",
            capture_output=True,
        )

        if p.returncode != 0:
            logger.error(p.stderr)
            return

        logger.debug(f"Updating finalized export {file_name}")
        os.rename(file_name, final_file_name)
        logger.debug(f"Finished exporting {file_name}")