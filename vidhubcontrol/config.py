import os
import json
import asyncio
from typing import List, Dict, ClassVar
from loguru import logger

import jsonfactory
from pydispatch import Dispatcher, Property
from pydispatch.properties import ListProperty, DictProperty

from vidhubcontrol.common import ConnectionState, ConnectionManager, SyncronizedConnectionManager
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
    """Config store for devices

    Handles storage of device connection information and any user-defined values
    for the backends defined in the :doc:`backends module <backends>`. Data is stored
    in JSON format.

    During :meth:`start`, all previously stored devices will be loaded and begin
    communication. Devices are also discovered using `Zeroconf`_ through the
    :doc:`discovery module <discovery>`.

    Since each device has a unique id, network address changes (due to DHCP, etc)
    are handled appropriately.

    The configuration data is stored when:

    * A device is added or removed
    * A change is detected for a device's network address
    * Any user-defined device value changes (device name, presets, etc)

    The recommended method to start ``Config`` is through the :meth:`load_async`
    method.

    Example:
        .. code-block:: python

            import asyncio
            from vidhubcontrol.config import Config

            loop = asyncio.get_event_loop()
            conf = loop.run_until_complete(Config.load_async())

    Keyword Arguments:
        filename (:obj:`str`, optional): Filename to load/save config data to.
            If not given, defaults to :attr:`DEFAULT_FILENAME`

    Attributes:
        vidhubs: A :class:`~pydispatch.properties.DictProperty` of
            :class:`VidhubConfig` instances using
            :attr:`~DeviceConfigBase.device_id` as keys
        smartviews: A :class:`~pydispatch.properties.DictProperty` of
            :class:`SmartViewConfig` instances using
            :attr:`~DeviceConfigBase.device_id` as keys
        smartscopes: A :class:`~pydispatch.properties.DictProperty` of
            :class:`SmartScopeConfig` instances using
            :attr:`~DeviceConfigBase.device_id` as keys
        all_devices: A :class:`~pydispatch.properties.DictProperty`
            containing all devices from :attr:`vidhubs`, :attr:`smartviews` and
            :attr:`smartscopes`

    .. autoattribute:: DEFAULT_FILENAME

    .. _Zeroconf: https://en.wikipedia.org/wiki/Zero-configuration_networking

    """
    DEFAULT_FILENAME = '~/vidhubcontrol.json'
    USE_DISCOVERY = True
    connection_manager: ConnectionManager #: Connection manager
    vidhubs: Dict[str, 'VidhubConfig'] = DictProperty()
    smartviews: Dict[str, 'SmartViewConfig'] = DictProperty()
    smartscopes: Dict[str, 'SmartScopeConfig'] = DictProperty()
    all_devices: Dict[str, 'DeviceConfigBase'] = DictProperty()
    _conf_attrs = ['vidhubs', 'smartscopes', 'smartviews']
    _device_type_map = {
        'vidhub':{'prop':'vidhubs'},
        'smartview':{'prop':'smartviews'},
        'smartscope':{'prop':'smartscopes'},
    }
    def __init__(self, **kwargs):
        self.start_kwargs = kwargs.copy()
        self.connection_manager = ConnectionManager()
        self.filename = kwargs.get('filename', self.DEFAULT_FILENAME)
        self.loop = asyncio.get_event_loop()
        self.discovery_listener = None
        self.discovery_lock = asyncio.Lock()

    @property
    def connection_state(self) -> ConnectionState:
        """The current :attr:`~.common.ConnectionManager.state` of the
        :attr:`connection_manager`
        """
        return self.connection_manager.state

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
        """Creates and initializes device backends

        Keyword Arguments:
            vidhubs (dict): A ``dict`` containing the necessary data (as values)
                to create an instance of :class:`VidhubConfig`
            smartviews (dict): A ``dict`` containing the necessary data (as values)
                to create an instance of :class:`SmartViewConfig`
            smartscopes (dict): A ``dict`` containing the necessary data (as values)
                to create an instance of :class:`SmartScopeConfig`

        Note:
            All config object instances are created using the
            :meth:`DeviceConfigBase.create` classmethod.

        """
        async def _init_backend(prop, cls, **okwargs):
            okwargs['config'] = self
            obj = await cls.create(**okwargs)
            device_id = obj.device_id
            if device_id is None:
                device_id = self.id_for_device(obj)
            prop[device_id] = obj
            assert device_id not in self.all_devices
            self.all_devices[device_id] = obj
            obj.bind(
                device_id=self.on_backend_device_id,
                trigger_save=self.on_device_trigger_save,
            )
        tasks = []
        for key, d in self._device_type_map.items():
            items = kwargs.get(d['prop'], {})
            prop = getattr(self, d['prop'])
            for item_data in items.values():
                okwargs = item_data.copy()
                task = _init_backend(prop, d['cls'], **okwargs)
                tasks.append(task)
        if len(tasks):
            await asyncio.gather(*tasks)

    async def start(self, **kwargs):
        """Starts the device backends and discovery routines

        Keyword arguments passed to the initialization will be used here,
        but can be overridden in this method. They will also be passed to
        :meth:`_initialize_backends`.

        """
        if ConnectionState.connecting in self.connection_state:
            await self.connection_manager.wait_for('connected')
            return
        if self.connection_state.is_connected:
            return
        await self.connection_manager.set_state('connecting')

        logger.info('Config starting...')
        self.start_kwargs.update(kwargs)
        kwargs = self.start_kwargs

        await self._initialize_backends(**kwargs)
        if not self.USE_DISCOVERY:
            await self.connection_manager.set_state('connected')
            return
        if self.discovery_listener is not None:
           await self.connection_manager.wait_for('connected')
           return
        self.discovery_listener = BMDDiscovery(self.loop)
        self.discovery_listener.bind_async(
            self.loop,
            bmd_service_added=self.on_discovery_service_added,
            bmd_service_updated=self.on_discovery_service_updated,
        )
        await self.discovery_listener.start()
        await self.connection_manager.set_state('connected')
        logger.debug('Config started')
    async def stop(self):
        """Stops all device backends and discovery routines
        """
        await self.connection_manager.set_state('disconnecting')
        logger.debug('Config stopping...')
        if self.discovery_listener is not None:
            await self.discovery_listener.stop()
            self.discovery_listener = None
        coros = set()
        for vidhub in self.vidhubs.values():
            coros.add(vidhub.close())
        for smartview in self.smartviews.values():
            coros.add(smartview.close())
        for smartscope in self.smartscopes.values():
            coros.add(smartscope.close())
        if len(coros):
            await asyncio.gather(*coros)
        await self.connection_manager.set_state('not_connected')
        logger.debug('Config stopped')
    async def build_backend(self, device_type, backend_name, **kwargs):
        """Creates a "backend" instance

        The supplied keyword arguments are used to create the instance object
        which will be created using its
        :meth:`~vidhubcontrol.backends.base.BackendBase.create` classmethod.

        The appropriate subclass of :class:`DeviceConfigBase` will be created
        and stored to the config using :meth:`add_device`.

        Arguments:
            device_type (str): Device type to create. Choices are "vidhub",
                "smartview", "smartscope"
            backend_name (str): The class name of the backend as found in
                :doc:`backends`

        Returns:
            An instance of a :class:`vidhubcontrol.backends.base.BackendBase`
            subclass

        """
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
        """Adds a "backend" instance to the config

        A subclass of :class:`DeviceConfigBase` will be either created or updated
        from the given backend instance.

        If the ``device_id`` exists in the config, the
        :attr:`DeviceConfigBase.backend` value of the matching
        :class:`DeviceConfigBase` instance will be set to the given ``backend``.
        Otherwise, a new :class:`DeviceConfigBase` instance will be created using
        the :meth:`DeviceConfigBase.from_existing` classmethod.

        Arguments:
            backend: An instance of one of the subclasses of
                :class:`vidhubcontrol.backends.base.BackendBase` found in
                :doc:`backends`

        """
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
        assert obj.device_id not in self.all_devices
        self.all_devices[obj.device_id] = obj
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
        if old in self.all_devices:
            del self.all_devices[old]
        if old in prop:
            del prop[old]
        if value in prop:
            self.save()
            return
        assert value not in self.all_devices
        self.all_devices[value] = backend
        prop[value] = backend
        self.save()
    async def add_discovered_device(self, device_type, info, device_id):
        if self.connection_state & (ConnectionState.disconnecting | ConnectionState.not_connected):
            return
        if ConnectionState.connecting in self.connection_state:
            await self.connection_manager.wait_for('connected')
        logger.debug(f'add_discovered_device: {device_type}, {info}, {device_id}')
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
                logger.debug(f'existing device: {obj!r}')
                if obj.hostaddr != hostaddr or obj.hostport != hostport:
                    logger.debug('resetting hostaddr')
                    await obj.reset_hostaddr(hostaddr, hostport)
                elif not obj.connection_state.is_connected:
                    await obj.reconnect()
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
    async def on_discovery_service_added(self, info, **kwargs):
        if kwargs.get('class') not in ['Videohub', 'SmartView']:
            return
        device_type = kwargs.get('device_type')
        device_id = kwargs.get('id')
        if device_id is None:
            return
        await self.add_discovered_device(device_type, info, device_id)

    async def on_discovery_service_updated(self, info, **kwargs):
        logger.debug(f'update: {info!r}, {kwargs}')

    def on_device_trigger_save(self, *args, **kwargs):
        self.save()
    def save(self, filename=None):
        """Saves the config data to the given filename

        Arguments:
            filename (:obj:`str`, optional): The filename to write config data to.
                If not supplied, the current :attr:`filename` is used.

        Notes:
            If the ``filename`` argument is provided, it will replace the
            existing :attr:`filename` value.

        """
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
        """Creates a Config instance, loading data from the given filename

        Arguments:
            filename (:obj:`str`, optional): The filename to read config data
                from, defaults to :const:`Config.DEFAULT_FILENAME`

        Returns:
            A :class:`Config` instance

        """
        kwargs = cls._prepare_load_params(filename, **kwargs)
        return cls(**kwargs)
    @classmethod
    async def load_async(cls, filename=None, **kwargs):
        """Creates a Config instance, loading data from the given filename

        This coroutine method creates the ``Config`` instance and will ``await``
        all start-up coroutines and futures before returning.

        Arguments:
            filename (:obj:`str`, optional): The filename to read config data
                from, defaults to :attr:`DEFAULT_FILENAME`

        Returns:
            A :class:`Config` instance

        """
        kwargs = cls._prepare_load_params(filename, **kwargs)
        config = cls(**kwargs)
        await config.start()
        return config

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.stop()


class DeviceConfigBase(ConfigBase):
    """Base class for device config storage

    Attributes:
        config: A reference to the parent :class:`Config` instance
        backend: An instance of :class:`vidhubcontrol.backends.base.BackendBase`
        backend_name: The class name of the backend, used when loading
            from saved config data
        hostaddr: The IPv4 address of the device
        hostport: The port address of the device
        device_name: User-defined name to store with the device, defaults
            to the :attr:`device_id` value
        device_id: The unique id as reported by the device

    """
    config: Config = Property()
    backend: 'vidhubcontrol.backends.base.BackendBase' = Property()
    backend_name: str = Property()
    hostaddr: str = Property()
    hostport: int = Property(9990)
    device_name: str = Property()
    device_id: str = Property()

    _conf_attrs = [
        'backend_name',
        'hostaddr',
        'hostport',
        'device_name',
        'device_id',
    ]
    connection_manager: SyncronizedConnectionManager
    """A connection manager that syncronizes its state with the :attr:`backend`
    """
    def __init__(self, **kwargs):
        self.config = kwargs.get('config')
        self.loop = asyncio.get_event_loop()
        self.bind_async(self.loop, backend=self.on_backend_set)
        self.connection_manager = SyncronizedConnectionManager()
    @property
    def connection_state(self) -> ConnectionState:
        """The current :attr:`~.common.SyncronizedConnectionManager.state`
        of the :attr:`connection_manager`
        """
        return self.connection_manager.state
    @classmethod
    async def create(cls, **kwargs):
        """Creates device config and backend instances asynchronously

        Keyword arguments passed to this classmethod are passed to the init
        method and will be used to set its attributes.

        If a "backend" keyword argument is supplied, it should be a running
        instance of :class:`vidhubcontrol.backends.base.BackendBase`. It will
        then be used to collect config values from.

        If "backend" is not present, the appropriate one will be created using
        :meth:`build_backend`.

        Returns:
            An instance of :class:`DeviceConfigBase`

        """
        self = cls(**kwargs)
        for attr in self._conf_attrs:
            setattr(self, attr, kwargs.get(attr))
        self.backend = kwargs.get('backend')
        if self.backend is not None:
            await self.connection_manager.set_other(self.backend.connection_manager)
        else:
            self.backend = await self.build_backend(**self._get_conf_data())
        return self
    @classmethod
    async def from_existing(cls, backend, **kwargs):
        """Creates a device config object from an existing backend

        Keyword arguments will be passed to the :meth:`create` method

        Arguments:
            backend: An instance of :class:`vidhubcontrol.backends.base.BackendBase`

        Returns:
            An instance of :class:`DeviceConfigBase`

        """
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
    async def reconnect(self):
        if ConnectionState.waiting in self.connection_manager.state:
            await self.connection_manager.wait_for('connected|failure')
        await self.backend.disconnect()
        await self.backend.connect()
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
    async def close(self):
        if self.backend is not None:
            await self.backend.disconnect()
        await self.connection_manager.close()
    async def build_backend(self, cls=None, **kwargs):
        """Creates a backend instance asynchronously

        Keyword arguments will be passed to the
        :meth:`vidhubcontrol.backends.base.BackendBase.create_async` method.

        Arguments:
            cls (optional): A subclass of
                :class:`~vidhubcontrol.backends.base.BackendBase`. If not present,
                the class will be determined from existing values of
                :attr:`device_type` and :attr:`backend_name`

        Returns:
            An instance of :class:`vidhubcontrol.backends.base.BackendBase`

        """
        kwargs.setdefault('event_loop', self.loop)
        if cls is None:
            cls = BACKENDS[self.device_type][self.backend_name]
        await self.connection_manager.set_other(None)
        await self.connection_manager.set_state(ConnectionState.connecting)
        backend = cls(**kwargs)
        async def wait_for_connecting():
            state = await backend.connection_manager.wait_for(ConnectionState.connecting)
            await self.connection_manager.set_other(backend.connection_manager)
        t = asyncio.ensure_future(backend.connect())
        await wait_for_connecting()
        await t
        return backend
    def on_backend_prop_change(self, instance, value, **kwargs):
        if instance is not self.backend:
            return
        if not instance.connection_state.is_connected:
            return
        prop = kwargs.get('property')
        setattr(self, prop.name, value)
        self.emit('trigger_save')
    async def on_backend_set(self, instance, backend, **kwargs):
        old = kwargs.get('old')
        if old is not None:
            old.unbind(self)
        if backend is None:
            await self.connection_manager.set_other(None)
            return
        await self.connection_manager.set_other(backend.connection_manager)
        if backend.connection_state.is_connected:
            if self.backend.device_name != self.device_name:
                self.device_name = self.backend.device_name
        if backend.device_id is None:
            if self.device_id is None:
                self.device_id = self.config.id_for_device(self)
        elif backend.connection_state.is_connected:
            self.device_id = backend.device_id
        backend.bind(
            device_name=self.on_backend_prop_change,
            device_id=self._on_backend_device_id,
        )
        if hasattr(backend, 'hostport'):
            if backend.connection_state.is_connected:
                self.hostaddr = backend.hostaddr
                self.hostport = backend.hostport
            backend.bind(
                hostaddr=self.on_backend_prop_change,
                hostport=self.on_backend_prop_change,
            )
    def _on_backend_device_id(self, backend, value, **kwargs):
        if backend is not self.backend:
            return
        if not backend.connection_state.is_connected:
            return
        if backend.device_id is None:
            if self.device_id is not None:
                self.device_id = self.config.id_for_device(self)
        else:
            self.device_id = backend.device_id


class VidhubConfig(DeviceConfigBase):
    """Config container for VideoHub devices

    Attributes:
        presets: Preset data collected from the device
            :class:`presets <vidhubcontrol.backends.base.Preset>`. Will be used
            on initialization to populate the preset data to the device

    """
    presets: List[Dict] = ListProperty()
    _conf_attrs = DeviceConfigBase._conf_attrs + [
        'presets',
    ]
    device_type: ClassVar[str] = 'vidhub'
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
    async def on_backend_set(self, instance, backend, **kwargs):
        if backend is not None:
            pkwargs = {k:self.on_preset_update for k in ['name', 'crosspoints']}
            for preset in self.backend.presets:
                preset.bind(**pkwargs)
            self.backend.bind(on_preset_added=self.on_preset_added)
        await super().on_backend_set(instance, backend, **kwargs)
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
    """Config container for SmartView devices
    """
    device_type: ClassVar[str] = 'smartview'

class SmartScopeConfig(DeviceConfigBase):
    """Config container for SmartScope devices
    """
    device_type: ClassVar[str] = 'smartscope'

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
