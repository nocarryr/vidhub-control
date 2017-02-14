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
        if self.app.selected_vidhub is not None:
            self.bind_vidhub()
        self.app.bind(selected_vidhub=self.on_app_selected_vidhub)
    def on_app_selected_vidhub(self, instance, value):
        if self.vidhub is not None:
            self.unbind_vidhub(self.vidhub)
        self.vidhub = value
        self.build_items()
        if value is not None:
            self.bind_vidhub()
    def bind_vidhub(self):
        self.vidhub.bind(**{self.vidhub_prop_get:self.on_vidhub_labels})
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


class VidhubEditLabelItem(BoxLayout):
    index = NumericProperty()
    text = StringProperty()
