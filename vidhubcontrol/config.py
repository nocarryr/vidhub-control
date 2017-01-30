import os
import json
import asyncio

import jsonfactory
from pydispatch import Dispatcher, Property
from pydispatch.properties import ListProperty, DictProperty

from vidhubcontrol.discovery import BMDDiscovery
from vidhubcontrol.backends.dummy import DummyBackend
from vidhubcontrol.backends.telnet import TelnetBackend

BACKENDS = {cls.__name__:cls for cls in [DummyBackend, TelnetBackend]}

DEFAULT_FILENAME = '~/vidhubcontrol.json'

class ConfigBase(Dispatcher):
    _conf_attrs = []
    _events_ = ['trigger_save']
    def _get_conf_data(self):
        d = {}
        for attr in self._conf_attrs:
            val = getattr(self, attr)
            if isinstance(val, ConfigBase):
                val = val._get_conf_data()
            d[attr] = val
        return d

class Config(ConfigBase):
    USE_DISCOVERY = True
    vidhubs = DictProperty()
    _conf_attrs = ['vidhubs']
    def __init__(self, **kwargs):
        self.running = asyncio.Event()
        self.stopped = asyncio.Event()
        self.filename = kwargs.get('filename', DEFAULT_FILENAME)
        self.loop = kwargs.get('loop', asyncio.get_event_loop())
        vidhubs = kwargs.get('vidhubs', {})
        for vidhub_data in vidhubs.values():
            vidhub = VidhubConfig(**vidhub_data)
            self.vidhubs[vidhub.device_id] = vidhub
            vidhub.bind(trigger_save=self.on_vidhub_trigger_save)
        self.discovery_listener = None
        self.discovery_lock = asyncio.Lock()
        if self.USE_DISCOVERY:
            asyncio.ensure_future(self.start(), loop=self.loop)
    async def start(self):
        if not self.USE_DISCOVERY:
            return
        self.discovery_listener = BMDDiscovery(self.loop)
        self.discovery_listener.bind(
            service_added=self.on_discovery_service_added,
        )
        await self.discovery_listener.start()
        self.running.set()
    async def stop(self):
        self.running.clear()
        if self.discovery_listener is None:
            return
        await self.discovery_listener.stop()
        self.discovery_listener = None
        for vidhub in self.vidhubs.values():
            await vidhub.disconnect()
        self.stopped.set()
    def build_backend(self, backend_name, **kwargs):
        for vidhub in self.vidhubs.values():
            if vidhub.backend_name != backend_name:
                continue
            if kwargs.get('device_id') is not None and kwargs['device_id'] == vidhub.device_id:
                return vidhub.backend
            if kwargs.get('hostaddr') is not None and kwargs['hostaddr'] == vidhub.hostaddr:
                return vidhub.backend
        cls = BACKENDS[backend_name]
        backend = cls(**kwargs)
        self.add_vidhub(backend)
        return backend
    def add_vidhub(self, backend):
        device_id = backend.device_id
        if device_id is None:
            backend.bind(device_id=self.on_backend_device_id)
            device_id = id(backend)
        vidhub = VidhubConfig.from_existing(backend)
        self.vidhubs[device_id] = vidhub
        vidhub.bind(trigger_save=self.on_vidhub_trigger_save)
        self.save()
    def on_backend_device_id(self, backend, value, **kwargs):
        if value is None:
            return
        backend.unbind(self.on_backend_device_id)
        vidhub = self.vidhubs[id(backend)]
        vidhub.device_id = value
        del self.vidhubs[id(backend)]
        if value in self.vidhubs:
            self.save()
            return
        self.vidhubs[value] = vidhub
        self.save()
    async def add_discovered_vidhub(self, info, device_id):
        async with self.discovery_lock:
            if device_id in self.vidhubs:
                return
            addr = str(info.address)
            backend = await TelnetBackend.create_async(
                hostaddr=addr,
                hostport=int(info.port),
                event_loop=self.loop,
            )
            if backend is None:
                return
            if backend.device_id != device_id:
                await backend.disconect()
                return
            self.add_vidhub(backend)
    def on_discovery_service_added(self, info, **kwargs):
        if kwargs.get('class') != 'Videohub':
            return
        device_id = kwargs.get('id')
        if device_id is None:
            return
        if device_id in self.vidhubs:
            return
        asyncio.ensure_future(self.add_discovered_vidhub(info, device_id))
    def on_vidhub_trigger_save(self, *args, **kwargs):
        self.save()
    def save(self, filename=None):
        if filename is not None:
            self.filename = filename
        else:
            filename = self.filename
        filename = os.path.expanduser(filename)
        data = self._get_conf_data()
        if not os.path.exists(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
        s = jsonfactory.dumps(data, indent=4)
        with open(filename, 'w') as f:
            f.write(s)
    @classmethod
    def load(cls, filename=None, **kwargs):
        if filename is None:
            filename = DEFAULT_FILENAME
        kwargs['filename'] = filename
        filename = os.path.expanduser(filename)
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                s = f.read()
            kwargs.update(jsonfactory.loads(s))
        return cls(**kwargs)

class VidhubConfig(ConfigBase):
    backend = Property()
    backend_name = Property()
    hostaddr = Property()
    hostport = Property(9990)
    device_name = Property()
    device_id = Property()
    presets = ListProperty()
    _conf_attrs = [
        'backend_name',
        'hostaddr',
        'hostport',
        'device_name',
        'device_id',
        'presets',
    ]
    def __init__(self, **kwargs):
        for attr in self._conf_attrs:
            setattr(self, attr, kwargs.get(attr))
        if self.presets is None:
            self.presets = []
        self.backend = kwargs.get('backend')
        if self.backend is None:
            bcls = BACKENDS[self.backend_name]
            bkwargs = self._get_conf_data()
            bkwargs['presets'] = bkwargs['presets'][:]
            self.backend = bcls(**bkwargs)
        pkwargs = {k:self.on_preset_update for k in ['name', 'crosspoints']}
        for preset in self.backend.presets:
            preset.bind(**pkwargs)
        if self.backend.device_name != self.device_name:
            self.device_name = self.backend.device_name
        self.backend.bind(
            device_name=self.on_backend_prop_change,
            on_preset_added=self.on_preset_added,
        )
        if hasattr(self.backend, 'hostport'):
            self.backend.bind(
                hostaddr=self.on_backend_prop_change,
                hostport=self.on_backend_prop_change,
            )
    @classmethod
    def from_existing(cls, backend):
        kwargs = dict(
            backend=backend,
            backend_name=backend.__class__.__name__,
            hostaddr=getattr(backend, 'hostaddr', None),
            hostport=getattr(backend, 'hostport', None),
            device_name=backend.device_name,
            device_id=backend.device_id,
            presets=[],
        )
        for preset in backend.presets:
            kwargs['presets'].append(dict(
                name=preset.name,
                index=preset.index,
                crosspoints=preset.crosspoints.copy(),
            ))
        return cls(**kwargs)
    def on_preset_added(self, *args, **kwargs):
        preset = kwargs.get('preset')
        self.presets.append(dict(
            name=preset.name,
            index=preset.index,
            crosspoints=preset.crosspoints.copy(),
        ))
        bkwargs = {k:self.on_preset_update for k in ['name', 'crosspoints']}
        self.emit('trigger_save')
        preset.bind(**bkwargs)
    def on_preset_update(self, instance, value, **kwargs):
        prop = kwargs.get('property')
        if prop.name == 'crosspoints':
            value = value.copy()
        self.presets[instance.index][prop.name] = value
        self.emit('trigger_save')
    def on_backend_prop_change(self, instance, value, **kwargs):
        prop = kwargs.get('property')
        setattr(self, prop.name, value)
        self.emit('trigger_save')
    def _get_conf_data(self):
        d = super()._get_conf_data()
        for pdata in d['presets']:
            if 'backend' in pdata:
                del pdata['backend']
        return d

@jsonfactory.register
class JsonHandler(object):
    def encode(self, o):
        if isinstance(o, ConfigBase):
            d = o._get_conf_data()
            return d
    def decode(self, d):
        keys = [key for key in d if key.isdigit()]
        if len(keys) == len(d.keys()):
            return {int(key):d[key] for key in d.keys()}
        return d
