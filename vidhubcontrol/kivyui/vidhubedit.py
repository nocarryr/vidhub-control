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
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button

from vidhubcontrol.kivyui.vidhubpresetedit import VidhubPresetEditPopup

class VidhubEditView(BoxLayout):
    app = ObjectProperty(None)
    device_name_text_widget = ObjectProperty(None)
    input_label_list = ObjectProperty(None)
    output_label_list = ObjectProperty(None)
    preset_label_list = ObjectProperty(None)
    vidhub = ObjectProperty(None, allownone=True)
    vidhub_bound = BooleanProperty(False)
    text = StringProperty('')
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.vidhub is not None and not self.vidhub_bound:
            self.bind_vidhub()
    def on_app(self, *args):
        device = self.app.selected_device
        if device is not None and device.device_type == 'vidhub':
            self.vidhub = device
        self.app.bind(selected_device=self.on_app_selected_device)
    def on_app_selected_device(self, instance, value):
        if self.vidhub is not None:
            self.unbind_vidhub(self.vidhub)
        if value.device_type != 'vidhub':
            value = None
        self.vidhub = value
        if value is not None:
            self.bind_vidhub()
    def on_vidhub(self, *args):
        if self.vidhub is None:
            self.text = ''
            return
        self.text = self.vidhub.device_name
        if not self.vidhub_bound:
            self.bind_vidhub()
    @mainthread
    def on_vidhub_device_name(self, instance, value, **kwargs):
        self.text = value
    def on_text(self, instance, value):
        if self.vidhub is None:
            return
        self.vidhub.device_name = value
    def bind_vidhub(self):
        self.app.bind_events(self.vidhub, device_name=self.on_vidhub_device_name)
        self.vidhub_bound = True
    def unbind_vidhub(self, vidhub):
        vidhub.unbind(self.on_vidhub_device_name)
        self.vidhub_bound = False


class VidhubEditLabelList(BoxLayout):
    app = ObjectProperty(None)
    text = StringProperty()
    label_list_widget = ObjectProperty(None)
    list_items = DictProperty()
    vidhub = ObjectProperty(None, allownone=True)
    vidhub_bound = BooleanProperty(False)
    vidhub_prop_get = StringProperty('')
    vidhub_prop_set = StringProperty('')
    kv_bind_props = [
        'app', 'label_list_widget', 'vidhub_prop_set', 'vidhub_prop_get',
    ]
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        bind_kwargs = {key:self._on_kv_prop_set for key in self.kv_bind_props}
        if not self._check_kv_props():
            self.bind(**bind_kwargs)
        else:
            if self.vidhub is not None:
                if not self.vidhub_bound:
                    self.bind_vidhub()
                self.build_items()
    def _on_kv_prop_set(self, *args, **kwargs):
        if not self._check_kv_props():
            return
        bind_kwargs = {key:self._on_kv_prop_set for key in self.kv_bind_props}
        self.unbind(**bind_kwargs)
        if self.vidhub is not None:
            if not self.vidhub_bound:
                self.bind_vidhub()
            self.build_items()
    def _check_kv_props(self):
        if None in [self.app, self.label_list_widget]:
            return False
        if '' in [self.vidhub_prop_get, self.vidhub_prop_set]:
            return False
        return True
    def on_label_list_widget(self, *args):
        if self.label_list_widget is None:
            return
        self.label_list_widget.bind(minimum_height=self.label_list_widget.setter('height'))
    def on_app(self, *args):
        if self.app is None:
            return
        device = self.app.selected_device
        if device is not None and device.device_type == 'vidhub':
            self.vidhub = device
        self.app.bind(selected_device=self.on_app_selected_device)
    def on_app_selected_device(self, instance, value):
        if self.vidhub is not None:
            self.unbind_vidhub(self.vidhub)
        if value.device_type != 'vidhub':
            value = None
        self.vidhub = value
        if value is not None:
            self.bind_vidhub()
    def bind_vidhub(self):
        self.app.bind_events(self.vidhub, **{self.vidhub_prop_get:self.on_vidhub_labels})
        self.vidhub_bound = True
    def unbind_vidhub(self, vidhub):
        vidhub.unbind(self.on_vidhub_labels)
        self.vidhub_bound = False
    def on_vidhub(self, *args):
        if self.vidhub is None:
            return
        if self._check_kv_props():
            if not self.vidhub_bound:
                self.bind_vidhub()
            self.build_items()
    def build_items(self):
        self.label_list_widget.clear_widgets()
        self.list_items.clear()
        if self.vidhub is None:
            return
        l = getattr(self.vidhub, self.vidhub_prop_get)
        for i, lbl in enumerate(l):
            item = VidhubEditLabelItem(index=i, text=lbl)
            item.bind(text=self.on_label_item_text)
            self.list_items[i] = item
            self.label_list_widget.add_widget(item)
    @mainthread
    def on_vidhub_labels(self, instance, value, **kwargs):
        for i, lbl in enumerate(value):
            item = self.list_items[i]
            item.text = lbl
    def on_label_item_text(self, instance, value):
        l = getattr(self.vidhub, self.vidhub_prop_set)
        l[instance.index] = value

class VidhubPresetEditList(VidhubEditLabelList):
    def _check_kv_props(self):
        if None in [self.app, self.label_list_widget]:
            return False
        return True
    def bind_vidhub(self):
        self.app.bind_events(self.vidhub, on_preset_added=self.on_vidhub_preset_added)
        self.vidhub_bound = True
    def unbind_vidhub(self, vidhub):
        vidhub.unbind(self.on_vidhub_preset_added)
        self.vidhub_bound = False
    def build_items(self):
        self.label_list_widget.clear_widgets()
        self.list_items.clear()
        if self.vidhub is None:
            return
        for preset in self.vidhub.presets:
            item = VidhubEditPresetItem(preset=preset)
            self.list_items[item.index] = item
            self.label_list_widget.add_widget(item)
    @mainthread
    def on_vidhub_preset_added(self, *args, **kwargs):
        self.build_items()
    def add_preset(self):
        self.app.run_async_coro(self.vidhub.add_preset())

class VidhubEditLabelItem(BoxLayout):
    index = NumericProperty()
    text = StringProperty()

class VidhubEditPresetItem(VidhubEditLabelItem):
    app = ObjectProperty(None)
    preset = ObjectProperty(None)
    edit_popup_widget = ObjectProperty(None, allownone=True)
    def on_text(self, *args):
        if self.preset is None:
            return
        if self.text is None:
            return
        self.preset.name = self.text
    def on_preset(self, *args):
        if self.preset is None:
            return
        self.index = self.preset.index
        self.text = self.preset.name
        if self.app is not None:
            self.bind_preset()
    def on_app(self, *args):
        if self.app is None:
            return
        if self.preset is not None:
            self.bind_preset()
    def bind_preset(self):
        self.app.bind_events(self.preset, name=self.on_preset_name)
    @mainthread
    def on_preset_name(self, instance, value, **kwargs):
        self.text = value
    def open_edit_popup(self, *args, **kwargs):
        w = self.edit_popup_widget = VidhubPresetEditPopup(preset=self.preset)
        w.bind(on_dismiss=self.on_edit_popup_dismiss)
        self.app.popup_widget = w
        w.open()
    def on_edit_popup_dismiss(self, *args):
        self.edit_popup_widget = None
