#!/usr/bin/python3

import fcntl
import http.server
import logging
import wsgiref.simple_server

from argparse import ArgumentParser
from collections import namedtuple
from contextlib import contextmanager
from http import HTTPStatus
from os import unlink
from pathlib import Path
from socketserver import ThreadingMixIn
from wsgiref.headers import Headers
from wsgiref.util import FileWrapper

import youtube_dl

logging.basicConfig(level=logging.DEBUG)
formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
handler = logging.StreamHandler()
handler.setFormatter(formatter)
dl_logger = logging.getLogger("youtube-dl")
dl_logger.addHandler(handler)
dl_logger.setLevel(logging.WARNING)


@contextmanager
def lock(path):
    with open(path, "w") as fp:
        try:
            fcntl.flock(fp, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fp, fcntl.LOCK_UN)
            try:
                unlink(path)
            except FileNotFoundError:
                pass


class ThreadingSimpleServer(ThreadingMixIn, http.server.HTTPServer):
    pass


class CannotDownload(Exception):
    pass


class CachingDownloader(object):

    class VideoInfo(namedtuple("VideoInfo",
                               ("url", "provider", "id", "title"))):
        @property
        def path(self):
            return Path(self.provider) / ("%s.mp3" % self.id)

    def __init__(self, cache_dir):

        self.cache_dir = Path(cache_dir)

        ydl_opts = {
                'outtmpl': str(self.cache_dir) + '/%(extractor)s/%(id)s',
                'noplaylist': True,
                'youtube_include_dash_manifest': False,
                'quiet': True,
                # ~ 'writethumbnail': True,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'logger': dl_logger,
                # ~ 'progress_hooks': [self.progress_hook],
            }

        self.ydl = youtube_dl.YoutubeDL(ydl_opts)

    def extract_info(self, url):
        try:
            with self.ydl:
                result = self.ydl.extract_info(url, download=False)
        except youtube_dl.utils.DownloadError as exc:
            raise CannotDownload(str(exc))
        if 'entries' in result:
            infos = result['entries']
        else:
            # Just a video
            infos = [result]
        return [self.VideoInfo(i["webpage_url"], i["extractor"],
                               i["id"], i["title"])
                for i in infos]

    def _download(self, info):
        mp3_path = self.cache_dir / info.path
        mp3_path.parent.mkdir(exist_ok=True)
        if not mp3_path.exists():
            logging.info("%r: Video not in cache, downloading", info.title)
            with lock(mp3_path.with_suffix(".lock")), self.ydl:
                self.ydl.download([info.url])
        return info

    def get_videos(self, url):
        return [self._download(i) for i in self.extract_info(url)]


class YoutubeDownloader(object):

    def __init__(self, cache_dir):
        self.downloader = CachingDownloader(cache_dir)

    class HTTPError(Exception):
        def __init__(self, status, reason=None, more=None):
            assert status >= 300
            self.status = HTTPStatus(status)
            self.reason = reason or self.status.phrase
            self.more = (more or self.status.description).encode("utf-8")

        def __str__(self):
            return "{} {}".format(self.status, self.reason)

    def __call__(self, environ, start_response):
        try:
            meth = getattr(self, "do_%s" % environ["REQUEST_METHOD"], None)
            if meth is None:
                raise self.HTTPError(405)
            return meth(environ, start_response)
        except self.HTTPError as hte:
            start_response(str(hte), [("Content-Type", "text/plain")])
            return [hte.more]

    def do_GET(self, environ, start_response):
        headers = Headers()
        video_url = "{PATH_INFO}?{QUERY_STRING}".format(**environ).strip("/")
        if video_url == "?":
            raise self.HTTPError(400, more="no URL provided")
        try:
            videos = self.downloader.get_videos(video_url)
        except CannotDownload as cad:
            raise self.HTTPError(400, "Cannot download", more=str(cad))

        if len(videos) != 1:
            raise self.HTTPError(400, more="playlists not supported yet")
        video = videos[0]
        audio_file = self.downloader.cache_dir / video.path
        assert audio_file.exists()
        filesize = audio_file.stat().st_size
        headers.add_header("Content-Disposition", "attachment",
                           filename=video.title)
        headers.add_header("Content-Type", "audio/mpeg")
        headers.add_header("Content-Length", str(filesize))
        start_response("200 OK", headers.items())
        return FileWrapper(audio_file.open("rb"))


class ThreadingWSGIServer(ThreadingMixIn, wsgiref.simple_server.WSGIServer):
    pass


class Binding(namedtuple("Binding", "host port")):

    def __new__(cls, value):
        host, port = value.split(":")
        return super().__new__(cls, host, int(port))


def main():
    psr = ArgumentParser()
    psr.add_argument("cache_dir", type=Path, metavar="DIR",
                     help="Video cache directory")
    psr.add_argument("--bind", type=Binding, default="127.0.0.1:1994",
                     help="host:port to bind to (default %(default)s)")
    args = psr.parse_args()
    downloader = YoutubeDownloader(args.cache_dir)
    server = wsgiref.simple_server.make_server(*args.bind,
                                               downloader,
                                               ThreadingWSGIServer)
    server.serve_forever()


if __name__ == "__main__":
    main()
