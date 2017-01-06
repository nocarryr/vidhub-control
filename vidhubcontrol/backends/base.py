import asyncio

from pydispatch import Dispatcher, Property
from pydispatch.properties import ListProperty, DictProperty

class BackendBase(Dispatcher):
    crosspoints = ListProperty()
    output_labels = ListProperty()
    input_labels = ListProperty()
    crosspoint_control = ListProperty()
    output_label_control = ListProperty()
    input_label_control = ListProperty()
    presets = ListProperty()
    device_model = Property()
    device_id = Property()
    device_version = Property()
    num_outputs = Property(0)
    num_inputs = Property(0)
    connected = Property(False)
    running = Property(False)
    prelude_parsed = Property(False)
    _events_ = ['on_preset_added', 'on_preset_stored', 'on_preset_active']
    def __init__(self, **kwargs):
        self.client = None
        self.event_loop = kwargs.get('event_loop', asyncio.get_event_loop())
        self.bind(
            num_outputs=self.on_num_outputs,
            num_inputs=self.on_num_inputs,
            output_labels=self.on_prop_feedback,
            input_labels=self.on_prop_feedback,
            crosspoints=self.on_prop_feedback,
            output_label_control=self.on_prop_control,
            input_label_control=self.on_prop_control,
            crosspoint_control=self.on_prop_control,
        )
        presets = kwargs.get('presets', [])
        for pst_data in presets:
            pst_data['backend'] = self
            preset = Preset(**pst_data)
            self.presets.append(preset)
            preset.bind(
                on_preset_stored=self.on_preset_stored,
                active=self.on_preset_active,
            )
        asyncio.ensure_future(self.connect(), loop=self.event_loop)
    async def connect(self):
        if self.connected:
            return self.client
        self.connected = True
        r = await self.do_connect()
        if r is False:
            self.connected = False
        else:
            if self.client is not None:
                self.client = r
        return r
    async def disconnect(self):
        if not self.connected:
            return
        await self.do_disconnect()
        self.client = None
        self.connected = False
    async def do_connect(self):
        raise NotImplementedError()
    async def do_disconnect(self):
        raise NotImplementedError()
    async def get_status(self):
        raise NotImplementedError()
    async def set_crosspoint(self, out_idx, in_idx):
        raise NotImplementedError()
    async def set_crosspoints(self, *args):
        raise NotImplementedError()
    async def set_output_label(self, out_idx, label):
        raise NotImplementedError()
    async def set_output_labels(self, *args):
        raise NotImplementedError()
    async def set_input_label(self, in_idx, label):
        raise NotImplementedError()
    async def set_input_labels(self, *args):
        raise NotImplementedError()
    async def add_preset(self, name=None):
        index = len(self.presets)
        preset = Preset(backend=self, name=name, index=index)
        self.presets.append(preset)
        preset.bind(
            on_preset_stored=self.on_preset_stored,
            active=self.on_preset_active,
        )
        self.emit('on_preset_added', backend=self, preset=preset)
        return preset
    async def store_preset(self, outputs_to_store=None, name=None, index=None, clear_current=True):
        if index is not None:
            while True:
                try:
                    preset = self.presets[index]
                except IndexError:
                    preset = None
                if preset is not None:
                    break
                await self.add_preset()
        if name is not None:
            preset.name = name
        await preset.store(outputs_to_store, clear_current)
        return preset
    def on_preset_stored(self, *args, **kwargs):
        kwargs['backend'] = self
        self.emit('on_preset_stored', *args, **kwargs)
    def on_preset_active(self, instance, value, **kwargs):
        self.emit('on_preset_active', backend=self, preset=instance, value=value)
    def on_num_outputs(self, instance, value, **kwargs):
        if value == len(self.output_labels):
            return
        if value != len(self.crosspoints):
            self.crosspoints = [0] * value
        self.output_labels = [''] * value
    def on_num_inputs(self, instance, value, **kwargs):
        if value == len(self.input_labels):
            return
        if value != len(self.crosspoints):
            self.crosspoints = [0] * value
        self.input_labels = [''] * value
    def on_prop_feedback(self, instance, value, **kwargs):
        prop = kwargs.get('property')
        if prop.name == 'crosspoints':
            self.crosspoint_control = value[:]
        elif prop.name == 'output_labels':
            self.output_label_control = value[:]
        elif prop.name == 'input_labels':
            self.input_label_control = value[:]
    def on_prop_control(self, instance, value, **kwargs):
        if not self.connected:
            return
        if not self.prelude_parsed:
            return
        prop = kwargs.get('property')
        keys = kwargs.get('keys')
        if keys is None:
            return
        coro = None
        args = [(key, value[key]) for key in keys]
        if prop.name == 'crosspoint_control':
            coro = self.set_crosspoints
        elif prop.name == 'output_label_control':
            coro = self.set_output_labels
        elif prop.name == 'input_label_control':
            coro = self.set_input_labels
        if coro is not None:
            tx_fut = asyncio.run_coroutine_threadsafe(coro(*args), loop=self.event_loop)

class Preset(Dispatcher):
    name = Property()
    index = Property()
    crosspoints = DictProperty()
    active = Property(False)
    _events_ = ['on_preset_stored']
    def __init__(self, **kwargs):
        self.backend = kwargs.get('backend')
        self.index = kwargs.get('index')
        name = kwargs.get('name')
        if name is None:
            name = 'Preset {}'.format(self.index + 1)
        self.name = name
        self.crosspoints = kwargs.get('crosspoints', {})
        if self.backend.connected and self.backend.prelude_parsed:
            self.check_active()
        else:
            self.backend.bind(prelude_parsed=self.on_backend_ready)
        self.backend.bind(crosspoints=self.on_backend_crosspoints)
    async def store(self, outputs_to_store=None, clear_current=True):
        if outputs_to_store is None:
            outputs_to_store = range(self.backend.num_outputs)
        if clear_current:
            self.crosspoints = {}
        for out_idx in outputs_to_store:
            self.crosspoints[out_idx] = self.backend.crosspoints[out_idx]
        self.active = True
        self.emit('on_preset_stored', preset=self)
    async def recall(self):
        if not len(self.crosspoints):
            return
        args = [(i, v) for i, v in self.crosspoints.items()]
        await self.backend.set_crosspoints(*args)
    def check_active(self):
        if not len(self.crosspoints):
            self.active = False
            return
        for out_idx, in_idx in self.crosspoints.items():
            in_idx = self.crosspoints[out_idx]
            if self.backend.crosspoints[out_idx] != in_idx:
                self.active = False
                return
        self.active = True
    def on_backend_ready(self, instance, value, **kwargs):
        if not value:
            return
        self.backend.unbind(self.on_backend_ready)
        self.check_active()
    def on_backend_crosspoints(self, instance, value, **kwargs):
        if not self.backend.prelude_parsed:
            return
        self.check_active()
