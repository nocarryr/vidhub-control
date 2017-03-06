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

class SmartViewWidget(BoxLayout):
    app = ObjectProperty(None)
    name = StringProperty('')
    connected = BooleanProperty(False)
    monitor_widgets = ListProperty()
    monitor_widget_container = ObjectProperty(None)
    device = ObjectProperty(None, allownone=True)
    def on_app(self, *args):
        device = self.app.selected_device
        if device is not None and device.device_type in ['smartview', 'smartscope']:
            self.device = device
        self.app.bind(selected_device=self.on_app_selected_device)
    def on_app_selected_device(self, instance, device):
        if self.device is not None:
            self.monitor_widget_container.clear_widgets()
            self.monitor_widgets = []
            self.device.unbind(self)
        if device.device_type not in ['smartview', 'smartscope']:
            device = None
        self.device = device
    def on_device(self, *args):
        if self.device is None:
            return
        self.name = self.device.device_name
        self.app.bind_events(self.device,
            device_name=self.on_device_name,
            connected=self.on_device_connected,
        )
        if self.device.connected:
            self.build_monitors()
        else:
            self.app.bind_events(self.device, connected=self.on_device_connected)
    def build_monitors(self, *args, **kwargs):
        if self.monitor_widget_container is None:
            return
        msize = 1 / self.device.num_monitors
        for monitor in self.device.monitors:
            mon_widget = MonitorWidget(monitor=monitor, size_hint_x=msize)
            mon_widget
            self.monitor_widgets.append(mon_widget)
            self.monitor_widget_container.add_widget(mon_widget)
    def on_monitor_widget_container(self, *args):
        if len(self.monitor_widgets):
            return
        if self.device and self.device.connected:
            self.build_monitors()
    def on_device_name(self, instance, value, **kwargs):
        self.name = value
    def on_device_connected(self, instance, value, **kwargs):
        print('on_device_connected: ', instance, value, kwargs)
        self.connected = value
        if value and not len(self.monitor_widgets):
            instance.unbind(self)
            self.build_monitors()


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
    monitor = ObjectProperty(None)
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
    def bind_monitor(self):
        if self.monitor.parent.device_type != 'smartscope':
            self._prop_keys = []
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
            if key == 'widescreen_sd':
                val = self.monitor.get_choice_for_property(key, val).title()
            elif key == 'border':
                val = str(val).title()
            elif key == 'scope_mode':
                val = self.monitor.get_choice_for_property(key, val)
                if val is None:
                    val = ''
            setattr(self, key, val)
        self.app.bind_events(
            self.monitor,
            **{key:self.on_monitor_prop for key in self._prop_keys}
        )
    def on_monitor_prop(self, instance, value, **kwargs):
        prop = kwargs.get('property')
        if prop.name in self._prop_keys:
            if prop.name == 'widescreen_sd':
                value = self.monitor.get_choice_for_property(prop.name, value).title()
            elif prop.name == 'border':
                value = str(value).title()
            elif prop.name == 'scope_mode':
                value = self.monitor.get_choice_for_property(prop.name, value)
            setattr(self, prop.name, value)
