# -*- coding: utf-8 -*-

# Copyright 2018-2019 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Extract images from https://www.artstation.com/"""

from .common import Extractor, Message
from .. import text, util, exception
import random
import string


class ArtstationExtractor(Extractor):
    """Base class for artstation extractors"""
    category = "artstation"
    filename_fmt = "{category}_{id}_{asset[id]}_{title}.{extension}"
    directory_fmt = ("{category}", "{userinfo[username]}")
    archive_fmt = "{asset[id]}"
    root = "https://www.artstation.com"

    def __init__(self, match):
        Extractor.__init__(self, match)
        self.user = match.group(1) or match.group(2)
        self.external = self.config("external", False)

    def items(self):
        data = self.metadata()
        yield Message.Version, 1
        yield Message.Directory, data

        for project in self.projects():
            for asset in self.get_project_assets(project["hash_id"]):
                asset.update(data)
                adict = asset["asset"]

                if adict["has_embedded_player"] and self.external:
                    player = adict["player_embedded"]
                    url = text.extract(player, 'src="', '"')[0]
                    if not url.startswith(self.root):
                        yield Message.Url, "ytdl:" + url, asset
                        continue

                if adict["has_image"]:
                    url = adict["image_url"]
                    text.nameext_from_url(url, asset)
                    yield Message.Url, self._no_cache(url), asset

    def metadata(self):
        """Return general metadata"""
        return {"userinfo": self.get_user_info(self.user)}

    def projects(self):
        """Return an iterable containing all relevant project IDs"""

    def get_project_assets(self, project_id):
        """Return all assets associated with 'project_id'"""
        url = "{}/projects/{}.json".format(self.root, project_id)
        data = self.request(url).json()

        data["title"] = text.unescape(data["title"])
        data["description"] = text.unescape(text.remove_html(
            data["description"]))

        assets = data["assets"]
        del data["assets"]

        if len(assets) == 1:
            data["asset"] = assets[0]
            yield data
        else:
            for asset in assets:
                data["asset"] = asset
                yield data.copy()

    def get_user_info(self, username):
        """Return metadata for a specific user"""
        url = "{}/users/{}/quick.json".format(self.root, username.lower())
        response = self.request(url, notfound="user")
        return response.json()

    def _pagination(self, url, params=None):
        if not params:
            params = {}
        params["page"] = 1
        total = 0

        while True:
            data = self.request(url, params=params).json()
            yield from data["data"]

            total += len(data["data"])
            if total >= data["total_count"]:
                return

            params["page"] += 1

    @staticmethod
    def _no_cache(url, alphabet=(string.digits + string.ascii_letters)):
        """Cause a cache miss to prevent Cloudflare 'optimizations'

        Cloudflare's 'Polish' optimization strips image metadata and may even
        recompress an image as lossy JPEG. This can be prevented by causing
        a cache miss when requesting an image by adding a random dummy query
        parameter.

        Ref:
        https://github.com/r888888888/danbooru/issues/3528
        https://danbooru.donmai.us/forum_topics/14952
        """
        param = "gallerydl_no_cache=" + util.bencode(
            random.getrandbits(64), alphabet)
        sep = "&" if "?" in url else "?"
        return url + sep + param


class ArtstationUserExtractor(ArtstationExtractor):
    """Extractor for all projects of an artstation user"""
    subcategory = "user"
    pattern = (r"(?:https?://)?(?:(?:www\.)?artstation\.com"
               r"/(?!artwork|projects|search)([^/?&#]+)(?:/albums/all)?"
               r"|((?!www)\w+)\.artstation\.com(?:/projects)?)/?$")
    test = (
        ("https://www.artstation.com/gaerikim/", {
            "pattern": r"https://\w+\.artstation\.com/p/assets"
                       r"/images/images/\d+/\d+/\d+/large/[^/]+",
            "count": ">= 6",
        }),
        ("https://www.artstation.com/gaerikim/albums/all/"),
        ("https://gaerikim.artstation.com/"),
        ("https://gaerikim.artstation.com/projects/"),
    )

    def projects(self):
        url = "{}/users/{}/projects.json".format(self.root, self.user)
        return self._pagination(url)


class ArtstationAlbumExtractor(ArtstationExtractor):
    """Extractor for all projects in an artstation album"""
    subcategory = "album"
    directory_fmt = ("{category}", "{userinfo[username]}", "Albums",
                     "{album[id]} - {album[title]}")
    archive_fmt = "a_{album[id]}_{asset[id]}"
    pattern = (r"(?:https?://)?(?:(?:www\.)?artstation\.com"
               r"/(?!artwork|projects|search)([^/?&#]+)"
               r"|((?!www)\w+)\.artstation\.com)/albums/(\d+)")
    test = (
        ("https://www.artstation.com/huimeiye/albums/770899", {
            "count": 2,
        }),
        ("https://www.artstation.com/huimeiye/albums/770898", {
            "exception": exception.NotFoundError,
        }),
        ("https://huimeiye.artstation.com/albums/770899"),
    )

    def __init__(self, match):
        ArtstationExtractor.__init__(self, match)
        self.album_id = text.parse_int(match.group(3))

    def metadata(self):
        userinfo = self.get_user_info(self.user)
        album = None

        for album in userinfo["albums_with_community_projects"]:
            if album["id"] == self.album_id:
                break
        else:
            raise exception.NotFoundError("album")

        return {
            "userinfo": userinfo,
            "album": album
        }

    def projects(self):
        url = "{}/users/{}/projects.json".format(self.root, self.user)
        params = {"album_id": self.album_id}
        return self._pagination(url, params)


class ArtstationLikesExtractor(ArtstationExtractor):
    """Extractor for liked projects of an artstation user"""
    subcategory = "likes"
    directory_fmt = ("{category}", "{userinfo[username]}", "Likes")
    archive_fmt = "f_{userinfo[id]}_{asset[id]}"
    pattern = (r"(?:https?://)?(?:www\.)?artstation\.com"
               r"/(?!artwork|projects|search)([^/?&#]+)/likes/?")
    test = (
        ("https://www.artstation.com/mikf/likes", {
            "pattern": r"https://\w+\.artstation\.com/p/assets"
                       r"/images/images/\d+/\d+/\d+/large/[^/]+",
            "count": 6,
        }),
        # no likes
        ("https://www.artstation.com/sungchoi/likes", {
            "count": 0,
        }),
    )

    def projects(self):
        url = "{}/users/{}/likes.json".format(self.root, self.user)
        return self._pagination(url)


class ArtstationChallengeExtractor(ArtstationExtractor):
    """Extractor for submissions of artstation challenges"""
    subcategory = "challenge"
    filename_fmt = "{submission_id}_{asset_id}_{filename}.{extension}"
    directory_fmt = ("{category}", "Challenges",
                     "{challenge[id]} - {challenge[title]}")
    archive_fmt = "c_{challenge[id]}_{asset_id}"
    pattern = (r"(?:https?://)?(?:www\.)?artstation\.com"
               r"/contests/[^/?&#]+/challenges/(\d+)"
               r"/?(?:\?sorting=([a-z]+))?")
    test = (
        ("https://www.artstation.com/contests/thu-2017/challenges/20"),
        (("https://www.artstation.com/contests/beyond-human"
          "/challenges/23?sorting=winners"), {
            "range": "1-30",
            "count": 30,
        }),
    )

    def __init__(self, match):
        ArtstationExtractor.__init__(self, match)
        self.challenge_id = match.group(1)
        self.sorting = match.group(2) or "popular"

    def items(self):
        challenge_url = "{}/contests/_/challenges/{}.json".format(
            self.root, self.challenge_id)
        submission_url = "{}/contests/_/challenges/{}/submissions.json".format(
            self.root, self.challenge_id)
        update_url = "{}/contests/submission_updates.json".format(
            self.root)

        challenge = self.request(challenge_url).json()
        yield Message.Version, 1
        yield Message.Directory, {"challenge": challenge}

        params = {"sorting": self.sorting}
        for submission in self._pagination(submission_url, params):

            params = {"submission_id": submission["id"]}
            for update in self._pagination(update_url, params=params):

                del update["replies"]
                update["challenge"] = challenge
                for url in text.extract_iter(
                        update["body_presentation_html"], ' href="', '"'):
                    update["asset_id"] = self._id_from_url(url)
                    text.nameext_from_url(url, update)
                    yield Message.Url, self._no_cache(url), update

    @staticmethod
    def _id_from_url(url):
        """Get an image's submission ID from its URL"""
        parts = url.split("/")
        return text.parse_int("".join(parts[7:10]))


class ArtstationSearchExtractor(ArtstationExtractor):
    """Extractor for artstation search results"""
    subcategory = "search"
    directory_fmt = ("{category}", "Searches", "{search[searchterm]}")
    archive_fmt = "s_{search[searchterm]}_{asset[id]}"
    pattern = (r"(?:https?://)?(?:\w+\.)?artstation\.com"
               r"/search/?\?([^#]+)")
    test = ("https://www.artstation.com/search?sorting=recent&q=ancient",)

    def __init__(self, match):
        ArtstationExtractor.__init__(self, match)
        query = text.parse_query(match.group(1))
        self.searchterm = query.get("q", "")
        self.order = query.get("sorting", "recent").lower()

    def metadata(self):
        return {"search": {
            "searchterm": self.searchterm,
            "order": self.order,
        }}

    def projects(self):
        order = "likes_count" if self.order == "likes" else "published_at"
        url = "{}/search/projects.json".format(self.root)
        params = {
            "direction": "desc",
            "order": order,
            "q": self.searchterm,
            #  "show_pro_first": "true",
        }
        return self._pagination(url, params)


class ArtstationArtworkExtractor(ArtstationExtractor):
    """Extractor for projects on artstation's artwork page"""
    subcategory = "artwork"
    directory_fmt = ("{category}", "Artworks", "{artwork[sorting]!c}")
    archive_fmt = "A_{asset[id]}"
    pattern = (r"(?:https?://)?(?:\w+\.)?artstation\.com"
               r"/artwork/?\?([^#]+)")
    test = ("https://www.artstation.com/artwork?sorting=latest",)

    def __init__(self, match):
        ArtstationExtractor.__init__(self, match)
        self.query = text.parse_query(match.group(1))

    def metadata(self):
        return {"artwork": self.query}

    def projects(self):
        url = "{}/projects.json".format(self.root)
        params = self.query.copy()
        params["page"] = 1
        return self._pagination(url, params)


class ArtstationImageExtractor(ArtstationExtractor):
    """Extractor for images from a single artstation project"""
    subcategory = "image"
    pattern = (r"(?:https?://)?(?:"
               r"(?:\w+\.)?artstation\.com/(?:artwork|projects|search)"
               r"|artstn\.co/p)/(\w+)")
    test = (
        ("https://www.artstation.com/artwork/LQVJr", {
            "pattern": r"https?://\w+\.artstation\.com/p/assets"
                       r"/images/images/008/760/279/large/.+",
            "content": "1f645ce7634e44675ebde8f6b634d36db0617d3c",
            # SHA1 hash without _no_cache()
            # "content": "2e8aaf6400aeff2345274f45e90b6ed3f2a0d946",
        }),
        # multiple images per project
        ("https://www.artstation.com/artwork/Db3dy", {
            "count": 4,
        }),
        # embedded youtube video
        ("https://www.artstation.com/artwork/g4WPK", {
            "range": "2",
            "options": (("external", True),),
            "pattern": "ytdl:https://www.youtube.com/embed/JNFfJtwwrU0",
        }),
        # alternate URL patterns
        ("https://sungchoi.artstation.com/projects/LQVJr"),
        ("https://artstn.co/p/LQVJr"),
    )

    def __init__(self, match):
        ArtstationExtractor.__init__(self, match)
        self.project_id = match.group(1)
        self.assets = None

    def metadata(self):
        self.assets = list(ArtstationExtractor.get_project_assets(
            self, self.project_id))
        self.user = self.assets[0]["user"]["username"]
        return ArtstationExtractor.metadata(self)

    def projects(self):
        return ({"hash_id": self.project_id},)

    def get_project_assets(self, project_id):
        return self.assets
