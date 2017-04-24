from kivy.uix.boxlayout import BoxLayout

class SubmitRow(BoxLayout):
    __events__ = ['on_submit', 'on_cancel']
    def on_submit(self, *args, **kwargs):
        pass # pragma: no cover
    def on_cancel(self, *args, **kwargs):
        pass # pragma: no cover
