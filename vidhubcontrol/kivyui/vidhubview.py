from kivy.clock import Clock, mainthread
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
    vidhub = ObjectProperty(None, allownone=True)
    name = StringProperty('')
    connected = BooleanProperty(False)
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
    def on_preset_button_grid(self, *args):
        if self.preset_button_grid is None:
            return
        self.preset_button_grid.vidhub_widget = self
    def on_vidhub(self, *args):
        if self.vidhub is None:
            self.name = ''
            self.connected = False
            self.crosspoints = []
            return
        self.name = self.vidhub.device_name
        self.connected = self.vidhub.connected
        self.crosspoints[:] = self.vidhub.crosspoints[:]
        self.app.bind_events(self.vidhub,
            connected=self.on_vidhub_connected,
            device_name=self.on_vidhub_device_name,
            crosspoints=self.on_vidhub_crosspoints,
        )
    def on_app(self, *args):
        if self.app is None:
            return
        device = self.app.selected_device
        if device is not None and device.device_type == 'vidhub':
            self.vidhub = device
        self.app.bind(selected_device=self.on_app_selected_device)
    def on_app_selected_device(self, instance, value):
        if self.vidhub is not None:
            self.vidhub.unbind(self)
            self.input_button_grid.unbind_vidhub()
            self.output_button_grid.unbind_vidhub()
            self.preset_button_grid.unbind_vidhub()
        if value.device_type == 'vidhub':
            self.vidhub = value
        else:
            self.vidhub = None
    @mainthread
    def on_vidhub_connected(self, instance, value, **kwargs):
        self.connected = value
    @mainthread
    def on_vidhub_device_name(self, instance, value, **kwargs):
        self.name = value
    @mainthread
    def on_vidhub_crosspoints(self, instance, value, **kwargs):
        if self.crosspoints == value:
            return
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
    vidhub = ObjectProperty(None, allownone=True)
    vidhub_widget = ObjectProperty(None)
    num_buttons = NumericProperty()
    selected_first = BooleanProperty(False)
    selected_buttons = ListProperty()
    button_labels = DictProperty()
    button_widgets = DictProperty()
    max_columns = NumericProperty(8)
    min_columns = NumericProperty(6)
    __events__ = ['on_button_release']
    @classmethod
    def get_button_cls(cls):
        return ButtonGridBtn
    def unbind_vidhub(self):
        self.vidhub.unbind(self)
        self.vidhub = None
    def on_vidhub(self, instance, vidhub):
        self.clear_widgets()
        self.button_widgets.clear()
        self.num_buttons = 0
        self.button_labels.clear()
        self.selected_first = False
        self.selected_buttons = []
    def on_vidhub_widget(self, *args):
        if self.vidhub_widget is None:
            return
        self.vidhub_widget.bind(
            crosspoints=self.update_selections,
        )
    def find_cols_rows(self):
        i = self.num_buttons
        c = self.max_columns
        while c > 1:
            if c > i:
                c -= 1
                continue
            r = i // c
            if i % c != 0:
                r += 1
            if r > 1 and r * c == i:
                return c, r
            c -= 1
            if c == self.min_columns:
                return c, r
        return None, None
    def on_num_buttons(self, instance, value):
        if not value:
            return
        if not value:
            return
        c, r = self.find_cols_rows()
        self.cols, self.rows = c, r
        btncls = self.get_button_cls()
        for i in range(value):
            if i in self.button_widgets:
                continue
            btn = btncls(index=i, button_grid=self)
            self.button_widgets[i] = btn
        for i in sorted(self.button_widgets.keys()):
            btn = self.button_widgets[i]
            self.add_widget(btn)
    @mainthread
    def on_vidhub_labels(self, instance, value, **kwargs):
        for i, lbl in enumerate(value):
            self.button_labels[i] = lbl
    @mainthread
    def on_vidhub_num_buttons(self, instance, value, **kwargs):
        self.num_buttons = value
    def on_button_release(self, *args, **kwargs):
        pass

class InputButtonGrid(ButtonGrid):
    @classmethod
    def get_button_cls(cls):
        return InputButtonGridBtn
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
    @classmethod
    def get_button_cls(cls):
        return OutputButtonGridBtn
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

class PresetButtonGrid(ButtonGrid):
    record_enable = BooleanProperty(False)
    def on_vidhub(self, instance, vidhub):
        super().on_vidhub(instance, vidhub)
        if not vidhub:
            return
        self.button_labels = {p.index:p.name for p in vidhub.presets}
        if len(vidhub.presets) <= 12:
            for i in range(12):
                self.button_labels.setdefault(i, 'Preset {}'.format(i+1))
            self.num_buttons = 12
        else:
            self.num_buttons = len(vidhub.presets)
        self.app.bind_events(vidhub,
            on_preset_added=self.on_preset_added,
            on_preset_active=self.on_preset_active,
        )
        for preset in vidhub.presets:
            self.on_preset_active(preset=preset, value=preset.active)
            self.app.bind_events(preset,
                name=self.on_preset_name,
            )
    def unbind_vidhub(self, *args, **kwargs):
        self.vidhub.unbind(self)
        for preset in self.vidhub.presets:
            preset.unbind(self)
    @mainthread
    def on_preset_added(self, *args, **kwargs):
        print('on_preset_added: ', args, kwargs)
        preset = kwargs.get('preset')
        while len(self.button_labels) < len(self.vidhub.presets):
            self.button_labels.append('')
        self.button_labels[preset.index] = preset.name
        if len(self.button_labels) < self.num_buttons:
            self.num_buttons = len(self.button_labels)
        if preset.active and preset.index not in self.selected_buttons:
            self.selected_buttons.append(preset.index)
        self.app.bind_events(preset,
            name=self.on_preset_name,
        )
    @mainthread
    def on_preset_name(self, instance, value, **kwargs):
        self.button_labels[instance.index] = value
    @mainthread
    def on_preset_active(self, *args, **kwargs):
        instance = kwargs['preset']
        value = kwargs['value']
        print('on_preset_active: ', instance.index, value)
        if value:
            if instance.index not in self.selected_buttons:
                self.selected_buttons.append(instance.index)
        else:
            if instance.index in self.selected_buttons:
                self.selected_buttons.remove(instance.index)
    def on_button_release(self, *args, **kwargs):
        button = kwargs['button']
        try:
            preset = self.vidhub.presets[button.index]
        except IndexError:
            preset = None
        print('preset button: ', button.index, preset)
        if self.record_enable:
            if preset is None:
                name = 'Preset {}'.format(button.index + 1)
                self.app.run_async_coro(self.vidhub.store_preset(name=name, index=button.index))
            else:
                self.app.run_async_coro(preset.store())
            self.record_enable = False
        else:
            if preset is None:
                return
            self.app.run_async_coro(preset.recall())


class ButtonGridBtn(Button):
    title_text = StringProperty('')
    content_text = StringProperty('')
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
    def _do_press(self, *args, **kwargs):
        return
    def _do_release(self, *args, **kwargs):
        return

class InputButtonGridBtn(ButtonGridBtn):
    selected_outputs = ListProperty([])
    vidhub_widget = ObjectProperty(None)
    def on_parent(self, *args):
        if self.parent is None and self.vidhub_widget is not None:
            self.vidhub_widget.unbind(crosspoints=self.update_crosspoints)
            self.vidhub_widget.output_button_grid.unbind(button_labels=self.on_output_button_labels)
    def on_vidhub_widget(self, *args):
        if self.vidhub_widget is None:
            return
        self.update_crosspoints()
        self.vidhub_widget.bind(crosspoints=self.update_crosspoints)
        self.vidhub_widget.output_button_grid.bind(button_labels=self.on_output_button_labels)
    def update_crosspoints(self, *args, **kwargs):
        l = []
        for out_idx, in_idx in enumerate(self.vidhub_widget.crosspoints):
            if in_idx == self.index:
                l.append(out_idx)
        self.selected_outputs = l
    def on_selected_outputs(self, instance, value):
        if not len(value):
            self.content_text = ''
        elif len(value) == 1:
            self.content_text = self.vidhub_widget.output_button_grid.button_labels[value[0]]
        else:
            self.content_text = ','.join((str(i) for i in self.selected_outputs))
    def on_output_button_labels(self, instance, value):
        self.on_selected_outputs(None, self.selected_outputs)

class OutputButtonGridBtn(ButtonGridBtn):
    selected_input = NumericProperty(0)
    vidhub_widget = ObjectProperty(None)
    def on_parent(self, *args):
        if self.parent is None and self.vidhub_widget is not None:
            self.vidhub_widget.unbind(crosspoints=self.update_crosspoints)
            self.vidhub_widget.input_button_grid.unbind(button_labels=self.on_input_button_labels)
    def on_vidhub_widget(self, *args):
        if self.vidhub_widget is None:
            return
        self.update_crosspoints()
        self.vidhub_widget.bind(crosspoints=self.update_crosspoints)
        self.vidhub_widget.input_button_grid.bind(button_labels=self.on_input_button_labels)
    def update_crosspoints(self, *args, **kwargs):
        self.selected_input = int(self.vidhub_widget.crosspoints[self.index])
        self.on_input_button_labels(None, self.vidhub_widget.input_button_grid.button_labels)
    def on_input_button_labels(self, instance, value):
        self.content_text = value.get(self.selected_input, '')
