import json
import asyncio
import logging

logging.basicConfig(format="%(asctime)s [%(levelname)s] - %(funcName)s: %(message)s", level=logging.INFO)

from sofi.app import Sofi
from sofi.ui import (
    Container, Heading, View, Row, Column, ButtonGroup, Button,
)

from pydispatch import Dispatcher, Property
from pydispatch.properties import ListProperty

from vidhubcontrol.backends.dummy import DummyBackend
logger = logging.getLogger(__name__)

class SofiDataId(Dispatcher):
    sofi_data_id_key = 'data-sofi-id'
    def __init__(self, **kwargs):
        self.app = kwargs.get('app')
    def get_data_id(self):
        return str(id(self))
    def get_data_id_attr(self):
        return {self.sofi_data_id_key:self.get_data_id()}

class ButtonGrid(SofiDataId):
    label_property = None
    num_buttons_property = None
    labels = ListProperty()
    buttons = ListProperty()
    button_states = ListProperty()
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.vidhub = kwargs.get('vidhub')
        self.vidhub_view = kwargs.get('vidhub_view')
        self.vidhub.bind(**{self.label_property:self.on_labels_set})
        self.vidhub_view.bind(selected_output=self.on_selected_output)
        self.widget = Container(attrs=self.get_data_id_attr())
        h = Heading(text=self.__class__.__name__)
        self.widget.addelement(h)
        num_buttons = getattr(self.vidhub, self.num_buttons_property)
        if num_buttons:
            self.build_buttons()
        else:
            self.vidhub.bind(**{self.num_buttons_property:self.on_num_buttons})
    def on_num_buttons(self, *args, **kwargs):
        self.build_buttons()
        self.vidhub.unbind(self.on_num_buttons)
    def build_buttons(self):
        assert len(self.buttons) == 0
        num_buttons = getattr(self.vidhub, self.num_buttons_property)
        if len(self.button_states) != num_buttons:
            self.button_states = [False]*num_buttons
        btns_per_row = int(num_buttons // 2)
        btngrp = ButtonGroup(justified=True)
        self.widget.addelement(btngrp)
        for i in range(num_buttons):
            if i % btns_per_row == 0:
                btngrp = ButtonGroup(justified=True)
                self.widget.addelement(btngrp)
            try:
                lbl = getattr(self.vidhub, self.label_property)[i]
            except IndexError:
                lbl = ''
            state = self.button_states[i]
            if state:
                severity = 'primary'
            else:
                severity = 'default'
            attrs = {self.sofi_data_id_key:'{}_{}'.format(self.get_data_id(), i)}
            btn = Button(text=lbl, severity=severity, attrs=attrs)
            self.buttons.append(btn)
            btngrp.addelement(btn)

        self.bind(button_states=self.on_button_state)
    def on_button_state(self, instance, value, **kwargs):
        keys = kwargs.get('keys')
        if keys is None:
            keys = range(len(value))
        for key in keys:
            state = value[key]
            btn = self.buttons[key]
            selector = "[{}='{}']".format(self.sofi_data_id_key, btn.attrs[self.sofi_data_id_key])
            #selector = "[{}='{}_{}']".format(self.sofi_data_id_key, self.get_data_id(), key)
            if state:
                self.app.removeclass(selector, 'btn-default')
                self.app.addclass(selector, 'btn-primary')
            else:
                self.app.removeclass(selector, 'btn-primary')
                self.app.addclass(selector, 'btn-secondary')
    def on_labels_set(self, instance, value, **kwargs):
        keys = kwargs.get('keys')
        if keys is None:
            keys = range(len(value))
        for key in keys:
            lbl = value[key]
            btn = self.buttons[key]
            selector = "[{}='{}']".format(self.sofi_data_id_key, btn.attrs[self.sofi_data_id_key])
            self.app.text(selector, lbl)

class InputButtons(ButtonGrid):
    label_property = 'input_labels'
    num_buttons_property = 'num_inputs'
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.vidhub.bind(crosspoints=self.on_vidhub_crosspoints)
    def on_vidhub_crosspoints(self, instance, value, **kwargs):
        self.on_selected_output(self.vidhub_view, self.vidhub_view.selected_output)
    def on_selected_output(self, instance, value, **kwargs):
        for i, state in enumerate(self.button_states):
            if not state:
                continue
            self.button_states[i] = False
        i = self.vidhub.crosspoints[value]
        self.button_states[i] = True
        logger.info('selected_output={}, crosspoint={}'.format(value, i))
    async def on_click(self, data_id):
        if data_id.split('_')[0] != self.get_data_id():
            return
        i = int(data_id.split('_')[1])
        await self.vidhub.set_crosspoint(self.vidhub_view.selected_output, i)


class OutputButtons(ButtonGrid):
    label_property = 'output_labels'
    num_buttons_property = 'num_outputs'
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    def on_selected_output(self, instance, value, **kwargs):
        for i, state in enumerate(self.button_states):
            if not state:
                continue
            self.button_states[i] = False
        self.button_states[value] = True
    async def on_click(self, data_id):
        if data_id.split('_')[0] != self.get_data_id():
            return
        i = int(data_id.split('_')[1])
        self.vidhub_view.selected_output = i

class PresetButtons(SofiDataId):
    presets = ListProperty()
    record_enable = Property(False)
    num_presets = 8
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.vidhub = kwargs.get('vidhub')
        self.widget = Container()
        self.presets = [[]]*8
        h = Heading(text='Presets')
        self.widget.addelement(h)
        btngrp = ButtonGroup(justified=True)
        for i in range(self.num_presets):
            attrs = {self.sofi_data_id_key:'{}_{}'.format(self.get_data_id(), i)}
            btn = Button(text=str(i+1), cl='preset-btn', attrs=attrs)
            btngrp.addelement(btn)
        self.widget.addelement(btngrp)
        attrs = {self.sofi_data_id_key:'{}_{}'.format(self.get_data_id(), 'record')}
        self.record_enable_btn = Button(text='Record', attrs=attrs)
        self.widget.addelement(self.record_enable_btn)
        self.bind(record_enable=self.on_record_enable)
    def on_record_enable(self, instance, value, **kwargs):
        id_key = self.record_enable_btn.attrs[self.sofi_data_id_key]
        selector = "[{}='{}']".format(self.sofi_data_id_key, id_key)
        if value:
            self.app.addclass(selector, 'btn-danger')
        else:
            self.app.removeclass(selector, 'btn-danger')
    async def on_click(self, data_id):
        if data_id.split('_')[0] != self.get_data_id():
            return
        if data_id.split('_')[1] == 'record':
            self.record_enable = not self.record_enable
            return
        i = int(data_id.split('_')[1])
        if self.record_enable:
            self.presets[i] = self.vidhub.crosspoints[:]
            self.record_enable = False
        elif len(self.presets[i]):
            args = [(i, v) for i, v in enumerate(self.presets[i])]
            await self.vidhub.set_crosspoints(*args)

class VidHubView(SofiDataId):
    selected_output = Property(0)
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.vidhub = kwargs.get('vidhub')
        self.input_buttons = InputButtons(vidhub_view=self, vidhub=self.vidhub, app=self.app)
        self.output_buttons = OutputButtons(vidhub_view=self, vidhub=self.vidhub, app=self.app)
        self.preset_buttons = PresetButtons(vidhub=self.vidhub, app=self.app)
        self.widget = Container()
        row = Row()
        col = Column(count=12)
        row.addelement(col)
        col.addelement(self.input_buttons.widget)
        self.widget.addelement(row)
        row = Row()
        col = Column(count=12)
        row.addelement(col)
        col.addelement(self.output_buttons.widget)
        self.widget.addelement(row)
        row = Row()
        col = Column(count=12)
        row.addelement(col)
        col.addelement(self.preset_buttons.widget)
        self.widget.addelement(row)
    async def on_click(self, data_id):
        await self.input_buttons.on_click(data_id)
        await self.output_buttons.on_click(data_id)
        await self.preset_buttons.on_click(data_id)

class App(object):
    def __init__(self, **kwargs):
        self.vidhub = kwargs.get('vidhub')
        self.app = Sofi()
        self.app.register('init', self.oninit)
        self.app.register('load', self.onload)
    def start(self):
        self.app.start()
    async def oninit(self, e):
        await self.vidhub.connect()
        v = View()
        self.vidhub_view = VidHubView(vidhub=self.vidhub, app=self.app)
        v.addelement(self.vidhub_view.widget)
        self.app.load(str(v))
    async def onload(self, e):
        self.app.register('click', self.on_click, selector='button')
    async def on_click(self, e):
        data_id = e['event_object']['target']['data-sofi-id']
        logger.info(data_id)
        await self.vidhub_view.on_click(data_id)

if __name__ == '__main__':
    App(vidhub=DummyBackend()).start()
