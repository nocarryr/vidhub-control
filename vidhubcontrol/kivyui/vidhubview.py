from kivy.clock import Clock
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

class VidhubWidget(BoxLayout):
    app = ObjectProperty(None)
    vidhub = ObjectProperty(None)
    name = StringProperty('')
    input_button_grid = ObjectProperty(None)
    output_button_grid = ObjectProperty(None)
    crosspoints = ListProperty()
    first_selected = OptionProperty('None', options=['input', 'output', 'None'])
    def on_input_button_grid(self, *args):
        if self.input_button_grid is None:
            return
        self.input_button_grid.vidhub_widget = self
        self.input_button_grid.bind(on_button_release=self.on_input_button_release)
    def on_output_button_grid(self, *args):
        if self.output_button_grid is None:
            return
        self.output_button_grid.vidhub_widget = self
        self.output_button_grid.bind(on_button_release=self.on_output_button_release)
    def on_vidhub(self, *args):
        if self.vidhub is None:
            return
        self.name = self.vidhub.device_name
        self.input_button_grid.vidhub = self.vidhub
        self.output_button_grid.vidhub = self.vidhub
        self.crosspoints[:] = self.vidhub.crosspoints[:]
        self.app.bind_events(self.vidhub,
            device_name=self.on_vidhub_device_name,
            crosspoints=self.on_vidhub_crosspoints,
        )
    def on_app(self, *args):
        if self.app is None:
            return
        self.vidhub = self.app.selected_vidhub
        self.app.bind(selected_vidhub=self.on_app_selected_vidhub)
    def on_app_selected_vidhub(self, instance, value):
        if self.vidhub is not None:
            self.vidhub.unbind(self)
            self.vidhub.unbind(self.input_button_grid)
            self.vidhub.unbind(self.output_button_grid)
        self.vidhub = value
    def on_vidhub_device_name(self, instance, value, **kwargs):
        self.name = value
    def on_vidhub_crosspoints(self, instance, value, **kwargs):
        self.crosspoints[:] = value[:]
    def deselect_all(self, *args, **kwargs):
        self.first_selected = 'None'
        self.input_button_grid.selected_buttons = []
        self.input_button_grid.selected_first = False
        self.output_button_grid.selected_buttons = []
        self.output_button_grid.selected_first = False
    def on_input_button_release(self, *args, **kwargs):
        btn = kwargs['button']
        grid = kwargs['button_grid']
        if self.first_selected == 'None':
            self.first_selected = 'input'
            grid.selected_first = True
            grid.selected_buttons = [btn.index]
            self.output_button_grid.selected_first = False
            self.output_button_grid.update_selections()
        elif self.first_selected == 'input':
            if btn.index in grid.selected_buttons:
                self.deselect_all()
            else:
                grid.selected_buttons = [btn.index]
                self.output_button_grid.update_selections()
        else:
            out_idx = self.output_button_grid.selected_buttons[0]
            if btn.index == self.crosspoints[out_idx]:
                return
            self.vidhub.crosspoint_control[out_idx] = btn.index
    def on_output_button_release(self, *args, **kwargs):
        btn = kwargs['button']
        grid = kwargs['button_grid']
        if self.first_selected == 'None':
            self.first_selected = 'output'
            grid.selected_first = True
            grid.selected_buttons = [btn.index]
            self.input_button_grid.selected_first = False
            self.input_button_grid.update_selections()
        elif self.first_selected == 'output':
            if btn.index in grid.selected_buttons:
                self.deselect_all()
            else:
                grid.selected_buttons = [btn.index]
                self.input_button_grid.update_selections()
        else:
            in_idx = self.input_button_grid.selected_buttons[0]
            if self.crosspoints[btn.index] == in_idx:
                return
            self.vidhub.crosspoint_control[btn.index] = in_idx


class ButtonGrid(GridLayout):
    app = ObjectProperty(None)
    vidhub = ObjectProperty(None)
    vidhub_widget = ObjectProperty(None)
    num_buttons = NumericProperty()
    selected_first = BooleanProperty(False)
    selected_buttons = ListProperty()
    button_labels = DictProperty()
    button_widgets = DictProperty()
    __events__ = ['on_button_release']
    def on_vidhub(self, instance, vidhub):
        self.num_buttons = 0
        self.button_labels = []
        self.selected_first = False
        self.selected_buttons = []
    def on_vidhub_widget(self, *args):
        if self.vidhub_widget is None:
            return
        self.vidhub_widget.bind(
            crosspoints=self.update_selections,
        )
    def on_num_buttons(self, instance, value):
        if not value:
            return
        for w in self.children[:]:
            if isinstance(w, ButtonGridBtn):
                self.remove_widget(w)
        if not value:
            self.button_widgets.clear()
            return
        if value % 8 == 0:
            self.cols = 8
        else:
            self.cols = 6
        self.rows = value // self.cols
        if value % (self.cols * self.rows):
            self.rows += 1
        for i in range(value):
            if i in self.button_widgets:
                continue
            btn = ButtonGridBtn(index=i, button_grid=self)
            self.button_widgets[i] = btn
        for i in sorted(self.button_widgets.keys()):
            btn = self.button_widgets[i]
            self.add_widget(btn)
    def on_vidhub_labels(self, instance, value, **kwargs):
        for i, lbl in enumerate(value):
            self.button_labels[i] = lbl
    def on_vidhub_num_buttons(self, instance, value, **kwargs):
        self.num_buttons = value
    def on_button_release(self, *args, **kwargs):
        pass

class InputButtonGrid(ButtonGrid):
    def on_vidhub(self, instance, vidhub):
        super().on_vidhub(instance, vidhub)
        if not vidhub:
            return
        self.button_labels = {i:lbl for i, lbl in enumerate(vidhub.input_labels)}
        self.num_buttons = vidhub.num_inputs
        self.app.bind_events(vidhub,
            input_labels=self.on_vidhub_labels,
            num_inputs=self.on_vidhub_num_buttons,
        )
    def update_selections(self, *args, **kwargs):
        if self.selected_first:
            return
        xpts = self.vidhub_widget.crosspoints
        dest_sel = self.vidhub_widget.output_button_grid.selected_buttons
        if not len(xpts):
            return
        if not len(dest_sel):
            return
        dest_idx = dest_sel[0]
        self.selected_buttons = [xpts[dest_idx]]

class OutputButtonGrid(ButtonGrid):
    def on_vidhub(self, instance, vidhub):
        super().on_vidhub(instance, vidhub)
        if not vidhub:
            return
        self.button_labels = {i:lbl for i, lbl in enumerate(vidhub.output_labels)}
        self.num_buttons = vidhub.num_outputs
        self.app.bind_events(vidhub,
            output_labels=self.on_vidhub_labels,
            num_outputs=self.on_vidhub_num_buttons,
        )
    def update_selections(self, *args, **kwargs):
        if self.selected_first:
            return
        xpts = self.vidhub_widget.crosspoints
        src_sel = self.vidhub_widget.input_button_grid.selected_buttons
        if not len(xpts):
            return
        if not len(src_sel):
            return
        src_idx = src_sel[0]
        self.selected_buttons[:] = [i for i, v in enumerate(xpts) if v == src_idx]

class ButtonGridBtn(Button):
    index = NumericProperty()
    button_grid = ObjectProperty(None)
    flash_interval = NumericProperty(.5)
    flash_event = ObjectProperty(None, allownone=True)
    selection_state = OptionProperty('normal', options=['normal', 'down', 'flash'])
    def on_button_grid(self, *args):
        if self.button_grid is None:
            return
        self.button_grid.bind(
            selected_first=self.on_grid_selected_buttons,
            selected_buttons=self.on_grid_selected_buttons,
        )
    def on_grid_selected_buttons(self, *args):
        selected_first = self.button_grid.selected_first
        if self.index in self.button_grid.selected_buttons:
            if selected_first:
                self.selection_state = 'flash'
            else:
                self.selection_state = 'down'
        else:
            self.selection_state = 'normal'
    def on_selection_state(self, instance, value):
        if self.flash_event is not None:
            self.flash_event.cancel()
            self.flash_event = None
        if value == 'flash':
            self.toggle_state()
            self.flash_event = Clock.schedule_interval(self.toggle_state, self.flash_interval)
        else:
            self.state = value
    def toggle_state(self, *args, **kwargs):
        if self.state == 'normal':
            self.state = 'down'
        else:
            self.state = 'normal'
    def on_release(self, *args, **kwargs):
        kwargs['button'] = self
        kwargs['button_grid'] = self.parent
        self.parent.dispatch('on_button_release', *args, **kwargs)
    def _do_press(self):
        return
    def _do_release(self):
        return
