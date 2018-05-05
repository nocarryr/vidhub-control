from kivy.clock import mainthread
from kivy.properties import (
    ObjectProperty,
    NumericProperty,
    StringProperty,
    BooleanProperty,
    OptionProperty,
    ListProperty,
    DictProperty,
)
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

class SmartViewWidget(BoxLayout):
    app = ObjectProperty(None)
    name = StringProperty('')
    connected = BooleanProperty(False)
    monitor_widgets = ListProperty()
    monitor_widget_container = ObjectProperty(None)
    device = ObjectProperty(None, allownone=True)
    edit_name_enabled = BooleanProperty(False)
    edit_name_widget = ObjectProperty(None, allownone=True)
    def on_app(self, *args):
        device = self.app.selected_device
        if device is not None and device.device_type in ['smartview', 'smartscope']:
            self.device = device
        self.app.bind(selected_device=self.on_app_selected_device)
    def on_app_selected_device(self, instance, device, *args):
        if self.device is not None:
            self.clear_monitors()
            self.device.unbind(self)
        if device.device_type not in ['smartview', 'smartscope']:
            device = None
        self.device = device
    def on_device(self, *args):
        if self.device is None:
            self.clear_monitors()
            return
        self.name = self.device.device_name
        self.connected = self.device.connected
        self.app.bind_events(self.device,
            device_name=self.on_device_name,
            connected=self.on_device_connected,
            num_monitors=self.build_monitors,
            monitors=self.build_monitors,
            prelude_parsed=self.build_monitors,
        )
        if self.device.connected:
            self.build_monitors()
    def clear_monitors(self, *args, **kwargs):
        for w in self.monitor_widgets:
            w.unbind_monitor()
        self.monitor_widgets = []
        self.monitor_widget_container.clear_widgets()
    @mainthread
    def build_monitors(self, *args, **kwargs):
        if self.monitor_widget_container is None:
            return
        if not self.device.connected:
            return
        if not self.device.prelude_parsed:
            return
        if len(self.monitor_widgets) == self.device.num_monitors:
            return
        msize = 1 / self.device.num_monitors
        for monitor in self.device.monitors:
            mon_widget = MonitorWidget(monitor=monitor, size_hint_x=msize)
            self.monitor_widgets.append(mon_widget)
            self.monitor_widget_container.add_widget(mon_widget)
    def on_monitor_widget_container(self, *args):
        if len(self.monitor_widgets):
            return
        if self.device and self.device.connected:
            self.build_monitors()
    @mainthread
    def on_device_name(self, instance, value, **kwargs):
        self.name = value
    @mainthread
    def on_device_connected(self, instance, value, **kwargs):
        self.connected = value
        if not value:
            return
        self.clear_monitors()
        self.build_monitors()
    def on_edit_name_enabled(self, instance, value):
        if value:
            r = self.open_edit_name_popup()
            if r is False:
                self.edit_name_enabled = False
        else:
            if self.edit_name_widget is None:
                return
            self.edit_name_widget.dismiss()
            self.edit_name_widget = None
    def open_edit_name_popup(self, *args, **kwargs):
        if self.edit_name_widget is not None:
            return False
        if self.device is None:
            return False
        w = self.edit_name_widget = SmartViewEditNamePopup(device=self.device)
        self.app.popup_widget = w
        w.bind(on_dismiss=self.on_edit_name_popup_dismiss)
        w.open()
    def on_edit_name_popup_dismiss(self, *args):
        self.edit_name_widget = None
        self.edit_name_enabled = False


class SmartViewEditNamePopup(Popup):
    text = StringProperty('')
    device = ObjectProperty(None)
    __events__ = ['on_submit', 'on_cancel']
    def on_device(self, *args):
        self.text = self.device.device_name
    def on_submit(self, *args):
        self.device.device_name = self.text
        self.dismiss()
    def on_cancel(self, *args):
        self.dismiss()

class MonitorWidget(BoxLayout):
    app = ObjectProperty(None)
    list_widget = ObjectProperty(None)
    scope_mode_widget = ObjectProperty(None)
    name = StringProperty('')
    brightness = NumericProperty()
    contrast = NumericProperty()
    saturation = NumericProperty()
    widescreen_sd = StringProperty('Auto')
    border = StringProperty('None')
    identify = BooleanProperty(False)
    audio_channel = NumericProperty()
    scope_mode = StringProperty('')
    monitor = ObjectProperty(None, allownone=True)
    _prop_keys = [
        'name', 'brightness', 'contrast', 'saturation', 'widescreen_sd',
        'border', 'identify', 'audio_channel', 'scope_mode',
    ]
    scope_mode_labels = ListProperty([''])
    def on_list_widget(self, *args):
        if self.list_widget is None:
            return
        self.list_widget.bind(minimum_height=self.list_widget.setter('height'))
    def on_app(self, *args):
        if None in [self.app, self.monitor]:
            return
        self.bind_monitor()
    def on_monitor(self, *args):
        if None in [self.app, self.monitor]:
            return
        self.bind_monitor()
    def _monitor_value_to_self(self, key, value):
        if key == 'widescreen_sd':
            value = self.monitor.get_choice_for_property(key, value).title()
        elif key == 'border':
            value = str(value).title()
        elif key == 'scope_mode':
            value = self.monitor.get_choice_for_property(key, value)
            if value is None:
                value = ''
        return value
    def bind_monitor(self):
        if self.monitor.parent.device_type != 'smartscope':
            self._prop_keys = self._prop_keys[:]
            self._prop_keys.remove('scope_mode')
            if self.scope_mode_widget is not None:
                self.remove_widget(self.scope_mode_widget)
        else:
            for lbl in sorted(self.monitor.get_property_choices('scope_mode').values()):
                self.scope_mode_labels.append(lbl)
        for key in self._prop_keys:
            if key == 'scope_mode' and not hasattr(self.monitor, key):
                continue
            val = getattr(self.monitor, key)
            val = self._monitor_value_to_self(key, val)
            setattr(self, key, val)
        self.app.bind_events(
            self.monitor,
            **{key:self.on_monitor_prop for key in self._prop_keys}
        )
    def unbind_monitor(self):
        if self.monitor is None:
            return
        self.monitor.unbind(self)
        self.monitor = None
    @mainthread
    def on_monitor_prop(self, instance, value, **kwargs):
        prop = kwargs.get('property')
        if prop.name in self._prop_keys:
            value = self._monitor_value_to_self(prop.name, value)
            setattr(self, prop.name, value)
