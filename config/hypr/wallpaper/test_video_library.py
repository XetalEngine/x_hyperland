from pathlib import Path
import tempfile,unittest
from wallpaper import library


class VideoLibraryTests(unittest.TestCase):
    def test_media_folders_are_separate_and_last_selection_is_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);pictures=root/'pictures';videos=root/'videos';pictures.mkdir();videos.mkdir()
            (pictures/'picture.png').touch();(pictures/'unlisted.mp4').touch();(videos/'clip.mp4').touch();(videos/'unlisted.png').touch()
            options=library.normalize(dict(library.DEFAULTS,folders=[str(pictures)],video_folders=[str(videos)],bundled=False))
            self.assertEqual([Path(p.path).name for p in library.scan(options)[0]],['picture.png'])
            options['media']='videos'
            self.assertEqual([Path(p.path).name for p in library.scan(options)[0]],['clip.mp4'])
            path=root/'browser.json';saved=library.save(options,library.read(path),path=path)
            self.assertEqual(library.read(path),saved);self.assertEqual(saved['media'],'videos')
