import tempfile
import unittest

from os import listdir, path
from threading import Thread
from time import sleep, time

import tutube

TEST_URL = "https://www.youtube.com/watch?v=C0DPdy98e4c"


class CachingDownloaderTests(unittest.TestCase):

    def setUp(self):
        pass

    def test_simple_download(self):
        with tempfile.TemporaryDirectory() as tempdir:
            down = tutube.CachingDownloader(tempdir)
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
            videodir, videofile = path.split(videopath)
            self.assertEqual(listdir(videodir), ["C0DPdy98e4c.mp3"])


class MiscTests(unittest.TestCase):

    def test_lock(self):
        with tempfile.TemporaryDirectory() as td:
            lf = path.join(td, "lockity.lock")
            with tutube.lock(lf):
                self.assertTrue(path.exists(lf))
        self.assertFalse(path.exists(lf))

    @staticmethod
    def lock_for(lockfile, seconds):
        with tutube.lock(lockfile):
            sleep(seconds)

    def test_parallel_lock(self):
        lock_duration = 1
        with tempfile.TemporaryDirectory() as td:
            lf = path.join(td, "lockity.lock")
            # Lock in the background for 2 seconds
            sleepthread = Thread(target=self.lock_for,
                                 args=[lf, lock_duration])
            sleepthread.start()
            locktime = time()
            with tutube.lock(lf):
                unlocktime = time()
                self.assertAlmostEqual(unlocktime - locktime,
                                       lock_duration, places=2)
                # Leave a bit of time for the thread to finish
                sleep(.1)
                # If we could get the lock that means that the sleep thread
                # has finished
                self.assertFalse(sleepthread.is_alive())
