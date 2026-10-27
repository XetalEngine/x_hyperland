import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import backend
import updater

URL='https://www.youtube.com/watch?v=BaW_jenozKc'


class BackendTests(unittest.TestCase):
    def test_video_links_and_ids_normalize_without_playlist_or_tracking(self):
        for value in ['BaW_jenozKc',URL+'&list=not-a-playlist-to-download',
                      'youtu.be/BaW_jenozKc?t=15','https://music.youtube.com/watch?v=BaW_jenozKc',
                      'https://www.youtube.com/shorts/BaW_jenozKc','https://www.youtube.com/live/BaW_jenozKc']:
            self.assertEqual(backend.youtube_url(value),URL)

    def test_invalid_and_spoofed_urls_are_rejected(self):
        for value in ['file:///etc/passwd','https://youtube.com.example.org/watch?v=BaW_jenozKc',
                      'https://user:secret@youtube.com/watch?v=BaW_jenozKc','https://youtube.com:1234/watch?v=BaW_jenozKc',
                      'https://youtube.com/playlist?list=123',URL+'\n--exec=bad','$(rm -rf something)']:
            with self.assertRaises(ValueError):backend.youtube_url(value)
        self.assertEqual(backend.selected_url('Look: '+URL+' thanks'),URL)
        self.assertEqual(backend.selected_url('unrelated selected text'),'')

    def test_formats_keep_best_streams_and_use_argv(self):
        with patch.object(backend.shutil,'which',side_effect=lambda name:'/usr/bin/'+name):
            audio=backend.command(URL,'mp3',Path('/tmp/music with spaces'),['yt-dlp'])
            video=backend.command(URL,'mp4',Path('/tmp/videos'),['yt-dlp'])
        self.assertIn('bestaudio/best',audio);self.assertEqual(audio[audio.index('--audio-quality')+1],'0')
        self.assertIn('bestvideo+bestaudio/best',video);self.assertNotIn('[ext=',str(video))
        self.assertEqual(video[video.index('--remux-video')+1],'mp4');self.assertNotIn('--recode-video',video)
        self.assertEqual(audio[-2:],['--',URL]);self.assertIn('/tmp/music with spaces',audio)
        self.assertIn('--no-playlist',video);self.assertIn('--ignore-config',video);self.assertIn('--no-overwrites',video)

    def test_selection_prefills_text_but_download_still_requires_valid_link(self):
        self.assertEqual(backend.prefill('  selected text  '),'selected text')
        self.assertEqual(backend.prefill('https://youtu.be/BaW_jenozKc'),URL)
        with self.assertRaises(ValueError):backend.youtube_url(backend.prefill('selected text'))

    def test_xdg_destination_and_disabled_folder_fallback(self):
        def run(argv,**kwargs):return subprocess.CompletedProcess(argv,0,'/tmp/My Music\n','')
        self.assertEqual(backend.destination('mp3',run),Path('/tmp/My Music'))
        def disabled(argv,**kwargs):return subprocess.CompletedProcess(argv,0,str(Path.home())+'\n','')
        self.assertEqual(backend.destination('mp4',disabled),Path.home()/'Videos')

    def test_progress_and_json_paths(self):
        self.assertEqual(backend.output_event('__XETAL_PROGRESS__ 42.5%|1.2MiB/s|00:04')['percent'],42.5)
        self.assertIsNone(backend.output_event('__XETAL_PROGRESS__NA|NA|NA')['percent'])
        name='/tmp/title "with quotes" and\nnewline.mp3'
        self.assertEqual(backend.output_event('__XETAL_FILE__'+json.dumps(name)),{'type':'file','text':name})

    def test_download_requires_successful_final_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);target=root/'finished.mp3';script=root/'fake.py'
            script.write_text('from pathlib import Path\nimport json\np=Path('+repr(str(target))+')\np.write_bytes(b"test")\nprint("__XETAL_FILE__"+json.dumps(str(p)))\n')
            events=[]
            with patch.object(backend.shutil,'which',return_value='/usr/bin/tool'):
                backend.download(URL,'mp3',events.append,root,[sys.executable,str(script)])
            self.assertEqual(events[-1]['file'],str(target));self.assertEqual(events[-1]['type'],'success')
            script.write_text('print("ERROR: example failure")\nraise SystemExit(2)\n')
            with patch.object(backend.shutil,'which',return_value='/usr/bin/tool'):
                with self.assertRaisesRegex(ValueError,'Download failed'):backend.download(URL,'mp3',events.append,root,[sys.executable,str(script)])


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.private=Path(self.temp.name)/'bin/yt-dlp';self.private.parent.mkdir();self.private.write_bytes(b'old')
        self.binary=b'new official archive';self.tag='2099.10.27';self.events=[]
        self.checksum=hashlib.sha256(self.binary).hexdigest()

    def opener(self,request,**kwargs):
        if request.full_url==updater.API:
            data=json.dumps({'tag_name':self.tag,'assets':[{'name':'yt-dlp'},{'name':'SHA2-256SUMS'}]}).encode()
        elif request.full_url.endswith('/SHA2-256SUMS'):data=(self.checksum+'  yt-dlp\n').encode()
        else:data=self.binary
        stream=io.BytesIO(data);stream.headers={'Content-Length':str(len(data))};return stream

    def version(self,argv):return '2026.01.01' if str(self.private) in argv else self.tag

    def test_atomic_verified_update_retains_previous_tool(self):
        updater.update(self.events.append,self.private,self.opener,self.version)
        self.assertEqual(self.private.read_bytes(),self.binary)
        self.assertEqual(self.private.with_suffix('.previous').read_bytes(),b'old')
        self.assertEqual(self.events[-1]['type'],'success')

    def test_checksum_failure_does_not_execute_or_replace(self):
        self.checksum='0'*64;calls=[]
        def version(argv):calls.append(argv);return self.version(argv)
        with self.assertRaisesRegex(ValueError,'checksum'):updater.update(self.events.append,self.private,self.opener,version)
        self.assertEqual(self.private.read_bytes(),b'old');self.assertEqual(len(calls),1)
        self.assertEqual(list(self.private.parent.glob('.yt-dlp-*')),[])

    def test_bad_version_keeps_previous_copy(self):
        with self.assertRaisesRegex(ValueError,'unexpected version'):
            updater.update(self.events.append,self.private,self.opener,lambda argv:'2026.01.01')
        self.assertEqual(self.private.read_bytes(),b'old')

    def test_update_never_downgrades_newer_package(self):
        updater.update(self.events.append,self.private,self.opener,lambda argv:'2100.01.01')
        self.assertEqual(self.private.read_bytes(),b'old');self.assertIn('already up to date',self.events[-1]['text'])


if __name__=='__main__':unittest.main()
