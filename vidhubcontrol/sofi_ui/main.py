import json
import asyncio
import logging

logging.basicConfig(format="%(asctime)s [%(levelname)s] - %(funcName)s: %(message)s", level=logging.INFO)

from sofi.app import Sofi
from sofi.ui import (
    Container, Heading, View, Row, Column, ButtonGroup, Button,
    Navbar, Dropdown, DropdownItem, PageHeader,
)

from pydispatch import Dispatcher, Property
from pydispatch.properties import ListProperty

from vidhubcontrol.config import Config

config = Config.load()

logger = logging.getLogger(__name__)

class SofiDataId(Dispatcher):
    sofi_data_id_key = 'data-sofi-id'
    def __init__(self, **kwargs):
        self.app = kwargs.get('app')
    def remove(self):
        if hasattr(self, 'vidhub'):
            self.vidhub.unbind(self)
        selector = "[{}='{}']".format(self.sofi_data_id_key, self.get_data_id())
        self.app.remove(selector)
        logger.info('remove {}'.format(selector))
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
                self.app.addclass(selector, 'btn-default')
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
    def build_buttons(self):
        self.button_states = [False]*self.vidhub.num_inputs
        self.on_selected_output(self.vidhub_view, self.vidhub_view.selected_output)
        super().build_buttons()
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
    def build_buttons(self):
        self.button_states = [False]*self.vidhub.num_outputs
        self.on_selected_output(self.vidhub_view, self.vidhub_view.selected_output)
        super().build_buttons()
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
    record_enable = Property(False)
    preset_buttons = ListProperty()
    num_presets = 8
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.vidhub = kwargs.get('vidhub')
        self.widget = Container(attrs=self.get_data_id_attr())
        h = Heading(text='Presets')
        self.widget.addelement(h)
        btngrp = ButtonGroup(justified=True)
        for i in range(self.num_presets):
            try:
                preset = self.vidhub.presets[i]
                name = preset.name
                active = preset.active
            except IndexError:
                name = str(i+1)
                active = False
            attrs = {self.sofi_data_id_key:'{}_{}'.format(self.get_data_id(), i)}
            if active:
                severity = 'primary'
            else:
                severity = 'default'
            btn = Button(text=name, cl='preset-btn', severity=severity, attrs=attrs)
            btngrp.addelement(btn)
            self.preset_buttons.append(btn)
        self.widget.addelement(btngrp)
        attrs = {self.sofi_data_id_key:'{}_{}'.format(self.get_data_id(), 'record')}
        self.record_enable_btn = Button(text='Record', attrs=attrs)
        self.widget.addelement(self.record_enable_btn)
        self.bind(record_enable=self.on_record_enable)
        self.vidhub.bind(
            on_preset_added=self.on_preset_added,
            on_preset_active=self.on_preset_active,
        )
    def remove(self):
        for preset in self.vidhub.presets:
            preset.unbind(self)
        super().remove()
    def on_record_enable(self, instance, value, **kwargs):
        id_key = self.record_enable_btn.attrs[self.sofi_data_id_key]
        selector = "[{}='{}']".format(self.sofi_data_id_key, id_key)
        if value:
            self.app.addclass(selector, 'btn-danger')
        else:
            self.app.removeclass(selector, 'btn-danger')
    def on_preset_added(self, *args, **kwargs):
        preset = kwargs.get('preset')
        try:
            btn = self.preset_buttons[preset.index]
        except IndexError:
            return
        selector = "[{}='{}']".format(self.sofi_data_id_key, btn.attrs[self.sofi_data_id_key])
        self.app.text(selector, preset.name)
        preset.bind(name=self.on_preset_name)
    def on_preset_name(self, instance, value, **kwargs):
        try:
            btn = self.preset_buttons[instance.index]
        except IndexError:
            return
        selector = "[{}='{}']".format(self.sofi_data_id_key, btn.attrs[self.sofi_data_id_key])
        self.app.text(selector, value)
    def on_preset_active(self, *args, **kwargs):
        preset = kwargs.get('preset')
        try:
            btn = self.preset_buttons[preset.index]
        except IndexError:
            return
        selector = "[{}='{}']".format(self.sofi_data_id_key, btn.attrs[self.sofi_data_id_key])
        if preset.active:
            self.app.removeclass(selector, 'btn-default')
            self.app.addclass(selector, 'btn-primary')
        else:
            self.app.removeclass(selector, 'btn-primary')
            self.app.addclass(selector, 'btn-default')
    async def on_click(self, data_id):
        if data_id.split('_')[0] != self.get_data_id():
            return
        if data_id.split('_')[1] == 'record':
            self.record_enable = not self.record_enable
            return
        i = int(data_id.split('_')[1])
        if self.record_enable:
            await self.vidhub.store_preset(index=i)
            self.record_enable = False
        else:
            try:
                preset = self.vidhub.presets[i]
            except IndexError:
                return
            await preset.recall()

class VidHubView(SofiDataId):
    selected_output = Property(0)
    vidhub = Property()
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.input_buttons = None
        self.output_buttons = None
        self.preset_buttons = None
        self.widget = Container(attrs=self.get_data_id_attr())
        self.bind(vidhub=self.on_vidhub)
        self.vidhub = kwargs.get('vidhub')
    def on_vidhub(self, instance, value, **kwargs):
        for attr in ['input_buttons', 'output_buttons', 'preset_buttons']:
            obj = getattr(self, attr)
            if obj is not None:
                obj.remove()
            setattr(self, attr, None)
        del self.widget._children[:]
        if self.vidhub is not None:
            self.build_view()
    def build_view(self):
        self.input_buttons = InputButtons(vidhub_view=self, vidhub=self.vidhub, app=self.app)
        self.output_buttons = OutputButtons(vidhub_view=self, vidhub=self.vidhub, app=self.app)
        self.preset_buttons = PresetButtons(vidhub=self.vidhub, app=self.app)
        self.widget.addelement(PageHeader(text=str(self.vidhub.device_id)))
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
        if self.app.loaded:
            selector = "[{}='{}']".format(self.sofi_data_id_key, self.get_data_id())
            self.app.replace(selector, str(self.widget))
    async def on_click(self, data_id):
        for attr in ['input_buttons', 'output_buttons', 'preset_buttons']:
            obj = getattr(self, attr)
            if obj is None:
                return
            await obj.on_click(data_id)

class App(object):
    def __init__(self, **kwargs):
        self.vidhub = kwargs.get('vidhub')
        self.app = Sofi()
        self.app.loaded = False
        self.app.register('init', self.oninit)
        self.app.register('load', self.onload)
    def start(self):
        self.app.start()
    async def oninit(self, e):
        await self.vidhub.connect()
        v = self.view = View()
        nav = Navbar(brand='Vidhub Control')
        dr = Dropdown('Select Device')
        for device_id, vidhub in config.vidhubs.items():
            dr.addelement(DropdownItem(
                str(device_id),
                cl='device-select',
                attrs={'data-device-id':str(device_id)},
            ))
        dr.addelement(DropdownItem(
            'None',
            cl='device-select',
            attrs={'data-device-id':'NONE'}
        ))
        nav.adddropdown(dr)
        v.addelement(nav)
        self.vidhub_view = VidHubView(vidhub=self.vidhub, app=self.app)
        v.addelement(self.vidhub_view.widget)
        self.app.load(str(v))
        self.app.loaded = True
    async def onload(self, e):
        self.app.register('click', self.on_device_select_click, selector='.device-select')
        self.app.register('click', self.on_click, selector='button')
    async def on_device_select_click(self, e):
        self.app.unregister('click', self.on_click, selector='button')
        device_id = e['event_object']['currentTarget']['data-device-id']
        if device_id == 'NONE':
            self.vidhub = None
            self.vidhub_view.vidhub = None
            return
        if device_id not in config.vidhubs:
            for key in config.vidhubs.keys():
                if str(key) == device_id:
                    device_id = key
                    break
        self.vidhub = config.vidhubs[device_id].backend
        logger.info('switching to vidhub {!r}'.format(self.vidhub))
        self.vidhub_view.vidhub = self.vidhub
        self.app.register('click', self.on_click, selector='button')
    async def on_click(self, e):
        data_id = e['event_object']['target']['data-sofi-id']
        logger.info(data_id)
        await self.vidhub_view.on_click(data_id)

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--addr', dest='hostaddr')
    p.add_argument('--port', dest='hostport', default=9990)
    args = p.parse_args()
    o = vars(args)
    if o.get('hostaddr'):
        vidhub = config.build_backend('TelnetBackend', **o)
    else:
        vidhub = config.build_backend('DummyBackend', device_id='dummy')
    App(vidhub=vidhub).start()
