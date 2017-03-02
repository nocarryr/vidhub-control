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

class VidhubEditView(BoxLayout):
    app = ObjectProperty(None)
    input_label_list = ObjectProperty(None)
    output_label_list = ObjectProperty(None)
    preset_label_list = ObjectProperty(None)

class VidhubEditLabelList(BoxLayout):
    app = ObjectProperty(None)
    text = StringProperty()
    label_list_widget = ObjectProperty(None)
    list_items = DictProperty()
    vidhub = ObjectProperty(None, allownone=True)
    vidhub_prop_get = StringProperty()
    vidhub_prop_set = StringProperty()
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
            self.bind_vidhub()
        self.app.bind(selected_device=self.on_app_selected_device)
    def on_app_selected_device(self, instance, value):
        if self.vidhub is not None:
            self.unbind_vidhub(self.vidhub)
        if value.device_type != 'vidhub':
            value = None
        self.vidhub = value
        self.build_items()
        if value is not None:
            self.bind_vidhub()
    def bind_vidhub(self):
        self.app.bind_events(self.vidhub, **{self.vidhub_prop_get:self.on_vidhub_labels})
    def unbind_vidhub(self, vidhub):
        vidhub.unbind(self.on_vidhub_labels)
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
    def on_vidhub_labels(self, instance, value, **kwargs):
        for i, lbl in enumerate(value):
            item = self.list_items[i]
            item.text = lbl
    def on_label_item_text(self, instance, value):
        l = getattr(self.vidhub, self.vidhub_prop_set)
        l[instance.index] = value

class VidhubPresetEditList(VidhubEditLabelList):
    def bind_vidhub(self):
        self.app.bind_events(self.vidhub, on_preset_added=self.on_vidhub_preset_added)
    def unbind_vidhub(self, vidhub):
        vidhub.unbind(self.on_vidhub_preset_added)
    def build_items(self):
        self.label_list_widget.clear_widgets()
        self.list_items.clear()
        if self.vidhub is None:
            return
        for preset in self.vidhub.presets:
            item = VidhubEditPresetItem(preset=preset)
            self.list_items[item.index] = item
            self.label_list_widget.add_widget(item)
    def on_vidhub_preset_added(self, *args, **kwargs):
        self.build_items()

class VidhubEditLabelItem(BoxLayout):
    index = NumericProperty()
    text = StringProperty()

class VidhubEditPresetItem(VidhubEditLabelItem):
    app = ObjectProperty(None)
    preset = ObjectProperty(None)
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
    def on_preset_name(self, instance, value, **kwargs):
        self.text = value
