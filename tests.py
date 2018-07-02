import tempfile
from os.path import split
from os import listdir
from tutube import CachingDownloader

import unittest


TEST_URL = "https://www.youtube.com/watch?v=C0DPdy98e4c"


class CachingDownloaderTests(unittest.TestCase):

    def setUp(self):
        pass

    def test_simple_download(self):
        with tempfile.TemporaryDirectory() as tempdir:
            down = CachingDownloader(tempdir)
            videos = down.get_videos(TEST_URL)
            self.assertEqual(len(videos), 1)
            video = videos[0]
            self.assertEqual("C0DPdy98e4c", video.id)
            self.assertEqual("youtube", video.provider)
            self.assertEqual(TEST_URL, video.url)
            self.assertEqual("TEST VIDEO", video.title)
            videopath = down.cache_dir / video.path
            self.assertTrue(videopath.exists())
            self.assertGreater(videopath.stat().st_size, 0)
            videodir, videofile = split(videopath)
            self.assertEqual(listdir(videodir), ["C0DPdy98e4c.mp3"])
