import json
import asyncio
import logging

logging.basicConfig(format="%(asctime)s [%(levelname)s] - %(funcName)s: %(message)s", level=logging.INFO)

from sofi.app import Sofi
from sofi.ui import (
    Container, Heading, View, Row, Column, ButtonGroup, Button, Div, Input,
    Navbar, Dropdown, DropdownItem, PageHeader, Span, Element,
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
        selector = self.get_selector()
        self.app.remove(selector)
        logger.info('remove {}'.format(selector))
    def get_data_id(self):
        return str(id(self))
    def get_data_id_attr(self, extra=None):
        if extra is not None:
            s = '{}_{}'.format(self.get_data_id(), extra)
        else:
            s = self.get_data_id()
        return {self.sofi_data_id_key:s}
    def get_selector(self, extra='', **kwargs):
        obj = kwargs.get('obj', self)
        if isinstance(obj, Element):
            if obj.attrs and self.sofi_data_id_key in obj.attrs:
                kwargs.setdefault('data_id', obj.attrs[self.sofi_data_id_key])
        data_id = kwargs.get('data_id', self.get_data_id())
        return "[{}='{}{}']".format(self.sofi_data_id_key, data_id, extra)

class InlineTextEdit(SofiDataId):
    label_text = Property()
    initial = Property()
    value = Property()
    input_type = Property('text')
    hidden = Property(True)
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.label_text = kwargs.get('label', '')
        self.initial = kwargs.get('initial', '')
        self.hidden = kwargs.get('hidden', True)
        self.input_type = kwargs.get('input_type', 'text')
        if self.hidden:
            cl = 'panel hidden'
        else:
            cl = 'panel'
        self.widget = Div(cl=cl, attrs=self.get_data_id_attr())
        body = Div(cl='panel-body')

        grp = Div(cl='input-group')
        self.label_widget = Span(
            text=self.label_text,
            cl='input-group-addon',
            attrs=self.get_data_id_attr('label'),
        )
        attrs = self.get_data_id_attr('input')
        attrs['value'] = self.initial
        self.input_widget = Input(
            inputtype=self.input_type,
            attrs=attrs,
        )
        grp.addelement(self.label_widget)
        grp.addelement(self.input_widget)
        body.addelement(grp)

        btngrp = ButtonGroup()
        self.ok_btn = Button(text='Ok', cl='text-edit-btn', severity='primary', attrs=self.get_data_id_attr('ok'))
        self.cancel_btn = Button(text='Cancel', cl='text-edit-btn', attrs=self.get_data_id_attr('cancel'))
        btngrp.addelement(self.ok_btn)
        btngrp.addelement(self.cancel_btn)
        body.addelement(btngrp)

        self.widget.addelement(body)

        self.bind(
            label_text=self.on_label_text,
            initial=self.on_initial,
            hidden=self.on_hidden,
        )
        self.app.register('load', self.on_app_load)
    async def on_app_load(self, *args):
        self.app.register('click', self.on_btn_click, '.text-edit-btn')
    async def on_btn_click(self, e):
        data_id = e['event_object']['target'].get('data-sofi-id')
        if not data_id:
            return
        data_id = data_id.split('_')
        if data_id[0] != self.get_data_id():
            return
        selector = self.get_selector(obj=self.input_widget)
        if data_id[1] == 'ok':
            self.value = await self.app.get_property(selector, 'value')
        elif data_id[1] == 'cancel':
            self.input_widget.attrs['value'] = self.initial
            self.app.property(selector, 'value', self.initial)
        self.hidden = True
    def on_label_text(self, instance, value, **kwargs):
        selector = self.get_selector(obj=self.label_widget)
        self.app.text(selector, value)
    def on_initial(self, instance, value, **kwargs):
        if self.input_widget.attrs['value'] == value:
            return
        self.input_widget.attrs['value'] = value
        selector = self.get_selector(obj=self.input_widget)
        self.app.attr(selector, 'value', value)
    def on_hidden(self, instance, value, **kwargs):
        if value:
            self.app.addclass(self.get_selector(), 'hidden')
        else:
            self.app.removeclass(self.get_selector(), 'hidden')

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
            btn = Button(text=lbl, severity=severity, attrs=self.get_data_id_attr(i))
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
            selector = self.get_selector(obj=btn)
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
            selector = self.get_selector(obj=btn)
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
    edit_enable = Property(False)
    edit_preset = Property()
    preset_buttons = ListProperty()
    num_presets = 8
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.vidhub = kwargs.get('vidhub')
        self.widget = Container(attrs=self.get_data_id_attr())
        h = Heading(text='Presets')
        self.widget.addelement(h)
        row = Row()
        col = Column(count=12)
        btngrp = ButtonGroup(justified=True)
        for i in range(self.num_presets):
            try:
                preset = self.vidhub.presets[i]
                preset.bind(name=self.on_preset_name)
                name = preset.name
                active = preset.active
            except IndexError:
                name = str(i+1)
                active = False
            attrs = self.get_data_id_attr(i)
            if active:
                severity = 'primary'
            else:
                severity = 'default'
            btn = Button(text=name, cl='preset-btn', severity=severity, attrs=attrs)
            btngrp.addelement(btn)
            self.preset_buttons.append(btn)
        col.addelement(btngrp)
        row.addelement(col)
        self.widget.addelement(row)

        row = Row()
        col = Column(count=4)
        btngrp = ButtonGroup()
        self.edit_enable_btn = Button(text='Edit Name', attrs=self.get_data_id_attr('edit'))
        self.record_enable_btn = Button(text='Record', attrs=self.get_data_id_attr('record'))
        btngrp.addelement(self.edit_enable_btn)
        btngrp.addelement(self.record_enable_btn)
        col.addelement(btngrp)
        row.addelement(col)

        col = Column(count=4)
        self.edit_widget = InlineTextEdit(app=self.app)
        self.edit_widget.bind(value=self.on_edit_widget_value)
        col.addelement(self.edit_widget.widget)
        row.addelement(col)

        self.widget.addelement(row)

        self.bind(
            edit_enable=self.on_edit_enable,
            record_enable=self.on_record_enable,
        )
        self.vidhub.bind(
            on_preset_added=self.on_preset_added,
            on_preset_active=self.on_preset_active,
        )
    def remove(self):
        for preset in self.vidhub.presets:
            preset.unbind(self)
        super().remove()
    def on_edit_enable(self, instance, value, **kwargs):
        selector = self.get_selector(obj=self.edit_enable_btn)
        if value:
            self.record_enable = False
            self.app.removeclass(selector, 'btn-default')
            self.app.addclass(selector, 'btn-primary')
        else:
            self.app.removeclass(selector, 'btn-primary')
            self.app.addclass(selector, 'btn-default')
    def on_record_enable(self, instance, value, **kwargs):
        selector = self.get_selector(obj=self.record_enable_btn)
        if value:
            self.edit_enable = False
            self.app.addclass(selector, 'btn-danger')
        else:
            self.app.removeclass(selector, 'btn-danger')
    def on_edit_widget_value(self, instance, value, **kwargs):
        if not self.edit_enable:
            return
        if not self.edit_preset:
            return
        self.edit_enable = False
        preset = self.edit_preset
        self.edit_preset = None
        preset.name = value
    def on_preset_added(self, *args, **kwargs):
        preset = kwargs.get('preset')
        try:
            btn = self.preset_buttons[preset.index]
        except IndexError:
            return
        selector = self.get_selector(obj=btn)
        self.app.text(selector, preset.name)
        preset.bind(name=self.on_preset_name)
    def on_preset_name(self, instance, value, **kwargs):
        try:
            btn = self.preset_buttons[instance.index]
        except IndexError:
            return
        selector = self.get_selector(obj=btn)
        self.app.text(selector, value)
    def on_preset_active(self, *args, **kwargs):
        preset = kwargs.get('preset')
        try:
            btn = self.preset_buttons[preset.index]
        except IndexError:
            return
        selector = self.get_selector(obj=btn)
        if preset.active:
            self.app.removeclass(selector, 'btn-default')
            self.app.addclass(selector, 'btn-primary')
        else:
            self.app.removeclass(selector, 'btn-primary')
            self.app.addclass(selector, 'btn-default')
    async def on_click(self, data_id):
        data_id = data_id.split('_')
        if data_id[0] != self.get_data_id():
            return
        if data_id[1] == 'edit':
            self.edit_enable = not self.edit_enable
            return
        if data_id[1] == 'record':
            self.record_enable = not self.record_enable
            return
        i = int(data_id[1])
        if self.edit_enable:
            try:
                preset = self.vidhub.presets[i]
            except IndexError:
                preset = None
            if preset is None:
                return
            self.edit_preset = preset
            self.edit_widget.initial = preset.name
            self.edit_widget.hidden = False
        elif self.record_enable:
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
        self.connection_icon = None
        self.connection_btn = None
        self.bind(vidhub=self.on_vidhub)
        self.vidhub = kwargs.get('vidhub')
    def on_vidhub(self, instance, value, **kwargs):
        old = kwargs.get('old')
        if old is not None:
            old.unbind(self)
        for attr in ['input_buttons', 'output_buttons', 'preset_buttons']:
            obj = getattr(self, attr)
            if obj is not None:
                obj.remove()
            setattr(self, attr, None)
        del self.widget._children[:]
        self.connection_icon = None
        self.connection_btn = None
        if self.vidhub is not None:
            self.vidhub.bind(connected=self.on_vidhub_connected)
            self.build_view()
    def on_vidhub_connected(self, instance, value, **kwargs):
        if self.connection_icon is None:
            return
        states = {True:'glyphicon glyphicon-ok-circle', False:'glyphicon glyphicon-ban-circle'}
        self.connection_icon.cl = states[value]

        states = {True:'btn btn-success', False:'btn btn-warning'}
        self.connection_btn._children[0] = 'Connect ' if not value else 'Disconnect '

        selector = '#{}'.format(self.connection_btn.ident)
        self.app.removeclass(selector, states[not value])
        self.app.addclass(selector, states[value])
        self.app.replace(selector, ''.join([str(c) for c in self.connection_btn._children]))

    def build_view(self):
        self.input_buttons = InputButtons(vidhub_view=self, vidhub=self.vidhub, app=self.app)
        self.output_buttons = OutputButtons(vidhub_view=self, vidhub=self.vidhub, app=self.app)
        self.preset_buttons = PresetButtons(vidhub=self.vidhub, app=self.app)

        row = Row()
        col = Column(count=4)
        h = PageHeader(text=str(self.vidhub.device_id))
        col.addelement(h)
        row.addelement(col)

        col = Column(count=4, ident='connection_container')
        if self.vidhub.connected:
            cl = 'glyphicon glyphicon-ok-circle'
        else:
            cl = 'glyphicon glyphicon-ban-circle'
        ico = self.connection_icon = Span(cl=cl, ident='connection_icon', attrs={'aria-hidden':'true'})
        btn = self.connection_btn = Button(
            severity='warning' if not self.vidhub.connected else 'success',
            ident='connection_btn',
        )
        btn._parent = col
        btn._children.append('Connect ' if not self.vidhub.connected else 'Disconnect ')
        btn.addelement(ico)
        col.addelement(btn)
        row.addelement(col)
        self.widget.addelement(row)

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
            self.app.replace(self.get_selector(), str(self.widget))
    async def on_click(self, e):
        ident = e['event_object']['target'].get('id')
        if self.connection_btn is not None and ident == self.connection_btn.ident:
            if self.vidhub is None:
                return
            if self.vidhub.connected:
                await self.vidhub.disconnect()
            else:
                await self.vidhub.connect()
            return
        data_id = e['event_object']['target'].get('data-sofi-id')
        if data_id is None:
            return
        logger.info(data_id)
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
        await self.vidhub_view.on_click(e)

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
