import json
import threading
import asyncio
from functools import partial, wraps, update_wrapper

from kivy.clock import Clock
from kivy.app import App
from kivy.properties import (
    ObjectProperty,
    StringProperty,
    NumericProperty,
    BooleanProperty,
    DictProperty,
)
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.dropdown import DropDown
from kivy.uix.button import Button

from vidhubcontrol import runserver
from vidhubcontrol.kivyui.vidhubview import VidhubWidget
from vidhubcontrol.kivyui.vidhubedit import VidhubEditView

APP_SETTINGS = [
    {
        'type':'title',
        'title':'VidhubControl',
    },{
        'type':'path',
        'title':'Conifg Filename',
        'section':'main',
        'key':'config_filename',
    },{
        'type':'bool',
        'title':'Restore Device Selection',
        'section':'main',
        'key':'restore_device',
        'values':['no', 'yes'],
    },{
        'type':'string',
        'title':'Last Selected Device',
        'section':'main',
        'key':'last_device',
    },{
        'type':'bool',
        'title':'Enable OSC Server',
        'section':'osc',
        'key':'enable',
        'values':['no', 'yes'],
    },{
        'type':'numeric',
        'title':'OSC Server Port',
        'section':'osc',
        'key':'port',
    },
]

APP_SETTINGS_DEFAULTS = {
    'main':{
        'config_filename':runserver.Config.DEFAULT_FILENAME,
        'restore_device':'yes',
        'last_device':'None',
    },
    'osc':{
        'enable':'yes',
        'port':runserver.OscInterface.DEFAULT_HOSTPORT,
    }
}

class HeaderWidget(BoxLayout):
    vidhub_dropdown = ObjectProperty(None)
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.vidhub_dropdown = VidhubDropdown()

class VidhubDropdown(DropDown):
    app = ObjectProperty(None)
    btns = DictProperty()
    def on_app(self, *args):
        if self.app is None:
            return
        self.update_buttons()
        self.app.bind(
            vidhubs=self.update_buttons,
            selected_vidhub=self.on_selected_vidhub,
        )
    def update_buttons(self, *args, **kwargs):
        for key in sorted(self.app.vidhubs.keys()):
            if key in self.btns:
                continue
            vidhub = self.app.vidhubs[key]
            btn = VidhubDropdownButton(vidhub=vidhub)
            self.btns[key] = btn
            self.add_widget(btn)
    def on_selected_vidhub(self, instance, value):
        self.select(value.device_name)

class VidhubDropdownButton(Button):
    app = ObjectProperty(None)
    vidhub = ObjectProperty(None)
    def on_vidhub(self, instance, value):
        if self.vidhub is None:
            return
        self.text = self.vidhub.device_name
        if self.app is None:
            return
        self.app.bind_events(self.vidhub, device_name=self.on_vidhub_device_name)
    def on_app(self, *args):
        if self.app is None:
            return
        if self.vidhub is not None:
            return
        self.app.bind_events(self.vidhub, device_name=self.on_vidhub_device_name)
    def on_vidhub_device_name(self, instance, value, **kwargs):
        self.text = value


class RootWidget(FloatLayout):
    header_widget = ObjectProperty(None)
    main_widget = ObjectProperty(None)
    vidhub_widget = ObjectProperty(None)
    vidhub_edit_widget = ObjectProperty(None)
    footer_widget = ObjectProperty(None)

class VidhubControlApp(App):
    async_server = ObjectProperty(None)
    vidhub_config = ObjectProperty(None)
    vidhubs = DictProperty()
    selected_vidhub = ObjectProperty(None)
    def build_config(self, config):
        for section_name, section in APP_SETTINGS_DEFAULTS.items():
            config.setdefaults(section_name, section)
    def build_settings(self, settings):
        settings.add_json_panel('VidhubControl', self.config, data=json.dumps(APP_SETTINGS))
    def get_application_config(self):
        return super().get_application_config('~/vidhubcontrol-ui.ini')
    def on_selected_vidhub(self, instance, value):
        if value is None:
            return
        stored = self.config.get('main', 'last_device')
        if stored == value.device_id:
            return
        self.config.set('main', 'last_device', value.device_id)
        self.config.write()
    def on_start(self, *args, **kwargs):
        self.aio_loop = asyncio.get_event_loop()
        Clock.schedule_interval(self._tick_aio_loop, .1)
        self.async_server = AsyncServer(self)
        self.async_server.start()
        self.async_server.thread_run_event.wait()
        self.vidhub_config = self.async_server.config
        self.update_vidhubs()
        self.bind_events(self.vidhub_config, vidhubs=self.update_vidhubs)
    def on_stop(self, *args, **kwargs):
        self.async_server.running = False
    def update_vidhubs(self, *args, **kwargs):
        restore_device = self.config.get('main', 'restore_device') == 'yes'
        last_device = self.config.get('main', 'last_device')
        for key, val in self.vidhub_config.vidhubs.items():
            if key in self.vidhubs:
                continue
            self.vidhubs[key] = val.backend
            if restore_device and key == last_device:
                self.selected_vidhub = val.backend
    async def _async_no_op(self):
        await asyncio.sleep(0)
    def _tick_aio_loop(self, *args):
        self.aio_loop.run_until_complete(self._async_no_op())
    def bind_events(self, obj, **kwargs):
        self.async_server.bind_events(obj, **kwargs)
    def run_async_coro(self, coro):
        return self.async_server.run_async_coro(coro)


WRAPPER_ASSIGNMENTS = ('__module__', '__name__', '__qualname__', '__doc__',
    '__annotations__', '__self__', '__func__')
def wrapped_callback(f):
    # Used by AioBridge.bind_events() to wrap a main thread callback
    # to be called by kivy.clock.Clock. Attributes are reassigned to make the
    # wrapped callback 'look' like the original (f.__func__ and f.__self__)
    # So the weakref storage in pydispatch still functions properly (in theory)
    class wrapped_(object):
        def __init__(self, f):
            pass
        def __call__(self, *args, **kwargs):
            Clock.schedule_once(partial(f, *args, **kwargs))
        def __get__(self, obj, objtype):
            return types.MethodType(self.__call__, obj, objtype)
    return update_wrapper(wrapped_(f), f, assigned=WRAPPER_ASSIGNMENTS)

class AioBridge(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = False
        self.thread_run_event = threading.Event()
        self.thread_stop_event = threading.Event()
    def run(self):
        loop = self.event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.running = True
        loop.run_until_complete(self.aioloop())
        self.thread_stop_event.set()
    def stop(self):
        self.running = False
        self.thread_stop_event.wait()
    async def aioloop(self):
        await self.aiostartup()
        self.thread_run_event.set()
        while self.running:
            await self.sleep()
        await self.aioshutdown()
    async def aiostartup(self):
        pass
    async def aioshutdown(self):
        pass
    async def sleep(self):
        await asyncio.sleep(.1)
    def bind_events(self, obj, **kwargs):
        # Override pydispatch.Dispatcher.bind() using wrapped_callback
        # Events should then be dispatched from the thread's event loop to
        # the main thread using kivy.clock.Clock
        async def do_bind(obj_, **kwargs_):
            obj_.bind(**kwargs_)
        kwargs_ = {}
        for name, callback in kwargs.items():
            kwargs_[name] = wrapped_callback(callback)
        asyncio.run_coroutine_threadsafe(do_bind(obj, **kwargs_), loop=self.event_loop)
    def run_async_coro(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, loop=self.event_loop)


class Opts(object):
    def __init__(self, d):
        for key, val in d.items():
            setattr(self, key, val)

class AsyncServer(AioBridge):
    def __init__(self, app):
        super().__init__()
        self.app = app
        osc_disabled = self.app.config.get('osc', 'enable') != 'yes'
        self.opts = Opts({
            'config_filename':self.app.config.get('main', 'config_filename'),
            'osc_address':None,
            'osc_port':self.app.config.get('osc', 'port'),
            'osc_iface_name':None,
            'osc_disabled':osc_disabled,
        })
    async def aiostartup(self):
        self.config, self.interfaces = await runserver.start(self.opts)
    async def aioshutdown(self):
        await runserver.stop(self.config, self.interfaces)


def main():
    VidhubControlApp().run()

if __name__ == '__main__':
    main()
