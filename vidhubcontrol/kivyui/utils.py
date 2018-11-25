from kivy.clock import Clock
from kivy.properties import BooleanProperty, NumericProperty, ObjectProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button

class SubmitRow(BoxLayout):
    __events__ = ['on_submit', 'on_cancel']
    def on_submit(self, *args, **kwargs):
        pass # pragma: no cover
    def on_cancel(self, *args, **kwargs):
        pass # pragma: no cover

class HoldRepeatBehavior(object):
    repeat_interval = NumericProperty(.1)
    repeat_delay = NumericProperty(.5)
    repeat_clock_event = ObjectProperty(None, allownone=True)
    delay_clock_event = ObjectProperty(None, allownone=True)
    __events__ = ['on_repeat']
    def on_repeat(self, *args, **kwargs):
        pass
    def _do_press(self):
        self._unschedule()
        self.delay_clock_event = Clock.schedule_once(self._delay_callback, self.repeat_delay)
        self.state = 'down'
    def _do_release(self, *args):
        self._unschedule()
        self.state = 'normal'
    def _delay_callback(self, *args):
        self._unschedule()
        self.repeat_clock_event = Clock.schedule_interval(self._repeat_callback, self.repeat_interval)
    def _repeat_callback(self, *args):
        self.dispatch('on_repeat', *args)
    def _unschedule(self):
        if self.repeat_clock_event is not None:
            Clock.unschedule(self.repeat_clock_event)
            self.repeat_clock_event = None
        if self.delay_clock_event is not None:
            Clock.unschedule(self.delay_clock_event)
            self.delay_clock_event = None

class RepeatButton(HoldRepeatBehavior, Button):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.always_release = True
