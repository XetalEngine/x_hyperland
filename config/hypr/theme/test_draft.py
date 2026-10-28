import copy
import unittest
from draft import merge


class ThemeDraftTests(unittest.TestCase):
    def setUp(self):
        self.base=('breakpoint','dark','auto',True,'',{'raw':{'tile_opacity':55,'group_opacity':0}},
                   {'names':True,'hotkeys':True},18,'follow')

    def test_background_survives_unrelated_theme_update(self):
        edited=list(copy.deepcopy(self.base));edited[4]='/pictures/chosen.png';edited[7]=45
        saved=list(copy.deepcopy(self.base));saved[0]='modern';saved[5]['raw']['group_opacity']=80
        merged,conflicts=merge(self.base,edited,saved)
        self.assertEqual(conflicts,[]);self.assertEqual(merged[4],edited[4]);self.assertEqual(merged[7],45)
        self.assertEqual(merged[0],'modern');self.assertEqual(merged[5],saved[5])

    def test_independent_global_switches_merge(self):
        edited=list(copy.deepcopy(self.base));edited[6]['names']=False
        saved=list(copy.deepcopy(self.base));saved[6]['hotkeys']=False
        merged,conflicts=merge(self.base,edited,saved)
        self.assertEqual(conflicts,[]);self.assertEqual(merged[6],{'names':False,'hotkeys':False})

    def test_only_conflicting_field_needs_a_choice(self):
        edited=list(copy.deepcopy(self.base));edited[4]='ours.png';edited[6]['names']=False
        saved=list(copy.deepcopy(self.base));saved[4]='theirs.png';saved[7]=60
        ours,conflicts=merge(self.base,edited,saved)
        theirs,_=merge(self.base,edited,saved,'saved')
        self.assertEqual(conflicts,['Apps background']);self.assertEqual(ours[4],'ours.png');self.assertEqual(theirs[4],'theirs.png')
        for result in (ours,theirs):
            self.assertFalse(result[6]['names']);self.assertEqual(result[7],60)
        self.assertEqual(self.base[4],'');self.assertTrue(self.base[6]['names'])


if __name__=='__main__':unittest.main()
