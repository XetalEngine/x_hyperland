import copy
from pathlib import Path
import sys
import unittest
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from window_rules import model
from effects.window_close import rules as buttons

class WindowRuleTests(unittest.TestCase):
    def rule(self,**fields):return dict(model.DEFAULT,id=uuid.uuid4().hex,app='org.kde.*',**fields)
    def test_match_and_config_preserve_literal_names(self):
        rule=self.rule(title='Project ? — Kate',layout='floating',workspace=3,width=900,height=600,position='center')
        self.assertTrue(model.matches(rule,'org.kde.kate','Project A — Kate'))
        self.assertFalse(model.matches(rule,'org.kde.kate','Project AB — Kate'))
        config=model.render({'version':1,'rules':[rule]})
        self.assertIn('workspace = 3 silent',config);self.assertIn('tag = +fusion-managed-rule',config)
        self.assertEqual(model.expression('org.kde.*'),r'^(org\.kde\..*)$')
    def test_button_only_does_not_change_window_layout(self):
        rule=self.rule(controls=dict(buttons.DEFAULTS,mode='always',size=10))
        value=model.validate({'version':1,'rules':[rule]})
        self.assertNotIn('windowrule {',model.render(value))
        self.assertEqual(value['rules'][0]['controls']['size'],10)
    def test_injection_and_incomplete_geometry_are_rejected(self):
        for fields in ({'app':'kate\nexec=bad'},{'title':'abc#comment'},{'monitor':'DP-1;exec bad'},{'width':900},{'app':'a[bc]'},{'opacity':101}):
            rule=dict(self.rule(),**fields)
            with self.subTest(fields=fields),self.assertRaises(ValueError):model.validate({'version':1,'rules':[rule]})
    def test_disabled_rule_and_order(self):
        first=self.rule(layout='floating');second=self.rule(layout='tile');disabled=self.rule(enabled=False,layout='floating')
        text=model.render({'version':1,'rules':[first,second,disabled]})
        self.assertLess(text.index(first['id']),text.index(second['id']));self.assertNotIn(disabled['id'],text)

if __name__=='__main__':unittest.main()
