import os
import json
import threading
import asyncio

from kivy.resources import resource_add_path
from kivy.logger import Logger
from kivy.clock import Clock, mainthread
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
from kivy.uix.tabbedpanel import TabbedPanel

from vidhubcontrol import runserver
from vidhubcontrol.kivyui.vidhubview import VidhubWidget
from vidhubcontrol.kivyui.vidhubedit import VidhubEditView
from vidhubcontrol.kivyui.smartview import SmartViewWidget
from vidhubcontrol.kivyui.newdevice import NewDevicePopup

APP_PATH = os.path.dirname(os.path.abspath(__file__))
resource_add_path(APP_PATH)

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
    smartview_dropdown = ObjectProperty(None)
    smartscope_dropdown = ObjectProperty(None)
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.vidhub_dropdown = VidhubDropdown()
        self.smartview_dropdown = SmartViewDropdown()
        self.smartscope_dropdown = SmartScopeDropdown()

class DeviceDropdown(DropDown):
    app = ObjectProperty(None)
    btns = DictProperty()
    devices = DictProperty()
    def on_app(self, *args):
        self.app.bind(selected_device=self.on_app_selected_device)
    def on_devices(self, instance, devices):
        for key in sorted(devices.keys()):
            if key in self.btns:
                continue
            device = devices[key]
            btn = DeviceDropdownButton(device=device)
            btn.bind(on_release=self.on_device_btn_release)
            self.btns[key] = btn
            self.add_widget(btn)
        to_remove = set(self.btns.keys()) - set(devices.keys())
        for key in to_remove:
            self.remove_widget(self.btns[key])
            del self.btns[key]
    def update_devices(self, app, devices):
        self.devices.update(devices)
    def on_app_selected_device(self, instance, value):
        if value.device_id not in self.devices:
            self.select(None)
        else:
            self.select(value.device_id)
    def on_device_btn_release(self, instance):
        self.app.selected_device = instance.device
    def open_new_device_popup(self, *args, **kwargs):
        popup = NewDevicePopup(port=self._default_port, device_type=self._device_type)
        self.app.popup_widget = popup
        popup.open()

class VidhubDropdown(DeviceDropdown):
    _device_type = 'vidhub'
    _default_port = '9990'
    def on_app(self, *args):
        super().on_app(*args)
        self.update_devices(self.app, self.app.vidhubs)
        self.app.bind(vidhubs=self.update_devices)

class SmartViewDropdown(DeviceDropdown):
    _device_type = 'smartview'
    _default_port = '9992'
    def on_app(self, *args):
        super().on_app(*args)
        self.update_devices(self.app, self.app.smartviews)
        self.app.bind(smartviews=self.update_devices)

class SmartScopeDropdown(DeviceDropdown):
    _device_type = 'smartscope'
    _default_port = '9992'
    def on_app(self, *args):
        super().on_app(*args)
        self.update_devices(self.app, self.app.smartscopes)
        self.app.bind(smartscopes=self.update_devices)

class DeviceDropdownButton(Button):
    app = ObjectProperty(None)
    device = ObjectProperty(None)
    def on_device(self, instance, value):
        if self.device is None:
            return
        self.text = str(self.device.device_name)
        if self.app is None:
            return
        self.device.bind(device_name=self.on_device_name)
    def on_app(self, instance, value):
        if self.app is None:
            return
        self.device.bind(device_name=self.on_device_name)
    @mainthread
    def on_device_name(self, instance, value, **kwargs):
        self.text = str(value)

class VidhubPanel(TabbedPanel):
    vidhub_widget = ObjectProperty(None)
    vidhub_edit_widget = ObjectProperty(None)
    name = StringProperty()
    connected = BooleanProperty()

class RootWidget(FloatLayout):
    app = ObjectProperty(None)
    header_widget = ObjectProperty(None)
    main_widget = ObjectProperty(None)
    footer_widget = ObjectProperty(None)
    active_widget = ObjectProperty(None, allownone=True)
    connected = BooleanProperty(False)
    name = StringProperty('')
    def on_app(self, *args):
        self.app.bind(selected_device=self.on_app_selected_device)
    def on_app_selected_device(self, instance, device):
        if device is None:
            return
        if device.device_type in ['smartview', 'smartscope']:
            cls = SmartViewWidget
        else:
            cls = VidhubPanel
        if isinstance(self.active_widget, cls):
            return
        if self.active_widget is not None:
            self.main_widget.remove_widget(self.active_widget)
            self.active_widget.unbind(
                name=self.update_active_widget_props,
                connected=self.update_active_widget_props,
            )
        w = cls()
        self.main_widget.add_widget(w)
        self.active_widget = w
    def on_active_widget(self, *args):
        self.update_active_widget_props()
        self.active_widget.bind(
            name=self.update_active_widget_props,
            connected=self.update_active_widget_props,
        )
    @mainthread
    def update_active_widget_props(self, *args, **kwargs):
        self.name = self.active_widget.name
        self.connected = self.active_widget.connected

class VidhubControlApp(App):
    vidhub_config = ObjectProperty(None)
    interfaces = ObjectProperty(None)
    vidhubs = DictProperty()
    smartviews = DictProperty()
    smartscopes = DictProperty()
    selected_device = ObjectProperty(None)
    popup_widget = ObjectProperty(None, allownone=True)
    aio_loop = ObjectProperty(None)
    def __init__(self, **kwargs):
        kwargs['kv_directory'] = APP_PATH
        super(VidhubControlApp, self).__init__(**kwargs)
    def build_config(self, config):
        for section_name, section in APP_SETTINGS_DEFAULTS.items():
            config.setdefaults(section_name, section)
    def build_settings(self, settings):
        settings.add_json_panel('VidhubControl', self.config, data=json.dumps(APP_SETTINGS))
    def get_application_config(self):
        return super().get_application_config('~/vidhubcontrol-ui.ini')
    def on_selected_device(self, instance, value):
        if value is None:
            self.selected_device_name = ''
            self.selected_device_connected = False
            return
        stored = self.config.get('main', 'last_device')
        if stored == value.device_id:
            return
        self.config.set('main', 'last_device', value.device_id)
        self.config.write()
    def on_start(self, *args, **kwargs):
        if self.aio_loop is None:
            self.aio_loop = asyncio.get_event_loop()
        self.run_async_coro(self.async_start())

    async def async_run(self, async_lib=None):
        await super().async_run(async_lib)
        await self.async_stop()
        Logger.info('Config shut down successfully')

    async def async_start(self):
        osc_disabled = self.config.get('osc', 'enable') != 'yes'
        opts = Opts({
            'config_filename':self.config.get('main', 'config_filename'),
            'osc_address':None,
            'osc_port':self.config.getint('osc', 'port'),
            'osc_iface_name':None,
            'osc_disabled':osc_disabled,
        })
        config, interfaces = await runserver.start(self.aio_loop, opts)
        self.vidhub_config = config
        self.interfaces = interfaces
        self.update_vidhubs()
        self.update_smartviews()
        self.update_smartscopes()
        self.vidhub_config.bind(
            vidhubs=self.update_vidhubs,
            smartviews=self.update_smartviews,
            smartscopes=self.update_smartscopes,
        )

    async def async_stop(self):
        await runserver.stop(self.vidhub_config, self.interfaces)

    def on_popup_widget(self, *args):
        if self.popup_widget is None:
            return
        self.popup_widget.bind(on_dismiss=self.on_popup_widget_dismiss)
    def on_popup_widget_dismiss(self, *args):
        self.popup_widget = None
    @mainthread
    def update_vidhubs(self, *args, **kwargs):
        restore_device = self.config.get('main', 'restore_device') == 'yes'
        last_device = self.config.get('main', 'last_device')
        for key, val in self.vidhub_config.vidhubs.items():
            if key in self.vidhubs:
                continue
            self.vidhubs[key] = val.backend
            if restore_device and key == last_device:
                self.selected_device = val.backend
    @mainthread
    def update_smartviews(self, *args, **kwargs):
        restore_device = self.config.get('main', 'restore_device') == 'yes'
        last_device = self.config.get('main', 'last_device')
        for key, val in self.vidhub_config.smartviews.items():
            if key in self.smartviews:
                continue
            self.smartviews[key] = val.backend
            if restore_device and key == last_device:
                self.selected_device = val.backend
    @mainthread
    def update_smartscopes(self, *args, **kwargs):
        restore_device = self.config.get('main', 'restore_device') == 'yes'
        last_device = self.config.get('main', 'last_device')
        for key, val in self.vidhub_config.smartscopes.items():
            if key in self.smartscopes:
                continue
            self.smartscopes[key] = val.backend
            if restore_device and key == last_device:
                self.selected_device = val.backend

    def run_async_coro(self, coro):
        return asyncio.ensure_future(coro)



class Opts(object):
    def __init__(self, d):
        for key, val in d.items():
            setattr(self, key, val)



def main():
    loop = asyncio.get_event_loop()
    app = VidhubControlApp()
    loop.run_until_complete(app.async_run())

if __name__ == '__main__':
    main()
