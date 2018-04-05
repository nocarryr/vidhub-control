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
    SmartViewTelnetBackend,
    SmartScopeTelnetBackend,
)

BACKENDS = {
    'vidhub':{cls.__name__:cls for cls in [DummyBackend, TelnetBackend]},
    'smartview':{cls.__name__:cls for cls in [SmartViewDummyBackend, SmartViewTelnetBackend]},
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
    loop = None
    def __init__(self, **kwargs):
        self.start_kwargs = kwargs.copy()
        auto_start = kwargs.get('auto_start', True)
        self.starting = asyncio.Event()
        self.running = asyncio.Event()
        self.stopped = asyncio.Event()
        self.filename = kwargs.get('filename', self.DEFAULT_FILENAME)
        if 'loop' in kwargs:
            Config.loop = kwargs['loop']
        elif Config.loop is None:
            Config.loop = asyncio.get_event_loop()
        self.discovery_listener = None
        self.discovery_lock = asyncio.Lock()
        if auto_start:
            self._start_fut = asyncio.ensure_future(self.start(**kwargs), loop=self.loop)
        else:
            async def _start_fut(config):
                await config.running.wait()
            self._start_fut = asyncio.ensure_future(_start_fut(self), loop=self.loop)
    def id_for_device(self, device):
        if not isinstance(device, DeviceConfigBase):
            prop = getattr(self, self._device_type_map[device.device_type]['prop'])
            obj = None
            for _obj in prop.values():
                if _obj.backend is device:
                    obj = _obj
                    break
            if obj is None:
                raise Exception('Could not find device {!r}'.format(device))
            else:
                device = obj
        if device.device_id is not None:
            return device.device_id
        return str(id(device))
    async def _initialize_backends(self, **kwargs):
        for key, d in self._device_type_map.items():
            items = kwargs.get(d['prop'], {})
            prop = getattr(self, d['prop'])
            for item_data in items.values():
                okwargs = item_data.copy()
                okwargs['config'] = self
                obj = await d['cls'].create(**okwargs)
                device_id = obj.device_id
                if device_id is None:
                    device_id = self.id_for_device(obj)
                prop[device_id] = obj
                obj.bind(
                    device_id=self.on_backend_device_id,
                    trigger_save=self.on_device_trigger_save,
                )
    async def start(self, **kwargs):
        if self.starting.is_set():
            await self.running.wait()
            return
        if self.running.is_set():
            return
        self.starting.set()

        self.start_kwargs.update(kwargs)
        kwargs = self.start_kwargs

        await self._initialize_backends(**kwargs)
        if not self.USE_DISCOVERY:
            self.starting.clear()
            self.running.set()
            return
        if self.discovery_listener is not None:
           await self.running.wait()
           return
        self.discovery_listener = BMDDiscovery(self.loop)
        self.discovery_listener.bind(
            service_added=self.on_discovery_service_added,
        )
        await self.discovery_listener.start()
        self.starting.clear()
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
        Config.loop = None
    async def build_backend(self, device_type, backend_name, **kwargs):
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
        backend = await cls.create_async(**kwargs)
        await self.add_device(backend)
        return backend
    async def add_vidhub(self, backend):
        return await self.add_device(backend)
    async def add_smartview(self, backend):
        return await self.add_device(backend)
    async def add_smartscope(self, backend):
        return await self.add_device(backend)
    async def add_device(self, backend):
        device_type = backend.device_type
        cls = self._device_type_map[device_type]['cls']
        prop = getattr(self, self._device_type_map[device_type]['prop'])
        if backend.device_id is not None and backend.device_id in prop:
            obj = prop[backend.device_id]
            obj.backend = backend
        else:
            obj = await cls.from_existing(backend, config=self)
        if obj.device_id is None:
            obj.device_id = self.id_for_device(obj)
        prop[obj.device_id] = obj
        obj.bind(
            trigger_save=self.on_device_trigger_save,
            device_id=self.on_backend_device_id,
        )
        self.save()
    def on_backend_device_id(self, backend, value, **kwargs):
        if value is None:
            return
        old = kwargs.get('old')
        prop = getattr(self, self._device_type_map[backend.device_type]['prop'])
        if old in prop:
            del prop[old]
        if value in prop:
            self.save()
            return
        prop[value] = backend
        self.save()
    async def add_discovered_device(self, device_type, info, device_id):
        async with self.discovery_lock:
            prop = getattr(self, self._device_type_map[device_type]['prop'])
            cls = None
            for key, _cls in BACKENDS[device_type].items():
                if 'Telnet' in key:
                    cls = _cls
                    break
            hostaddr = str(info.address)
            hostport = int(info.port)
            if device_id in prop:
                obj = prop[device_id]
                if obj.hostaddr != hostaddr or obj.hostport != hostport:
                    await obj.reset_hostaddr(hostaddr, hostport)
                return
            backend = await cls.create_async(
                hostaddr=hostaddr,
                hostport=hostport,
                event_loop=self.loop,
            )
            if backend is None:
                return
            if backend.device_id != device_id:
                await backend.disconnect()
                return
            await self.add_device(backend)
    def on_discovery_service_added(self, info, **kwargs):
        if kwargs.get('class') not in ['Videohub', 'SmartView']:
            return
        device_type = kwargs.get('device_type')
        device_id = kwargs.get('id')
        if device_id is None:
            return
        prop = getattr(self, self._device_type_map[device_type]['prop'])
        if device_id in prop:
            obj = prop[device_id]
            if not obj.backend_unavailable:
                return
        asyncio.run_coroutine_threadsafe(self.add_discovered_device(device_type, info, device_id), loop=self.loop)
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
    def _prepare_load_params(cls, filename=None, **kwargs):
        if filename is None:
            filename = cls.DEFAULT_FILENAME
        kwargs['filename'] = filename
        filename = os.path.expanduser(filename)
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                s = f.read()
            kwargs.update(jsonfactory.loads(s))
        return kwargs
    @classmethod
    def load(cls, filename=None, **kwargs):
        kwargs = cls._prepare_load_params(filename, **kwargs)
        return cls(**kwargs)
    @classmethod
    async def load_async(cls, filename=None, **kwargs):
        kwargs = cls._prepare_load_params(filename, **kwargs)
        kwargs['auto_start'] = False
        config = cls(**kwargs)
        await config.start()
        await config._start_fut
        return config


class DeviceConfigBase(ConfigBase):
    config = Property()
    backend = Property()
    backend_name = Property()
    hostaddr = Property()
    hostport = Property(9990)
    device_name = Property()
    device_id = Property()
    backend_unavailable = Property(False)
    _conf_attrs = [
        'backend_name',
        'hostaddr',
        'hostport',
        'device_name',
        'device_id',
    ]
    def __init__(self, **kwargs):
        self.config = kwargs.get('config')
        self.bind(backend=self.on_backend_set)
        self.loop = kwargs.get('event_loop', Config.loop)
    @classmethod
    async def create(cls, **kwargs):
        self = cls(**kwargs)
        for attr in self._conf_attrs:
            setattr(self, attr, kwargs.get(attr))
        self.backend = kwargs.get('backend')
        if self.backend is None:
            self.backend = await self.build_backend(**self._get_conf_data())
        return self
    @classmethod
    async def from_existing(cls, backend, **kwargs):
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
        kwargs['event_loop'] = backend.event_loop
        return await cls.create(**kwargs)
    async def reset_hostaddr(self, hostaddr, hostport=None):
        if hostport is None:
            hostport = self.hostport
        await self.backend.disconnect()
        self.hostaddr = hostaddr
        self.hostport = hostport
        self.backend.hostaddr = hostaddr
        self.backend.hostport = hostport
        await self.backend.connect()
        self.emit('trigger_save')
    async def build_backend(self, cls=None, **kwargs):
        kwargs.setdefault('event_loop', self.loop)
        if cls is None:
            cls = BACKENDS[self.device_type][self.backend_name]
        backend = await cls.create_async(**kwargs)
        if backend is not None:
            if backend.connection_unavailable:
                self.backend_unavailable = True
        return backend
    def on_backend_prop_change(self, instance, value, **kwargs):
        if instance is not self.backend:
            return
        if not instance.connected:
            return
        prop = kwargs.get('property')
        setattr(self, prop.name, value)
        self.emit('trigger_save')
    def on_backend_set(self, instance, backend, **kwargs):
        old = kwargs.get('old')
        if old is not None:
            old.unbind(self)
        if backend is None:
            return
        if backend.connected:
            if self.backend.device_name != self.device_name:
                self.device_name = self.backend.device_name
        if backend.device_id is None:
            if self.device_id is None:
                self.device_id = self.config.id_for_device(self)
        elif backend.connected:
            self.device_id = backend.device_id
        backend.bind(
            device_name=self.on_backend_prop_change,
            device_id=self._on_backend_device_id,
        )
        if hasattr(backend, 'hostport'):
            if backend.connected:
                self.hostaddr = backend.hostaddr
                self.hostport = backend.hostport
            backend.bind(
                hostaddr=self.on_backend_prop_change,
                hostport=self.on_backend_prop_change,
            )
    def _on_backend_device_id(self, backend, value, **kwargs):
        if backend is not self.backend:
            return
        if not backend.connected:
            return
        if backend.device_id is None:
            if self.device_id is not None:
                self.device_id = self.config.id_for_device(self)
        else:
            self.device_id = backend.device_id


class VidhubConfig(DeviceConfigBase):
    presets = ListProperty()
    _conf_attrs = DeviceConfigBase._conf_attrs + [
        'presets',
    ]
    device_type = 'vidhub'
    @classmethod
    async def create(cls, **kwargs):
        kwargs.setdefault('presets', [])
        self = await super().create(**kwargs)
        return self
    @classmethod
    async def from_existing(cls, backend, **kwargs):
        kwargs.setdefault('presets', [])
        for preset in backend.presets:
            kwargs['presets'].append(dict(
                name=preset.name,
                index=preset.index,
                crosspoints=preset.crosspoints.copy(),
            ))
        return await super().from_existing(backend, **kwargs)
    async def build_backend(self, cls=None, **kwargs):
        kwargs['presets'] = kwargs['presets'][:]
        return await super().build_backend(cls, **kwargs)
    def on_backend_set(self, instance, backend, **kwargs):
        super().on_backend_set(instance, backend, **kwargs)
        if self.backend is None:
            return
        pkwargs = {k:self.on_preset_update for k in ['name', 'crosspoints']}
        for preset in self.backend.presets:
            preset.bind(**pkwargs)
        self.backend.bind(on_preset_added=self.on_preset_added)
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
