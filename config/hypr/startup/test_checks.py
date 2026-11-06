"""Welcome must expose failures without blocking or hiding long diagnostics."""
import threading
import time
import unittest

import checks
import companion
import scene


def healthy_report():
    return dict(ok=True, hyprland={'version':'0.56.2'}, plugins=[
        dict(key=p.key, label=p.label, ok=True, message='Loaded · responding' if p.command else 'Loaded',
             detail='', log='') for p in checks.plugin_health.PLUGINS])


class CheckPanelTests(unittest.TestCase):
    def panel(self, report):
        panel=scene.Scene('clock')
        panel.check.refresh=lambda: report
        return panel

    def text(self, panel, cols=68, rows=17):
        lines=panel.frame(cols,rows)
        self.assertEqual(len(lines),rows)
        return '\n'.join(scene.clip(line,cols) for line in lines)

    def test_stock_panel_shows_all_eight_results_and_count(self):
        report=healthy_report()
        text=self.text(self.panel(report))
        self.assertIn('03 / FUSION CHECK',text)
        self.assertIn('8 passed · 0 need attention',text)
        self.assertEqual(text.count('[✓]'),8)
        for row in report['plugins']:self.assertIn(row['label'],text)

    def test_failures_sort_first_and_count_stays_visible_when_scrolling(self):
        report=healthy_report();report['ok']=False
        report['plugins'][-1].update(ok=False, message='NOT LOADED',
            detail='Compiler error\n'+'missing library\n'*20, log='/tmp/session/window-close.log')
        panel=self.panel(report)
        text=self.text(panel,48,10)
        self.assertIn('7 passed · 1 need attention',text)
        self.assertIn('[✗] Window buttons / forced layout',text)
        self.assertIn('Compiler error',text)
        self.assertIn('↑↓ / wheel',text)
        for event in companion.Input(scroll=True).feed(b'\x1b[6~\x1b[<65;10;10M'):
            panel.input(event)
        scrolled=self.text(panel,48,10)
        self.assertNotEqual(scrolled,text)
        self.assertIn('7 passed · 1 need attention',scrolled)
        # A new failure/recovery brings the changed results back into view.
        report['plugins'][-1]['detail']='Renderer unavailable'
        self.assertIn('Renderer unavailable',self.text(panel,48,10))
        self.assertEqual(panel.check_scroll,0)

    def test_pending_and_checker_failure_never_look_like_success(self):
        for report, expected in [(None,'Checking native plugins'),
                                 ({'ok':False,'error':'Hyprland IPC timed out'},'Hyprland IPC timed out')]:
            text=self.text(self.panel(report))
            self.assertIn(expected,text)
            self.assertNotIn('0 need attention',text)
        text=self.text(self.panel({'ok':False,'error':'bad\x1b[2J\x1b]2;title\x07'}))
        self.assertNotIn('\x1b[2J',text)
        self.assertNotIn('\x1b]2;',text)

    def test_slow_check_is_async_single_flight_and_recovers_after_error(self):
        started=threading.Event();release=threading.Event()
        self.addCleanup(release.set)
        calls=[]
        def inspect():
            calls.append(True);started.set();release.wait(2)
            if len(calls)==1:raise RuntimeError('IPC not ready')
            return healthy_report()
        check=checks.LiveCheck(inspect)
        def completed():
            deadline=time.monotonic()+2
            while time.monotonic()<deadline:
                check.refresh()
                if not check.busy:return check.report
                time.sleep(.005)
            self.fail('Check did not finish')
        self.assertIsNone(check.refresh())
        self.assertTrue(started.wait(1))
        for _ in range(10):self.assertIsNone(check.refresh())
        self.assertEqual(len(calls),1)
        release.set()
        self.assertEqual(completed()['error'],'IPC not ready')
        for _ in range(10):check.refresh()
        self.assertEqual(len(calls),1)
        check.next_check=0
        check.refresh()
        self.assertTrue(completed()['ok'])
        self.assertEqual(len(calls),2)


if __name__=='__main__':unittest.main()
