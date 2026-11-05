"""Exercise actual Pango ink extents through repeated GTK theme reloads."""
import unittest
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk, Gdk
import bar_styles
import designs
import runtime


class MetricSpacingTests(unittest.TestCase):
    def test_icons_and_values_do_not_overlap_after_theme_reloads(self):
        initialized=Gtk.init_check()
        if not (initialized[0] if isinstance(initialized,tuple) else initialized):
            self.skipTest('Run under xvfb-run or a graphical display to check GTK text layout.')
        window=Gtk.OffscreenWindow();window.set_name('waybar')
        box=Gtk.Box(spacing=2);window.add(box)
        labels=[]
        for name in ('cpu','memory'):
            widget=Gtk.Label();widget.set_name(name);box.pack_start(widget,False,False,0);labels.append(widget)
        provider=Gtk.CssProvider();screen=Gdk.Screen.get_default()
        Gtk.StyleContext.add_provider_for_screen(screen,provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        source=(runtime.ROOT/'waybar-dark.css').read_text()
        window.show_all()
        try:
            # Reuse the same labels as Waybar does on a CSS-only refresh; values
            # change width while theme faces change between mono and proportional.
            for mode in runtime.MODES:
                for design in (*designs.DESIGNS,*reversed(designs.DESIGNS)):
                    colors=runtime.colors(mode,design)
                    css=runtime.stylesheet(source,mode,design,qt=False)
                    if design!='raw':css+=designs.waybar_style(colors,design)
                    css+=bar_styles.stylesheet(colors,design)
                    provider.load_from_data(css.encode())
                    for values in (('\uf4bc 1%','\uefc5 8G'),('\uf4bc 100%','\uefc5 1024G')):
                        for label,value in zip(labels,values):label.set_text(value)
                        while Gtk.events_pending():Gtk.main_iteration()
                        for label in labels:
                            layout=label.get_layout();iterator=layout.get_iter();ink=[]
                            while True:
                                index=iterator.get_index()
                                char=label.get_text().encode()[index:].decode()[0:1]
                                bounds,_=iterator.get_cluster_extents()
                                if char and not char.isspace():ink.append(bounds)
                                if not iterator.next_cluster():break
                            with self.subTest(mode=mode,design=design,text=label.get_text()):
                                self.assertGreaterEqual(len(ink),2)
                                self.assertLessEqual(ink[0].x+ink[0].width,ink[1].x,
                                                     'Icon ink overlaps the first digit')
        finally:
            window.destroy();Gtk.StyleContext.remove_provider_for_screen(screen,provider)


if __name__=='__main__':unittest.main()
