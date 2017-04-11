import os
import json
import asyncio

import jsonfactory
from pydispatch import Dispatcher, Property
from pydispatch.properties import ListProperty, DictProperty

from vidhubcontrol.discovery import BMDDiscovery
from vidhubcontrol.backends import (
    DummyBackend,
    SmartViewDummyBackend,
    SmartScopeDummyBackend,
    TelnetBackend,
    SmartScopeTelnetBackend,
)

BACKENDS = {
    'vidhub':{cls.__name__:cls for cls in [DummyBackend, TelnetBackend]},
    'smartview':{cls.__name__:cls for cls in [SmartViewDummyBackend]},
    'smartscope':{cls.__name__:cls for cls in [SmartScopeDummyBackend, SmartScopeTelnetBackend]},
}

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
    DEFAULT_FILENAME = '~/vidhubcontrol.json'
    USE_DISCOVERY = True
    vidhubs = DictProperty()
    smartviews = DictProperty()
    smartscopes = DictProperty()
    _conf_attrs = ['vidhubs', 'smartscopes', 'smartviews']
    _device_type_map = {
        'vidhub':{'prop':'vidhubs'},
        'smartview':{'prop':'smartviews'},
        'smartscope':{'prop':'smartscopes'},
    }
    def __init__(self, **kwargs):
        self.running = asyncio.Event()
        self.stopped = asyncio.Event()
        self.filename = kwargs.get('filename', self.DEFAULT_FILENAME)
        self.loop = kwargs.get('loop', asyncio.get_event_loop())
        for key, d in self._device_type_map.items():
            items = kwargs.get(d['prop'], {})
            prop = getattr(self, d['prop'])
            for item_data in items.values():
                obj = d['cls'](**item_data)
                device_id = obj.device_id
                if device_id is None:
                    device_id = str(id(obj.backend))
                prop[device_id] = obj
                obj.backend.bind(device_id=self.on_backend_device_id)
                obj.bind(trigger_save=self.on_device_trigger_save)
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
            await vidhub.backend.disconnect()
        for smartview in self.smartviews.values():
            await smartview.backend.disconnect()
        for smartscope in self.smartscopes.values():
            await smartscope.backend.disconnect()
        self.stopped.set()
    def build_backend(self, device_type, backend_name, **kwargs):
        prop = getattr(self, self._device_type_map[device_type]['prop'])
        for obj in prop.values():
            if obj.backend_name != backend_name:
                continue
            if kwargs.get('device_id') is not None and kwargs['device_id'] == obj.device_id:
                return obj.backend
            if kwargs.get('hostaddr') is not None and kwargs['hostaddr'] == obj.hostaddr:
                return obj.backend
        cls = BACKENDS[device_type][backend_name]
        kwargs['event_loop'] = self.loop
        backend = cls(**kwargs)
        self.add_device(backend)
        return backend
    def add_vidhub(self, backend):
        return self.add_device(backend)
    def add_smartview(self, backend):
        return self.add_device(backend)
    def add_smartscope(self, backend):
        return self.add_device(backend)
    def add_device(self, backend):
        device_type = backend.device_type
        device_id = backend.device_id
        if device_id is None:
            device_id = str(id(backend))
        cls = self._device_type_map[device_type]['cls']
        prop = getattr(self, self._device_type_map[device_type]['prop'])
        obj = cls.from_existing(backend)
        prop[device_id] = obj
        obj.bind(trigger_save=self.on_device_trigger_save)
        backend.bind(device_id=self.on_backend_device_id)
        self.save()
    def on_backend_device_id(self, backend, value, **kwargs):
        if value is None:
            return
        prop = getattr(self, self._device_type_map[backend.device_type]['prop'])
        obj = prop[str(id(backend))]
        obj.device_id = value
        del prop[str(id(backend))]
        if value in prop:
            self.save()
            return
        prop[value] = obj
        self.save()
    async def add_discovered_device(self, device_type, info, device_id):
        async with self.discovery_lock:
            prop = getattr(self, self._device_type_map[device_type]['prop'])
            cls = None
            for key, _cls in BACKENDS[device_type].items():
                if 'Telnet' in key:
                    cls = _cls
                    break
            if device_id in prop:
                return
            addr = str(info.address)
            backend = await cls.create_async(
                hostaddr=addr,
                hostport=int(info.port),
                event_loop=self.loop,
            )
            if backend is None:
                return
            if backend.device_id != device_id:
                await backend.disconnect()
                return
            self.add_device(backend)
    def on_discovery_service_added(self, info, **kwargs):
        if kwargs.get('class') not in ['Videohub', 'SmartView']:
            return
        device_type = kwargs.get('device_type')
        device_id = kwargs.get('id')
        if device_id is None:
            return
        prop = getattr(self, self._device_type_map[device_type]['prop'])
        if device_id in prop:
            return
        asyncio.ensure_future(self.add_discovered_device(device_type, info, device_id))
    def on_device_trigger_save(self, *args, **kwargs):
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
            filename = cls.DEFAULT_FILENAME
        kwargs['filename'] = filename
        filename = os.path.expanduser(filename)
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                s = f.read()
            kwargs.update(jsonfactory.loads(s))
        return cls(**kwargs)

class DeviceConfigBase(ConfigBase):
    backend = Property()
    backend_name = Property()
    hostaddr = Property()
    hostport = Property(9990)
    device_name = Property()
    device_id = Property()
    _conf_attrs = [
        'backend_name',
        'hostaddr',
        'hostport',
        'device_name',
        'device_id',
    ]
    def __init__(self, **kwargs):
        for attr in self._conf_attrs:
            setattr(self, attr, kwargs.get(attr))
        self.backend = kwargs.get('backend')
        if self.backend is None:
            self.backend = self.build_backend(**self._get_conf_data())
        if self.backend.device_name != self.device_name:
            self.device_name = self.backend.device_name
        self.backend.bind(device_name=self.on_backend_prop_change)
        if hasattr(self.backend, 'hostport'):
            self.backend.bind(
                hostaddr=self.on_backend_prop_change,
                hostport=self.on_backend_prop_change,
            )
    @classmethod
    def from_existing(cls, backend, **kwargs):
        d = dict(
            backend=backend,
            backend_name=backend.__class__.__name__,
            hostaddr=getattr(backend, 'hostaddr', None),
            hostport=getattr(backend, 'hostport', None),
            device_name=backend.device_name,
            device_id=backend.device_id,
        )
        for key, val in d.items():
            kwargs.setdefault(key, val)
        return cls(**kwargs)
    def build_backend(self, cls=None, **kwargs):
        if cls is None:
            cls = BACKENDS[self.device_type][self.backend_name]
        return cls(**kwargs)
    def on_backend_prop_change(self, instance, value, **kwargs):
        prop = kwargs.get('property')
        setattr(self, prop.name, value)
        self.emit('trigger_save')

class VidhubConfig(DeviceConfigBase):
    presets = ListProperty()
    _conf_attrs = DeviceConfigBase._conf_attrs + [
        'presets',
    ]
    device_type = 'vidhub'
    def __init__(self, **kwargs):
        kwargs.setdefault('presets', [])
        super().__init__(**kwargs)
        pkwargs = {k:self.on_preset_update for k in ['name', 'crosspoints']}
        for preset in self.backend.presets:
            preset.bind(**pkwargs)
        self.backend.bind(on_preset_added=self.on_preset_added)
        if hasattr(self.backend, 'hostport'):
            self.backend.bind(
                hostaddr=self.on_backend_prop_change,
                hostport=self.on_backend_prop_change,
            )
    @classmethod
    def from_existing(cls, backend, **kwargs):
        kwargs.setdefault('presets', [])
        for preset in backend.presets:
            kwargs['presets'].append(dict(
                name=preset.name,
                index=preset.index,
                crosspoints=preset.crosspoints.copy(),
            ))
        return super().from_existing(backend, **kwargs)
    def build_backend(self, cls=None, **kwargs):
        kwargs['presets'] = kwargs['presets'][:]
        return super().build_backend(cls, **kwargs)
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
    def _get_conf_data(self):
        d = super()._get_conf_data()
        for pdata in d['presets']:
            if 'backend' in pdata:
                del pdata['backend']
        return d

class SmartViewConfig(DeviceConfigBase):
    device_type = 'smartview'

class SmartScopeConfig(DeviceConfigBase):
    device_type = 'smartscope'

Config._device_type_map['vidhub']['cls'] = VidhubConfig
Config._device_type_map['smartview']['cls'] = SmartViewConfig
Config._device_type_map['smartscope']['cls'] = SmartScopeConfig

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
