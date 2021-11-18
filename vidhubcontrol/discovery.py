import asyncio
from typing import (
    List, Tuple, Dict, Union, Optional, Any, Callable, Coroutine, Awaitable,
)
import ipaddress
import platform
from loguru import logger

from pydispatch import Dispatcher, Property
from pydispatch.properties import DictProperty


try:
    import zeroconf
    ZEROCONF_AVAILABLE = True
except ImportError: # pragma: no cover
    zeroconf = None
    ZEROCONF_AVAILABLE = False

if ZEROCONF_AVAILABLE:
    from zeroconf.asyncio import AsyncZeroconf
    from zeroconf import IPVersion


from vidhubcontrol.utils import find_ip_addresses

PUBLISH_TTL = 60

StrOrBytes = Union[str, bytes]
AddressLike = Union[StrOrBytes, ipaddress.IPv4Address]
CoroFunc = Callable[[Any, Any], Coroutine]

def convert_bytes_dict(d: Dict[bytes, bytes]) -> Dict[str, str]:
    return {str(k, 'UTF-8'):str(d[k], 'UTF-8') for k in d.keys()}

def convert_dict_bytes(d: Dict[StrOrBytes, StrOrBytes]) -> Dict[bytes, bytes]:
    r = {}
    for key, val in d.items():
        if not isinstance(key, bytes):
            key = key.encode()
        if not isinstance(val, bytes):
            val = val.encode()
        r[key] = val
    return r

def pack_ip_address(ip: AddressLike) -> bytes:
    if isinstance(ip, bytes):
        return ip
    if isinstance(ip, ipaddress.IPv4Interface):
        ip = ip.ip.packed
    elif isinstance(ip, ipaddress.IPv4Address):
        ip = ip.packed
    elif isinstance(val, str):
        ip = ipaddress.ip_address(val).packed
    return ip

def unpack_ip_address(ip: AddressLike) -> ipaddress.IPv4Address:
    if isinstance(ip, ipaddress.IPv4Interface):
        return ip.ip
    return ipaddress.ip_address(ip)

def run_on_loop(
    coro: CoroFunc,
    dest_loop: asyncio.BaseEventLoop,
    cur_loop: Optional[asyncio.BaseEventLoop] = None,
    create_task: Optional[bool] = True
) -> Awaitable:
    if cur_loop is None:
        try:
            cur_loop = asyncio.get_event_loop()
        except RuntimeError:
            cur_loop = None
    is_same_loop = cur_loop is dest_loop
    if not is_same_loop:
        fut = asyncio.run_coroutine_threadsafe(coro, loop=dest_loop)
    elif create_task:
        fut = asyncio.ensure_future(coro)
    else:
        fut = coro
    return fut

class ServiceInfo(Dispatcher):
    """Container for Zeroconf service information

    Closely related to :class:`zeroconf.ServiceInfo`

    Attributes:
        type (str): Fully qualified service type
        name (str): Fully qualified service name
        server (str): Fully qualified name for service host
            (defaults to :attr:`name`)
        addresses: The service ip address
        port (int): The service port
        properties: Custom properties for the service

    """
    properties: Dict[str, str] = DictProperty()
    _direct_attrs = ['name', 'server', 'port', 'properties']
    def __init__(
        self,
        type_: str,
        name: str,
        server: Optional[str] = None,
        port: Optional[int] = None,
        addresses: Optional[List[AddressLike]] = None,
        properties: Optional[Dict] = None,
        ttl: Optional[int] = None,
    ) -> None:
        self.type: str = type_
        self.name: str = name
        self.server: Optional[str] = server
        self.port: Optional[int] = port

        if addresses is None:
            addresses = []
        self.addresses: List[AddressLike] = addresses
        if properties is not None:
            self.properties = properties
        self.ttl: Optional[int] = ttl

    @property
    def address(self) -> Optional[ipaddress.IPv4Address]:
        """The first element of :attr:`addresses`
        """
        if not len(self.addresses):
            raise ValueError(f'{self!r} has no addresses')
        return self.addresses[0]

    @classmethod
    def from_zc_info(cls, info: 'zeroconf.ServiceInfo') -> 'ServiceInfo':
        """Creates an instance from a :class:`zeroconf.ServiceInfo` object

        Arguments:
            info (:class:`zeroconf.ServiceInfo`):

        Returns:
            An instance of :class:`ServiceInfo`

        """
        kwargs = {k:getattr(info, k) for k in cls._direct_attrs}
        kwargs['type_'] = info.type
        addresses = info.parsed_addresses(IPVersion.V4Only)
        kwargs['addresses'] = [unpack_ip_address(addr) for addr in addresses]
        kwargs['properties'] = convert_bytes_dict(info.properties)
        kwargs['ttl'] = info.host_ttl
        return cls(**kwargs)

    @property
    def id(self) -> Tuple[str, str]:
        """Unique id for the service as a ``tuple`` of (:attr:`type`, :attr:`name`)
        """
        return (self.type, self.name)#, self.address, self.port)

    def to_zc_info(self) -> 'zeroconf.ServiceInfo':
        """Creates a copy as an instance of :class:`zeroconf.ServiceInfo`
        """
        kwargs = {k:getattr(self, k) for k in self._direct_attrs}
        kwargs['type_'] = self.type
        kwargs['addresses'] = [pack_ip_address(addr) for addr in self.addresses]
        kwargs['properties'] = convert_dict_bytes(self.properties)
        if self.ttl is not None:
            kwargs['host_ttl'] = self.ttl
        return zeroconf.ServiceInfo(**kwargs)

    def update(self, other: 'ServiceInfo'):
        """Updates the :attr:`properties` from another :class:`ServiceInfo` instance
        """
        assert other.id == self.id
        self.properties = other.properties.copy()
        self.addresses = other.addresses.copy()
        self.server = other.server
        self.port = other.port

    def __hash__(self):
        return hash(self.id)
    def __eq__(self, other: 'ServiceInfo'):
        return self.id == other.id
    def __repr__(self):
        return '<{self.__class__.__name__}> {self}'.format(self=self)
    def __str__(self):
        if not len(self.addresses):
            addr = None
        else:
            addr = self.addresses[0]
        return f'{self.name}: {self.type} ({addr}:{self.port}), properties={self.properties}'

class Message(object):
    """A message to communicate actions to and from :class:`Listener`

    Attributes:
        info: The :class:`ServiceInfo` related to the message

    Note:
        This class and its subclasses are not meant to be used directly. They
        are used internally in :class:`Listener` methods.

    """
    info: ServiceInfo
    __slots__ = ('info',)
    def __init__(self, info: ServiceInfo):
        self.info: ServiceInfo = info
    def __repr__(self):
        return str(self)
    def __str__(self):
        return '{self.__class__.__name__}: {self.info}'.format(self=self)

class BrowserMessage(Message):
    pass

class AddedMessage(BrowserMessage):
    pass

class RemovedMessage(BrowserMessage):
    pass

class UpdateMessage(BrowserMessage):
    pass

class RegistrationMessage(Message):
    pass

class PublishMessage(RegistrationMessage):
    pass

class RepublishMessage(RegistrationMessage):
    pass

class UnPublishMessage(RegistrationMessage):
    pass

class Listener(Dispatcher):
    """An async zeroconf service listener

    Allows async communication with :class:`zeroconf.Zeroconf` through
    :meth:`asyncio.AbstractEventLoop.run_in_executor` calls.

    Arguments:
        mainloop (:class:`asyncio.BaseEventLoop`): asyncio event loop instance
        service_type (str): The fully qualified service type name to subscribe to

    Attributes:
        services: All services currently discovered as instances of
            :class:`ServiceInfo`. Stored using :attr:`ServiceInfo.id` as keys
        message_queue: Used to communicate actions and
            events with instances of :class:`Message`
        published_services: Stores services that have been published
            using :meth:`publish_service` as :class:`ServiceInfo` instances.

    """
    _events_ = ['service_added', 'service_updated', 'service_removed']
    services: Dict[str, ServiceInfo] = DictProperty()
    message_queue: asyncio.Queue
    published_services: Dict[str, ServiceInfo]
    def __init__(self, mainloop, service_type):
        self.mainloop = mainloop
        self.service_type = service_type
        self.running = False
        self.stopped = asyncio.Event()
        self.message_queue = asyncio.Queue()
        self._service_info_lock = asyncio.Lock()
        self.zeroconf = None
        self.published_services = {}

    async def start(self):
        """Starts the service listener
        """
        if self.running:
            return
        self.running = True
        logger.debug('Discovery starting...')
        self.run_zeroconf()
        self.run_future = asyncio.ensure_future(self.run())
        logger.debug('Discovery started')

    @logger.catch
    async def run(self):
        """Main loop for communicating with :class:`zeroconf.Zeroconf`

        Waits for messages on the :attr:`message_queue` and processes them.
        The loop will exit if an object placed on the queue is not an instance
        of :class:`Message`.
        """
        async def handle_service_registration(msg: RegistrationMessage):
            if not ZEROCONF_AVAILABLE:
                return
            zc_info = msg.info.to_zc_info()
            if isinstance(msg, PublishMessage):
                coro = self.async_zeroconf.async_register_service(zc_info)
            elif isinstance(msg, RepublishMessage):
                coro = self.async_zeroconf.async_update_service(zc_info)
            else:
                coro = self.async_zeroconf.async_unregister_service(zc_info)
            await coro

        while self.running:
            msg = await self.message_queue.get()
            if not isinstance(msg, Message):
                self.message_queue.task_done()
                break
            logger.debug(f'Handling "{msg!r}"')
            if isinstance(msg, RegistrationMessage):
                await handle_service_registration(msg)
            elif isinstance(msg, AddedMessage):
                await self.add_service_info(msg.info)
            elif isinstance(msg, RemovedMessage):
                await self.remove_service_info(msg.info)
            elif isinstance(msg, UpdateMessage):
                await self.update_service_info(msg.info)
            logger.debug('Message handled')
            self.message_queue.task_done()

    async def stop(self):
        """Stops the service listener
        """
        if not self.running:
            return
        self.running = False
        logger.debug('Discovery stopping...')
        await self.message_queue.put(None)
        await self.run_future
        await self.stop_zeroconf()
        self.stopped.set()
        logger.debug('Discovery stopped')

    def run_zeroconf(self):
        """Starts :class:`zeroconf.Zeroconf` and :class:`zeroconf.ServiceBrowser` instances
        """
        if not ZEROCONF_AVAILABLE:
            return
        self.async_zeroconf = AsyncZeroconf()
        self.zeroconf = self.async_zeroconf.zeroconf
        self.zeroconf.listener = self
        self.browser = zeroconf.ServiceBrowser(self.zeroconf, self.service_type, self)

    async def stop_zeroconf(self):
        """Closes the :class:`zeroconf.Zeroconf` instance
        """
        if self.zeroconf is None:
            return
        zc, a_zc = self.zeroconf, self.async_zeroconf
        self.zeroconf = None
        self.async_zeroconf = None
        await a_zc.async_close()

    async def add_message(self, msg: Message):
        """Adds a message to the :attr:`message_queue`

        Arguments:
            msg (:class:`Message`): Message to send

        """
        await self.message_queue.put(msg)

    async def add_service_info(self, info: ServiceInfo, **kwargs):
        async with self._service_info_lock:
            if info.id in self.services:
                raise ValueError(f'Service "{info}" already discovered')
            self.services[info.id] = info
        self.emit('service_added', info, **kwargs)

    async def update_service_info(self, info: ServiceInfo, **kwargs):
        async with self._service_info_lock:
            if info.id not in self.services:
                self.services[info.id] = info
                self.emit('service_added', info, **kwargs)
                return
            cur = self.services[info.id]
            cur.update(info)
        self.emit('service_updated', info, **kwargs)

    async def remove_service_info(self, info: ServiceInfo, **kwargs):
        async with self._service_info_lock:
            if info.id not in self.services:
                return
            del self.services[info.id]
        self.emit('service_removed', info, **kwargs)

    def add_service(self, zc: 'zeroconf.Zeroconf', type_: str, name: str):
        if self.running:
            info = zc.get_service_info(type_, name)
            info = ServiceInfo.from_zc_info(info)
            msg = AddedMessage(info)
            run_on_loop(self.add_message(msg), self.mainloop)

    def remove_service(self, zc: 'zeroconf.Zeroconf', type_: str, name: str):
        if self.running:
            info = ServiceInfo(type_=type_, name=name)
            msg = RemovedMessage(info)
            run_on_loop(self.add_message(msg), self.mainloop)

    def update_service(self, zc: 'zeroconf.Zeroconf', type_: str, name: str):
        if self.running:
            info = zc.get_service_info(type_, name)
            if info is None:
                self.remove_service(zc, type_, name)
                return
            info = ServiceInfo.from_zc_info(info)
            msg = UpdateMessage(info)
            run_on_loop(self.add_message(msg), self.mainloop)

    async def get_local_ifaces(self, refresh: Optional[bool] = False) -> List[ipaddress.IPv4Interface]:
        ifaces = getattr(self, '_local_ifaces', None)
        if ifaces is not None and not refresh:
            return ifaces
        ifaces = self._local_ifaces = [iface for iface_name, iface in find_ip_addresses()]
        return ifaces

    async def get_local_hostname(self) -> str:
        name = getattr(self, '_local_hostname', None)
        if name is not None:
            return name
        name = None
        for iface in await self.get_local_ifaces():
            _name, srv = await self.mainloop.getnameinfo((str(iface.ip), 80))
            if _name is None or _name == 'localhost':
                continue
            if _name == str(iface.ip):
                continue
            if len(_name) > 63:
                continue
        if name is None:
            name = platform.node()
        if not name:
            name = 'localhost'
        self._local_hostname = name
        return name

    async def publish_service(
        self,
        type_: str,
        port: int,
        name: Optional[str] = None,
        addresses: Optional[AddressLike] = None,
        properties: Optional[Dict] = None,
        ttl: Optional[int] = PUBLISH_TTL
    ):
        """Publishes a service on the network

        Arguments:
            type_ (str): Fully qualified service type
            port (int): The service port
            name (str, optional): Fully qualified service name. If not provided,
                this will be generated from the ``type_`` and the hostname
                detected by :meth:`get_local_hostname`
            addresses (optional): If provided, an ``iterable`` of IP addresses
                to publish. Can be :class:`ipaddress.IPv4Address` or any type
                that can be parsed by :func:`ipaddress.ip_address`
            properties (dict, optional): Custom properties for the service
            ttl (int, optional): The TTL value to publish.
                Defaults to :const:`PUBLISH_TTL`

        """
        hostname = await self.get_local_hostname()
        if name is None:
            name = '.'.join([hostname, type_])
        if addresses is None:
            addresses = await self.get_local_ifaces()
        if properties is None:
            properties = {}

        if addresses is None:
            addresses = []
        addresses = [unpack_ip_address(addr) for addr in addresses]
        info = ServiceInfo(
            type_=type_, port=port, name=name, properties=properties,
            ttl=ttl, addresses=addresses,
        )

        if info.id in self.published_services:
            raise ValueError(f'Service already published: {info!r}')
        self.published_services[info.id] = info
        msg = PublishMessage(info)
        await run_on_loop(self.add_message(msg), self.mainloop)

    async def republish_service(
        self,
        type_: str,
        port: int,
        name: Optional[str] = None,
        addresses: Optional[AddressLike] = None,
        properties: Optional[Dict] = None,
        ttl: Optional[int] = PUBLISH_TTL
    ):
        """Update an existing :class:`ServiceInfo` and republish it

        """
        hostname = await self.get_local_hostname()
        if name is None:
            name = '.'.join([hostname, type_])
        service_id = (type_, name)
        if service_id not in self.published_services:
            raise KeyError(f'Service "{service_id}" does not exist')
        info = self.published_services[service_id]
        info.port = port
        if addresses is not None:
            addresses = [unpack_ip_address(addr) for addr in addresses]
            info.addresses = addresses
        if properties is not None:
            info.properties = properties
        info.ttl = ttl
        msg = RepublishMessage(info)
        await run_on_loop(self.add_message(msg), self.mainloop)

    async def unpublish_service(self, type_: str, name: Optional[str] = None):
        """Removes a service published through :meth:`publish_service`

        Arguments:
            type_ (str): Fully qualified service type
            name (str, optional): Fully qualified service name. If not provided,
                this will be generated from the ``type_`` and the hostname
                detected by :meth:`get_local_hostname`
        """
        hostname = await self.get_local_hostname()
        if name is None:
            name = '.'.join([hostname, type_])

        service_id = (type_, name)
        if service_id not in self.published_services:
            raise KeyError(f'Service "{service_id}" does not exist')
        info = self.published_services[service_id]
        msg = UnPublishMessage(info)
        del self.published_services[service_id]
        await run_on_loop(self.add_message(msg), self.mainloop)

class BMDDiscovery(Listener):
    """Zeroconf listener for Blackmagic devices

    Attributes:
        vidhubs: Contains discovered Videohub devices.
            This :class:`~pydispatch.properties.DictProperty` can be used to
            subscribe to changes.
        smart_views: Contains discovered SmartView devices.
            This :class:`~pydispatch.properties.DictProperty` can be used to
            subscribe to changes.
        smart_scopes: Contains discovered SmartScope devices.
            This :class:`~pydispatch.properties.DictProperty` can be used to
            subscribe to changes.

    """
    vidhubs: Dict[str, ServiceInfo] = DictProperty()
    smart_views: Dict[str, ServiceInfo] = DictProperty()
    smart_scopes: Dict[str, ServiceInfo] = DictProperty()
    _events_ = ['bmd_service_added', 'bmd_service_updated', 'bmd_service_removed']
    def __init__(self, mainloop, service_type='_blackmagic._tcp.local.'):
        super().__init__(mainloop, service_type)
        self.bind_async(
            mainloop,
            service_added=self._add_bmd_service_info,
            service_updated=self._update_bmd_service_info,
            service_removed=self._remove_bmd_service_info,
        )

    async def _add_bmd_service_info(self, info: ServiceInfo, **kwargs):
        device_cls = info.properties['class']
        bmd_id = info.properties['unique id'].upper()
        kwargs.update({'class':device_cls, 'id':bmd_id})
        async with self._service_info_lock:
            if device_cls == 'Videohub':
                assert bmd_id not in self.vidhubs
                self.vidhubs[bmd_id] = info
                device_type = 'vidhub'
            elif device_cls == 'SmartView':
                if 'SmartScope' in info.properties['name']:
                    assert bmd_id not in self.smart_scopes
                    self.smart_scopes[bmd_id] = info
                    device_type = 'smartscope'
                else:
                    assert bmd_id not in self.smart_views
                    self.smart_views[bmd_id] = info
                    device_type = 'smartview'
        kwargs['device_type'] = device_type
        self.emit('bmd_service_added', info, **kwargs)

    async def _update_bmd_service_info(self, info: ServiceInfo, **kwargs):
        device_cls = info.properties['class']
        bmd_id = info.properties['unique id'].upper()
        kwargs.update({'class':device_cls, 'id':bmd_id})
        async with self._service_info_lock:
            if bmd_id in self.vidhubs:
                device_type = 'vidhub'
                o = self.vidhubs[bmd_id]
            elif bmd_id in self.smart_scopes:
                device_type = 'smartscope'
                o = self.smart_scopes[bmd_id]
            elif bmd_id in self.smart_views:
                device_type = 'smartview'
                o = self.smart_views[bmd_id]
            else:
                raise KeyError(f'Cannot find entry for "{info!r}"')
        assert o.id == info.id
        kwargs['device_type'] = device_type
        self.emit('bmd_service_updated', info, **kwargs)

    async def _remove_bmd_service_info(self, info: ServiceInfo, **kwargs):
        device_cls = info.properties.get('class')
        bmd_id = info.properties.get('unique id', '').upper()
        async with self._service_info_lock:
            if bmd_id in self.vidhubs and device_cls == 'Videohub':
                del self.vidhubs[bmd_id]
                kwargs.update({'class':device_cls, 'id':bmd_id, 'device_type':'vidhub'})
            elif bmd_id in self.smart_views and device_cls == 'SmartView':
                del self.smart_views[bmd_id]
                kwargs.update({'class':device_cls, 'id':bmd_id, 'device_type':'smartview'})
            elif bmd_id in self.smart_scopes and device_cls == 'SmartView':
                del self.smart_scopes[bmd_id]
                kwargs.update({'class':device_cls, 'id':bmd_id, 'device_type':'smartscope'})
        self.emit('bmd_service_removed', info, **kwargs)


def main():
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    listener = BMDDiscovery(loop)
    def on_service_added(info, **kwargs):
        logger.info('Added: {}'.format(info))
    def on_service_removed(info, **kwargs):
        logger.info('Removed: {}'.format(info))

    listener.bind(service_added=on_service_added, service_removed=on_service_removed)

    async def run():
        await listener.start()
        await asyncio.sleep(5)
        logger.info(str(listener.services))
        await listener.stop()

    loop.run_until_complete(run())
    return listener

if __name__ == '__main__':
    main()
