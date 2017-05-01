from kivy.properties import (
    ObjectProperty,
    NumericProperty,
    StringProperty,
    BooleanProperty,
    OptionProperty,
    ListProperty,
    DictProperty,
)
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout

from vidhubcontrol.kivyui.vidhubview import ButtonGrid, ButtonGridBtn

class VidhubPresetEditPopup(Popup):
    app = ObjectProperty(None)
    preset = ObjectProperty(None)
    crosspoint_container = ObjectProperty(None)
    crosspoint_widgets = DictProperty()
    crosspoint_widgets_built = BooleanProperty(False)
    __events__ = ['on_submit', 'on_cancel']
    def on_preset(self, *args):
        if self.crosspoint_widgets_built:
            return
        if self.crosspoint_container is None:
            return
        self.build_crosspoint_widgets()
    def on_crosspoint_container(self, *args):
        self.crosspoint_container.bind(minimum_height=self.crosspoint_container.setter('height'))
        if self.crosspoint_widgets_built:
            return
        if self.preset is None:
            return
        self.build_crosspoint_widgets()
    def build_crosspoint_widgets(self, *args, **kwargs):
        self.crosspoint_widgets_built = True
        for out_idx in sorted(self.preset.crosspoints.keys()):
            in_idx = self.preset.crosspoints[out_idx]
            w = VidhubPresetEditCrosspoint(edit_widget=self, dest=out_idx, source=in_idx)
            self.crosspoint_widgets[out_idx] = w
            self.crosspoint_container.add_widget(w)
            w.bind(
                dest=self.on_crosspoint_widget_dest,
                on_crosspoint_remove=self.on_crosspoint_widget_remove,
            )
    def on_crosspoint_widget_remove(self, *args, **kwargs):
        w = kwargs['widget']
        del self.crosspoint_widgets[w.dest]
        self.crosspoint_container.remove_widget(w)
    def on_crosspoint_widget_dest(self, instance, value):
        old_widget = self.crosspoint_widgets.get(value)
        if old_widget is not None:
            self.on_crosspoint_widget_remove(widget=old_widget)
        old_dest = None
        for dest, w in self.crosspoint_widgets.items():
            if w == instance:
                old_dest = dest
                break
        self.crosspoint_widgets[value] = instance
        del self.crosspoint_widgets[old_dest]
    def next_available_dest(self):
        all_dests = set(range(self.preset.backend.num_outputs))
        used_dests = set(self.crosspoint_widgets.keys())
        avail = all_dests - used_dests
        if not len(avail):
            return None
        return min(avail)
    def get_crosspoint_dict(self):
        return {w.dest:w.source for w in self.crosspoint_widgets.values()}
    def add_crosspoint(self, **kwargs):
        kwargs['edit_widget'] = self
        kwargs.setdefault('source', 0)
        dest = kwargs.get('dest')
        if dest is None:
            dest = self.next_available_dest()
            if dest is None:
                return
            else:
                kwargs['dest'] = dest
        w = VidhubPresetEditCrosspoint(**kwargs)
        self.crosspoint_widgets[w.dest] = w
        self.crosspoint_container.add_widget(w)
        w.bind(
            dest=self.on_crosspoint_widget_dest,
            on_crosspoint_remove=self.on_crosspoint_widget_remove,
        )
        return w
    def on_submit(self, *args):
        self.preset.crosspoints = self.get_crosspoint_dict()
        self.dismiss()
    def on_cancel(self, *args):
        self.dismiss()

class VidhubPresetEditGridPopup(Popup):
    crosspoint_widget = ObjectProperty(None)
    button_grid = ObjectProperty(None)
    __events__ = ['on_submit', 'on_cancel']
    def on_submit(self, *args, **kwargs):
        self.dismiss()
    def on_cancel(self, *args, **kwargs):
        self.dismiss()

class VidhubPresetEditInputPopup(VidhubPresetEditGridPopup):
    selected_output = NumericProperty(0)
    def on_submit(self, *args, **kwargs):
        selected = self.button_grid.selected_buttons
        w = self.crosspoint_widget
        if not len(selected):
            w.dispatch('on_crosspoint_remove', widget=w)
        else:
            w.source = selected[0]
        super().on_submit(*args, **kwargs)

class VidhubPresetEditOutputPopup(VidhubPresetEditGridPopup):
    selected_input = NumericProperty(0)
    def on_submit(self, *args, **kwargs):
        selected = self.button_grid.selected_buttons
        edit_widget = self.crosspoint_widget.edit_widget
        src_idx = self.selected_input
        if not len(selected):
            self.crosspoint_widget.dispatch('on_crosspoint_remove', widget=self.crosspoint_widget)
        else:
            self.crosspoint_widget.dest = selected[0]
        super().on_submit(*args, **kwargs)


class VidhubPresetEditGrid(ButtonGrid):
    crosspoint_widget = ObjectProperty(None)
    preset = ObjectProperty(None)
    selections_loaded = BooleanProperty(False)
    @classmethod
    def get_button_cls(cls):
        return VidhubPresetEditGridBtn
    def on_vidhub(self, instance, vidhub):
        super().on_vidhub(instance, vidhub)
        self.build_labels()
        self.num_buttons = len(self.button_labels)
        self.update_selections()
    def on_preset(self, *args):
        self.vidhub = self.preset.backend

class VidhubPresetEditInputGrid(VidhubPresetEditGrid):
    selected_output = NumericProperty(0)
    def build_labels(self):
        lbls = self.vidhub.input_labels
        self.button_labels = {i:lbl for i, lbl in enumerate(lbls)}
    def update_selections(self, *args, **kwargs):
        if self.selections_loaded:
            return
        self.selected_buttons = [self.crosspoint_widget.source]
        self.selections_loaded = True
    def on_selected_output(self, instance, value):
        self.selections_loaded = False
        self.update_selections()
    def on_button_release(self, *args, **kwargs):
        btn = kwargs['button']
        if btn.index in self.selected_buttons:
            return
        self.selected_buttons = [btn.index]

class VidhubPresetEditOutputGrid(VidhubPresetEditGrid):
    selected_input = NumericProperty(0)
    unselected_buttons = ListProperty()
    def build_labels(self):
        lbls = self.vidhub.output_labels
        self.button_labels = {i:lbl for i, lbl in enumerate(lbls)}
    def update_selections(self, *args, **kwargs):
        if self.selections_loaded:
            return
        self.selected_buttons = [self.crosspoint_widget.dest]
        self.selections_loaded = True
    def on_selected_input(self, instance, value):
        self.selections_loaded = False
        self.update_selections()
    def on_button_release(self, *args, **kwargs):
        btn = kwargs['button']
        if btn.index in self.selected_buttons:
            return
        self.selected_buttons = [btn.index]

class VidhubPresetEditGridBtn(ButtonGridBtn):
    pass


class VidhubPresetEditCrosspoint(BoxLayout):
    edit_widget = ObjectProperty(None)
    preset = ObjectProperty(None)
    selection_popup = ObjectProperty(None, allownone=True)
    source = NumericProperty(0)
    dest = NumericProperty(0)
    source_label = StringProperty('')
    dest_label = StringProperty('')
    __events__ = ['on_crosspoint_remove']
    def on_edit_widget(self, *args):
        self.preset = self.edit_widget.preset
    def on_preset(self, *args):
        self.update_labels()
    def on_source(self, *args):
        self.update_labels()
    def on_dest(self, *args):
        self.update_labels()
    def update_labels(self, *args, **kwargs):
        if self.preset is None:
            return
        vidhub = self.preset.backend
        self.source_label = vidhub.input_labels[self.source]
        self.dest_label = vidhub.output_labels[self.dest]
    def open_input_selection(self):
        w = self.selection_popup = VidhubPresetEditInputPopup(crosspoint_widget=self)
        w.bind(on_dismiss=self.on_selection_popup_dismiss)
        w.open()
    def open_output_selection(self):
        w = self.selection_popup = VidhubPresetEditOutputPopup(crosspoint_widget=self)
        w.bind(on_dismiss=self.on_selection_popup_dismiss)
        w.open()
    def on_selection_popup_dismiss(self, *args):
        self.selection_popup = None
    def on_crosspoint_remove(self, *args, **kwargs):
        pass # pragma: no cover
