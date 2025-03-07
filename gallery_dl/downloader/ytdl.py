# -*- coding: utf-8 -*-

# Copyright 2018 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Downloader module for URLs requiring youtube-dl support"""

from youtube_dl import YoutubeDL
from .common import DownloaderBase
from .. import text
import os


class YoutubeDLDownloader(DownloaderBase):
    scheme = "ytdl"

    def __init__(self, extractor, output):
        DownloaderBase.__init__(self, extractor, output)

        retries = self.config("retries", extractor._retries)
        options = {
            "format": self.config("format") or None,
            "ratelimit": text.parse_bytes(self.config("rate"), None),
            "retries": retries+1 if retries >= 0 else float("inf"),
            "socket_timeout": self.config("timeout", extractor._timeout),
            "nocheckcertificate": not self.config("verify", extractor._verify),
            "nopart": not self.part,
            "updatetime": self.config("mtime", True),
        }
        options.update(self.config("raw-options") or {})

        if self.config("logging", True):
            options["logger"] = self.log
        self.forward_cookies = self.config("forward-cookies", True)

        self.ytdl = YoutubeDL(options)

    def download(self, url, pathfmt):
        if self.forward_cookies:
            set_cookie = self.ytdl.cookiejar.set_cookie
            for cookie in self.session.cookies:
                set_cookie(cookie)

        try:
            info_dict = self.ytdl.extract_info(url[5:], download=False)
        except Exception:
            return False

        if "entries" in info_dict:
            index = pathfmt.keywords.get("_ytdl_index")
            if index is None:
                return self._download_playlist(pathfmt, info_dict)
            else:
                info_dict = info_dict["entries"][index]
        return self._download_video(pathfmt, info_dict)

    def _download_video(self, pathfmt, info_dict):
        if "url" in info_dict:
            text.nameext_from_url(info_dict["url"], pathfmt.keywords)
        pathfmt.set_extension(info_dict["ext"])
        if pathfmt.exists():
            pathfmt.temppath = ""
            return True
        if self.part and self.partdir:
            pathfmt.temppath = os.path.join(
                self.partdir, pathfmt.filename)
        self.ytdl.params["outtmpl"] = pathfmt.temppath.replace("%", "%%")

        self.out.start(pathfmt.path)
        try:
            self.ytdl.process_info(info_dict)
        except Exception:
            self.log.debug("Traceback", exc_info=True)
            return False
        return True

    def _download_playlist(self, pathfmt, info_dict):
        pathfmt.set_extension("%(playlist_index)s.%(ext)s")
        self.ytdl.params["outtmpl"] = pathfmt.realpath

        for entry in info_dict["entries"]:
            self.ytdl.process_info(entry)
        return True


__downloader__ = YoutubeDLDownloader
