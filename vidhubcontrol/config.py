import os
import json

import jsonfactory
from pydispatch import Dispatcher, Property
from pydispatch.properties import ListProperty, DictProperty

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
    vidhubs = DictProperty()
    _conf_attrs = ['vidhubs']
    def __init__(self, **kwargs):
        self.filename = kwargs.get('filename', DEFAULT_FILENAME)
        vidhubs = kwargs.get('vidhubs', {})
        for vidhub_data in vidhubs.values():
            vidhub = VidhubConfig(**vidhub_data)
            self.vidhubs[vidhub.device_id] = vidhub
            vidhub.bind(trigger_save=self.on_vidhub_trigger_save)
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
    def load(cls, filename=None):
        if filename is None:
            filename = DEFAULT_FILENAME
        kwargs = {'filename':filename}
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
    device_id = Property()
    presets = ListProperty()
    _conf_attrs = [
        'backend_name',
        'hostaddr',
        'hostport',
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
        self.backend.bind(on_preset_added=self.on_preset_added)
    @classmethod
    def from_existing(cls, backend):
        kwargs = dict(
            backend=backend,
            backend_name=backend.__class__.__name__,
            hostaddr=getattr(backend, 'hostaddr', None),
            hostport=getattr(backend, 'hostport', None),
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
