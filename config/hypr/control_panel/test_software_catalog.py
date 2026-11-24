"""Catalog integrity, cache lifecycle and network boundaries; no host mutations."""
import contextlib
import gzip
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import software_catalog as catalog


def desc(name,version='1',description='Sample app'):
    return f'%NAME%\n{name}\n\n%VERSION%\n{version}\n\n%DESC%\n{description}\n\n%URL%\nhttps://example.org/\n\n%LICENSE%\nMIT\n\n'.encode()


class CatalogTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.base=Path(temp.name)
        self.db=self.base/'db';(self.db/'sync').mkdir(parents=True);(self.db/'local').mkdir()
        self.apps=self.base/'applications';self.apps.mkdir();self.xml=self.base/'swcatalog';(self.xml/'xml').mkdir(parents=True)
        self.seed=self.base/'seed.json';self.seed.write_text(json.dumps({'schema':1,'categories':[],'apps':[]}))
        self.repo('extra',{'alpha':desc('alpha'),'library':desc('library')})
        self.paths=(self.db,['extra'],[self.apps],self.xml)
        self.patch(patch.object(catalog,'SEED',self.seed));self.patch(patch.object(catalog,'system_paths',return_value=self.paths))
        self.patch(patch.dict(os.environ,{'XDG_CACHE_HOME':str(self.base/'cache')}))

    def patch(self,value):
        result=value.start();self.addCleanup(value.stop);return result

    def repo(self,name,records):
        with tarfile.open(self.db/'sync'/(name+'.db'),'w:gz') as out:
            for key,data in records.items():
                entry=tarfile.TarInfo(key+'/desc');entry.size=len(data);out.addfile(entry,io.BytesIO(data))

    def install(self,name,version='1'):
        folder=self.db/'local'/(name+'-'+version);folder.mkdir();(folder/'desc').write_bytes(desc(name,version))

    def seed_apps(self,apps):
        self.seed.write_text(json.dumps({'schema':1,'categories':[],'apps':apps}))

    def build(self):return catalog.build_catalog(*self.paths)

    def local(self,force=False):
        with contextlib.redirect_stdout(io.StringIO()):return catalog.local_catalog(force)

    def test_repository_priority_and_unconfigured_db_are_respected(self):
        self.repo('preferred',{'alpha':desc('alpha','2')});self.repo('unused',{'hidden':desc('hidden')})
        records,warnings=catalog.package_records(self.db,['preferred','extra'])
        self.assertEqual(records['alpha']['version'],'2');self.assertEqual(records['alpha']['repository'],'preferred')
        self.assertNotIn('hidden',records);self.assertFalse(warnings)

    def test_appstream_descriptions_categories_icons_and_locale(self):
        icon=self.xml/'icons/archlinux-arch-extra/64x64/app.png';icon.parent.mkdir(parents=True);icon.write_bytes(b'fixture')
        xml='''<components origin="archlinux-arch-extra"><component type="desktop-application"><id>org.example.Alpha</id><pkgname>alpha</pkgname><name xml:lang="de">Andere</name><name>Alpha App</name><summary>A friendly app</summary><description><p>First paragraph.</p><p>Second paragraph.</p></description><categories><category>Utility</category><category>Development</category></categories><icon type="stock">alpha-icon</icon><icon type="cached" width="64">app.png</icon><launchable type="desktop-id">alpha.desktop</launchable></component><component type="desktop-application"><pkgname>absent</pkgname><name>Missing package</name></component></components>'''
        with gzip.open(self.xml/'xml/extra.xml.gz','wt') as f:f.write(xml)
        (self.apps/'alpha.desktop').write_text('[Desktop Entry]\nType=Application\nName=Alpha\nExec=alpha\n')
        self.install('alpha','3');value=self.build();a=next(v for v in value['apps'] if v['package']=='alpha')
        self.assertEqual(a['name'],'Alpha App');self.assertEqual(a['categories'],['Utility','Development']);self.assertEqual(a['icon'],'alpha-icon')
        self.assertEqual(a['cached_icon'],str(icon));self.assertTrue(a['installed']);self.assertEqual(a['installed_version'],'3')
        self.assertEqual(a['desktop_file'],str(self.apps/'alpha.desktop'));self.assertEqual(value['appstream_count'],1)
        self.assertEqual(a['description'],'First paragraph.\n\nSecond paragraph.')
        self.assertEqual(next(v for v in value['apps'] if v['package']=='library')['kind'],'package')

    def test_seed_does_not_claim_absent_pacman_packages_exist_and_aliases_open(self):
        self.seed_apps([dict(package='missing',source='pacman',name='Missing',icon='missing',categories=['Utility']),
            dict(package='google-chrome',source='aur',name='Chrome',icon='chrome',categories=['WebBrowser'],installed_aliases=['google-chrome-stable'],desktop_id='google-chrome.desktop'),
            dict(package='echo',source='vendor',name='Echo',icon='echo',categories=['Network'],desktop_id='echo.desktop')])
        self.install('google-chrome-stable','157')
        for name in ('echo','google-chrome'):(self.apps/(name+'.desktop')).write_text('[Desktop Entry]\nType=Application\nExec='+name+'\n')
        values={a['package']:a for a in self.build()['apps']}
        self.assertFalse(values['missing']['available']);self.assertTrue(values['google-chrome']['installed']);self.assertEqual(values['google-chrome']['installed_version'],'157')
        self.assertTrue(values['echo']['installed']);self.assertEqual(values['echo']['source'],'vendor')

    def test_user_hidden_launcher_masks_system_file(self):
        system=self.base/'system';system.mkdir();(system/'alpha.desktop').write_text('[Desktop Entry]\nType=Application\nExec=alpha\n')
        (self.apps/'alpha.desktop').write_text('[Desktop Entry]\nHidden=true\n')
        entries=catalog.desktop_entries([self.apps,system]);self.assertEqual(entries['alpha.desktop'],{})
        a={'package':'alpha'};catalog.attach_desktop(a,entries);self.assertNotIn('desktop_file',a)

    def test_missing_databases_are_distinguished_from_absent_packages(self):
        self.assertFalse(self.build()['needs_sync'])
        (self.db/'sync/extra.db').unlink()
        value=self.build();self.assertTrue(value['needs_sync']);self.assertTrue(value['warnings'])

    def test_validated_deb_apps_include_alternative_route_and_installed_alias(self):
        self.repo('extra',{'discord':desc('discord'),'code':desc('code')})
        self.install('discord')
        app=next(a for a in self.build()['apps'] if a['package']=='discord')
        self.assertEqual(app['deb_id'],'discord');self.assertIn('working',app['deb_note'])
        self.assertEqual(app['installed_package'],'discord')
        self.assertNotIn('deb_id',next(a for a in self.build()['apps'] if a['package']=='code'))

    def test_warm_cache_skips_reparse_but_database_and_install_changes_invalidate(self):
        first=self.local()
        with patch.object(catalog,'build_catalog',side_effect=AssertionError('Reparsed unchanged cache')):self.assertEqual(self.local()['apps'],first['apps'])
        self.install('alpha','4');second=self.local();self.assertNotEqual(first['fingerprint'],second['fingerprint'])
        self.assertEqual(next(a for a in second['apps'] if a['package']=='alpha')['installed_version'],'4')
        self.repo('extra',{'new':desc('new')});third=self.local();self.assertEqual([a['package'] for a in third['apps']],['new'])

    def test_failed_refresh_retains_previous_usable_catalog_and_does_not_cache_failure(self):
        value=self.local();(self.db/'sync/extra.db').write_bytes(b'not an archive')
        self.assertEqual(self.local()['apps'],value['apps'])
        self.repo('extra',{'new':desc('new')});self.assertEqual([a['package'] for a in self.local()['apps']],['new'])

    def test_invalid_icon_paths_and_urls_are_not_followed(self):
        self.assertEqual(catalog.safe_url('file:///etc/passwd'),'');self.assertEqual(catalog.safe_url('javascript:alert(1)'),'')
        self.assertEqual(catalog.safe_url('https://user:pass@example.com'),'');self.assertEqual(catalog.safe_url('https://['),'');self.assertEqual(catalog.safe_url(7),'')
        self.assertEqual(catalog.safe_url('https://example.com/a'),'https://example.com/a')
        self.repo('extra',{'evil':desc('../evil')});self.assertEqual(self.build()['apps'],[])

    def test_opening_local_catalog_has_no_network_or_privileged_commands(self):
        with patch.object(catalog.urllib.request,'urlopen',side_effect=AssertionError('Network used')),patch.object(catalog.subprocess,'run',side_effect=AssertionError('Command run')):
            self.local();self.local()

    def test_cache_corruption_is_rebuilt(self):
        self.local();file=next(catalog.cache_root().glob('catalog-*.json'));file.write_text('{broken')
        value=self.local();self.assertEqual(value['type'],'catalog');self.assertEqual(len(value['apps']),2)

    def test_aur_is_bounded_encoded_and_cached(self):
        response={'version':5,'type':'search','results':[{'Name':'hello-app','Description':'Hello','Version':'2','URL':'https://example.com','License':['MIT']},{'Name':'../unsafe'}]}
        urls=[]
        def opener(request,timeout):urls.append(request.full_url);self.assertEqual(timeout,12);return io.BytesIO(json.dumps(response).encode())
        value=catalog.aur_search('hello app',opener=opener)
        self.assertEqual([a['package'] for a in value['apps']],['hello-app']);self.assertIn('hello%20app',urls[0])
        again=catalog.aur_search('hello app',opener=lambda *a,**kw:self.fail('Warm search fetched again'))
        self.assertTrue(again['cached']);self.assertEqual(again['apps'],value['apps'])
        failed=catalog.aur_search('hello app',True,opener=lambda *a,**kw:(_ for _ in ()).throw(OSError('offline')))
        self.assertIn('saved results',failed['warning']);self.assertEqual(failed['apps'],value['apps'])

    def test_aur_errors_and_oversized_results_remain_explicit(self):
        for text in ('x','\nhello','x'*101):
            with self.assertRaises(ValueError):catalog.aur_search(text,opener=lambda *a,**kw:self.fail('Invalid query fetched'))
        with self.assertRaisesRegex(RuntimeError,'AUR'):
            catalog.aur_search('hello',opener=lambda *a,**kw:io.BytesIO(b'x'*(4*1024*1024+1)))
        with self.assertRaisesRegex(RuntimeError,'unexpected'):
            catalog.aur_search('hello',opener=lambda *a,**kw:io.BytesIO(b'{"results":[]}'))

    def test_vendor_release_uses_current_host_linux_artifacts_without_execution(self):
        artifact=lambda name:dict(file=name,sha256='a'*64,size=123456)
        fixtures={
            'echo':dict(platforms=dict(linux=dict(version='1.2.3',**artifact('Echo_Future-1.2.3-linux-x86_64.tar.gz'),installer=dict(mode='bundled',version='1.2.3',**artifact('Echo_Future-1.2.3-linux-x86_64-setup.run'))))),
            'linuxstudio':dict(release=dict(filename='ls2026-x86_64_alpha-0.0.0.999.AppImage',buildVersion='0.0.0.999',arch='x86_64',sha256='b'*64,sizeBytes=999)),
            'xmusic':dict(release=dict(app='xmusic',version='0.1.2',architecture='x86_64',platforms=dict(linux=dict(installer=artifact('XMusic-0.1.2-linux-x86_64-install.run'),appimage=artifact('XMusic-0.1.2-linux-x86_64.AppImage'))))),
            'xvideo':dict(release=dict(app='xvideo',version='0.2.3',architecture='x86_64',platforms=dict(linux=dict(archive=artifact('XVideo-0.2.3-linux-x86_64.tar.gz'))))),
        }
        for product,data in fixtures.items():
            with self.subTest(product=product),patch.object(catalog.subprocess,'run',side_effect=AssertionError('Executed a download')):
                urls=[]
                def opener(request,timeout):urls.append(request.full_url);self.assertEqual(timeout,12);return io.BytesIO(json.dumps(data).encode())
                value=catalog.vendor_release(product,opener=opener)
                self.assertEqual(urls,[catalog.VENDOR_MANIFESTS[product]]);self.assertEqual(value['type'],'vendor');self.assertEqual(value['product'],product)
                for choice in value['choices']:
                    self.assertTrue(choice['url'].startswith('https://www.xetal.net/'));self.assertEqual(len(choice['sha256']),64)
                    self.assertNotIn('windows',choice['filename']);self.assertNotIn('freebsd',choice['filename']);self.assertTrue(choice['instructions'])
        self.assertEqual(catalog.vendor_release('linuxstudio',opener=lambda *a,**kw:io.BytesIO(json.dumps(fixtures['linuxstudio']).encode()))['choices'][0]['url'],catalog.VENDOR_SITE+'api/d.php?t=a')

    def test_vendor_does_not_substitute_other_platforms_or_unpublished_installers(self):
        a=dict(file='XMusic-0.1.2-windows-x86_64-setup.exe',sha256='a'*64,size=12)
        release=dict(app='xmusic',version='0.1.2',architecture='x86_64',platforms=dict(windows=dict(installer=a)))
        with self.assertRaisesRegex(RuntimeError,'No Linux download'):
            catalog.vendor_release('xmusic',opener=lambda *a,**kw:io.BytesIO(json.dumps({'release':release}).encode()))
        echo=dict(platforms=dict(linux=dict(version='1.2.3',installer=dict(mode='bundled',version='1.2.2',file='Echo_Future-1.2.2-linux-x86_64-setup.run',size=123,sha256='a'*64))))
        with self.assertRaisesRegex(RuntimeError,'No Linux download'):
            catalog.vendor_release('echo',opener=lambda *a,**kw:io.BytesIO(json.dumps(echo).encode()))

    def test_vendor_rejects_bad_identity_path_architecture_and_checksum(self):
        a=dict(file='XVideo-0.2.3-linux-x86_64.AppImage',sha256='a'*64,size=42)
        def call(release):return catalog.vendor_release('xvideo',opener=lambda *a,**kw:io.BytesIO(json.dumps({'release':release}).encode()))
        base=dict(app='xvideo',version='0.2.3',architecture='x86_64',platforms=dict(linux=dict(appimage=a)))
        for key,value in [('app','xmusic'),('architecture','arm64'),('version','../bad')]:
            with self.subTest(key=key),self.assertRaises(RuntimeError):call(dict(base,**{key:value}))
        for key,value in [('file','../../bad.AppImage'),('sha256','invalid'),('size',True),('file','XVideo-0.2.2-linux-x86_64.AppImage')]:
            bad=dict(base,platforms=dict(linux=dict(appimage=dict(a,**{key:value}))))
            with self.subTest(key=key),self.assertRaises(RuntimeError):call(bad)
        with self.assertRaises(ValueError):catalog.vendor_release('unknown',opener=lambda *a,**kw:self.fail('Unknown product fetched'))

    def test_vendor_errors_remain_visible_and_response_size_is_bounded(self):
        for raw in (b'null',b'{"release":[]}',b'{"platforms":[]}',b'x'*(1024*1024+1)):
            with self.subTest(raw=raw[:30]),self.assertRaises((ValueError,RuntimeError)):
                catalog.vendor_release('echo',opener=lambda *a,**kw:io.BytesIO(raw))

if __name__=='__main__':unittest.main()
