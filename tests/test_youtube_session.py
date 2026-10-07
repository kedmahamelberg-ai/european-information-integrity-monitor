import contextlib
import io
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from eiim.youtube_session import youtube_cookies, prepare, cleanup, cookie_file
from eiim.audio_transcripts import transcribe_public_audio

COOKIES = '# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tprivate-cookie-value\n'


class YouTubeSessionTests(unittest.TestCase):
    def test_only_unexpired_youtube_cookies_are_retained(self):
        other = '.example.com\tTRUE\t/\tTRUE\t0\tSID\tunrelated-account\n'
        expired = '.youtube.com\tTRUE\t/\tTRUE\t1\tOLD\texpired\n'
        http_only = '#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t0\tAUTH\tprivate-http-only\n'
        result = youtube_cookies(COOKIES + other + expired + http_only, at=100)
        self.assertNotIn('unrelated-account', result)
        self.assertNotIn('expired', result)
        self.assertIn(http_only, result)

    def test_invalid_and_expired_files_are_rejected_without_values(self):
        for value in ['private-cookie-value', COOKIES.replace('\t0\t', '\t1\t'), COOKIES.replace('\tTRUE\t/', '\tINVALID\t/')]:
            with self.assertRaises(ValueError) as caught:
                youtube_cookies(value, at=100)
            self.assertNotIn('private-cookie-value', str(caught.exception))

    def test_private_permissions_no_secret_output_and_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'cookies.txt'
            with patch.dict(os.environ, {'EIIM_YOUTUBE_COOKIES': COOKIES, 'EIIM_YOUTUBE_COOKIE_FILE': str(target)}):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    prepare()
                self.assertNotIn('private-cookie-value', out.getvalue())
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
                self.assertEqual(cookie_file(), str(target))
                self.assertNotIn('EIIM_YOUTUBE_COOKIES', os.environ)
                cleanup()
                cleanup()
                self.assertIsNone(cookie_file())

    def test_absent_secret_keeps_public_mode(self):
        with patch.dict(os.environ, {'EIIM_YOUTUBE_COOKIES': '', 'EIIM_YOUTUBE_COOKIE_FILE':'/nonexistent/eiim-cookies.txt'}):
            with contextlib.redirect_stdout(io.StringIO()):
                prepare()
            self.assertIsNone(cookie_file())

    def test_existing_file_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'cookies.txt'
            target.write_text('keep')
            with patch.dict(os.environ, {'EIIM_YOUTUBE_COOKIES':COOKIES,'EIIM_YOUTUBE_COOKIE_FILE':str(target)}):
                with self.assertRaises(FileExistsError):
                    prepare()
            self.assertEqual(target.read_text(), 'keep')

    def test_downloader_receives_private_copy_without_disabling_tls(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'session.txt'; source.write_text(COOKIES)
            work = Path(folder) / 'worker'; work.mkdir()
            seen = {}
            class Downloader:
                def __init__(self, options): seen.update(options)
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def extract_info(self, *args, **kwargs): return {'is_live':True}
            modules = {'yt_dlp':SimpleNamespace(YoutubeDL=Downloader), 'faster_whisper':SimpleNamespace(WhisperModel=None)}
            with patch.dict('sys.modules', modules), patch.dict(os.environ, {'EIIM_YOUTUBE_COOKIE_FILE':str(source)}):
                result = transcribe_public_audio('abcDEFG1234', str(work))
            self.assertEqual(result['failure_reason'], 'AudioLiveOrUpcoming')
            self.assertEqual(Path(seen['cookiefile']).read_text(), COOKIES)
            self.assertNotEqual(seen['cookiefile'], str(source))
            self.assertFalse(seen.get('nocheckcertificate', False))
            self.assertNotIn('cookiesfrombrowser', seen)
            self.assertNotIn('private-cookie-value', str(result))


if __name__ == '__main__':
    unittest.main()
