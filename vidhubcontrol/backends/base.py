import asyncio

from pydispatch import Dispatcher, Property
from pydispatch.properties import ListProperty, DictProperty


class BackendBase(Dispatcher):
    device_name = Property()
    device_model = Property()
    device_id = Property()
    device_version = Property()
    connected = Property(False)
    connection_error = Property(False)
    exception_type = Property(None)
    exception_info = Property(None)
    connection_unavailable = Property(False)
    running = Property(False)
    prelude_parsed = Property(False)
    def __init__(self, **kwargs):
        self.device_name = kwargs.get('device_name')
        self.client = None
        self.event_loop = kwargs.get('event_loop', asyncio.get_event_loop())
        self.bind(device_id=self.on_device_id)
        if self.device_id is None:
            self.device_id = kwargs.get('device_id')
    @classmethod
    async def create_async(cls, **kwargs):
        obj = cls(**kwargs)
        await obj.connect_fut
        return obj
    async def connect(self):
        if self.connected:
            return self.client
        self.connected = True
        r = await self.do_connect()
        if r is False:
            self.connection_error = True
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
    def _catch_exception(self, e):
        self.exception_type = e.__class__
        try:
            self.exception_info = e.args
        except:
            self.exception_info = str(e)
        self.connection_error = True
    async def do_connect(self):
        raise NotImplementedError()
    async def do_disconnect(self):
        raise NotImplementedError()
    async def get_status(self):
        raise NotImplementedError()
    def on_device_id(self, instance, value, **kwargs):
        if value is None:
            return
        if self.device_name is None:
            self.device_name = value
        self.unbind(self.on_device_id)

class VidhubBackendBase(BackendBase):
    crosspoints = ListProperty()
    output_labels = ListProperty()
    input_labels = ListProperty()
    crosspoint_control = ListProperty()
    output_label_control = ListProperty()
    input_label_control = ListProperty()
    presets = ListProperty()
    num_outputs = Property(0)
    num_inputs = Property(0)
    device_type = 'vidhub'
    feedback_prop_map = {
        'crosspoints':'crosspoint_control',
        'input_labels':'input_label_control',
        'output_labels':'output_label_control',
    }
    _events_ = ['on_preset_added', 'on_preset_stored', 'on_preset_active']
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
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
        self.connect_fut = asyncio.ensure_future(self.connect(), loop=self.event_loop)
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
        if index is None:
            preset = await self.add_preset()
        else:
            while True:
                try:
                    preset = self.presets[index]
                except IndexError:
                    preset = None
                if preset is not None:
                    break
                preset = await self.add_preset()
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
        if prop.name not in self.feedback_prop_map:
            return
        elock = self.emission_lock(prop.name)
        control_prop = self.feedback_prop_map[prop.name]
        setattr(self, control_prop, value[:])
    def on_prop_control(self, instance, value, **kwargs):
        if not self.connected:
            return
        if not self.prelude_parsed:
            return
        prop = kwargs.get('property')
        keys = kwargs.get('keys')
        if keys is None:
            keys = range(len(value))
        feedback_prop = '{}s'.format(prop.name.split('_control')[0])
        elock = self.emission_lock(feedback_prop)
        if elock.held or elock.aio_lock.locked():
            return
        if value == getattr(self, feedback_prop):
            return
        coro_name = '_'.join(['set', feedback_prop])
        coro = getattr(self, coro_name)
        args = [(key, value[key]) for key in keys]
        tx_fut = asyncio.run_coroutine_threadsafe(coro(*args), loop=self.event_loop)

class SmartViewBackendBase(BackendBase):
    num_monitors = Property()
    inverted = Property(False)
    monitors = ListProperty()
    monitor_cls = None
    device_type = 'smartview'
    _events_ = ['on_monitor_property_change']
    def __init__(self, **kwargs):
        self.bind(monitors=self._on_monitors)
        super().__init__(**kwargs)
        self.connect_fut = asyncio.ensure_future(self.connect(), loop=self.event_loop)
    async def set_monitor_property(self, monitor, name, value):
        raise NotImplementedError()
    def get_monitor_cls(self):
        cls = self.monitor_cls
        if cls is None:
            cls = SmartViewMonitor
        return cls
    async def add_monitor(self, **kwargs):
        cls = self.get_monitor_cls()
        kwargs.setdefault('parent', self)
        kwargs.setdefault('index', len(self.monitors))
        monitor = cls(**kwargs)
        monitor.bind(on_property_change=self.on_monitor_prop)
        self.monitors.append(monitor)
        return monitor
    def on_monitor_prop(self, instance, name, value, **kwargs):
        kwargs['monitor'] = instance
        self.emit('on_monitor_property_change', self, name, value, **kwargs)
    def _on_monitors(self, *args, **kwargs):
        self.num_monitors = len(self.monitors)

class SmartScopeBackendBase(SmartViewBackendBase):
    device_type = 'smartscope'
    def get_monitor_cls(self):
        cls = self.monitor_cls
        if cls is None:
            cls = SmartScopeMonitor
        return cls

MONITOR_PROPERTY_MAP = {k:k.title() for k in [
    'brightness', 'contrast', 'saturation', 'identify', 'border']}
MONITOR_PROPERTY_MAP.update({
    'widescreen_sd':'WidescreenSD',
    'audio_channel':'AudioChannel',
    'scope_mode':'ScopeMode',
})

class SmartViewMonitor(Dispatcher):
    index = Property()
    name = Property()
    brightness = Property()
    contrast = Property()
    saturation = Property()
    widescreen_sd = Property()
    identify = Property(False)
    border = Property()
    audio_channel = Property()
    class PropertyChoices():
        widescreen_sd = {
            True:'ON',
            False:'OFF',
            None:'auto',
        }
        border = {
            'red':'red',
            'green':'green',
            'blue':'blue',
            'white':'white',
            None:'NONE',
        }
        identify = {
            True:'true',
            False:'false',
        }
        _bind_properties = [
            'brightness', 'contrast', 'saturation',
            'widescreen_sd', 'identify', 'border', 'audio_channel',
        ]
    _events_ = ['on_property_change']
    def __init__(self, **kwargs):
        self._property_locks = {}
        self.parent = kwargs.get('parent')
        self.event_loop = self.parent.event_loop
        self.index = kwargs.get('index')
        self.name = kwargs.get('name')
        props = self.PropertyChoices._bind_properties
        for prop in props:
            value = kwargs.get(prop)
            value = self.get_property_for_choice(prop, value)
            setattr(self, prop, value)
        self.bind(**{prop:self.on_prop_control for prop in props})
    def _get_property_lock(self, name):
        lock = self._property_locks.get(name)
        if lock is None:
            lock = asyncio.Lock()
            self._property_locks[name] = lock
        return lock
    async def set_property_from_backend(self, name, value):
        value = self.get_property_for_choice(name, value)
        lock = self._get_property_lock(name)
        async with lock:
            setattr(self, name, value)
        self.emit('on_property_change', self, name, value)
    async def set_property(self, name, value):
        await self.parent.set_monitor_property(self, name, value)
    async def flash(self):
        await self.set_property('identify', True)
    def get_property_choices(self, name):
        return getattr(self.PropertyChoices, name, None)
    def get_choice_for_property(self, name, value):
        choices = self.get_property_choices(name)
        if choices is not None:
            if value in choices:
                value = choices[value]
        return value
    def get_property_for_choice(self, name, value):
        choices = self.get_property_choices(name)
        if choices is not None:
            if value in choices.values():
                for k, v in choices.items():
                    if v == value:
                        value = k
                        break
        if isinstance(value, str) and value.lower() in ('none', 'true', 'false'):
            if value.lower() == 'none':
                value = None
            else:
                value = value.lower() == 'true'
        return value
    def on_prop_control(self, instance, value, **kwargs):
        prop = kwargs.get('property')
        lock = self._get_property_lock(prop.name)
        if lock.locked():
            return
        value = self.get_choice_for_property(prop.name, value)
        fut = self.set_property(prop.name, value)
        asyncio.run_coroutine_threadsafe(fut, loop=self.event_loop)


class SmartScopeMonitor(SmartViewMonitor):
    scope_mode = Property()
    class PropertyChoices(SmartViewMonitor.PropertyChoices):
        scope_mode = {
            'audio_dbfs':'AudioDbfs',
            'audio_dbvu':'AudioDbvu',
            'histogram':'Histogram',
            'parade_rgb':'ParadeRGB',
            'parade_yuv':'ParadeYUV',
            'video':'Picture',
            'vector_100':'Vector100',
            'vector_75':'Vector75',
            'waveform':'WaveformLuma',
        }
        _bind_properties = SmartViewMonitor.PropertyChoices._bind_properties + [
            'scope_mode',
        ]


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
        self.bind(crosspoints=self.on_preset_crosspoints)
    async def store(self, outputs_to_store=None, clear_current=True):
        if outputs_to_store is None:
            outputs_to_store = range(self.backend.num_outputs)
        if clear_current:
            self.crosspoints = {}
        async with self.emission_lock('crosspoints'):
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
    def on_preset_crosspoints(self, instance, value, **kwargs):
        if not len(self.crosspoints) or not self.backend.prelude_parsed:
            return
        self.check_active()
