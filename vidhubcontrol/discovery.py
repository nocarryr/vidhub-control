import asyncio
import ipaddress

from pydispatch import Dispatcher, Property
from pydispatch.properties import DictProperty

try:
    import zeroconf
    ZEROCONF_AVAILABLE = True
except ImportError: # pragma: no cover
    zeroconf = None
    ZEROCONF_AVAILABLE = False

from vidhubcontrol.utils import find_ip_addresses

PUBLISH_TTL = 60

def convert_bytes_dict(d):
    return {str(k, 'UTF-8'):str(d[k], 'UTF-8') for k in d.keys()}

def convert_dict_bytes(d):
    return {bytes(k, 'UTF-8'):bytes(d[k], 'UTF-8') for k in d.keys()}

class ServiceInfo(Dispatcher):
    """Container for Zeroconf service information

    Closely related to :class:`zeroconf.ServiceInfo`

    Attributes:
        type (str): Fully qualified service type
        name (str): Fully qualified service name
        server (str): Fully qualified name for service host
            (defaults to :attr:`name`)
        address (:class:`ipaddress.IPv4Address`): The service ip address
        port (int): The service port
        properties (dict): Custom properties for the service

    """
    properties = DictProperty()
    _attrs = ['type', 'name', 'server', 'address', 'port', 'properties']
    def __init__(self, **kwargs):
        for attr in self._attrs:
            setattr(self, attr, kwargs.get(attr))
    @classmethod
    def from_zc_info(cls, info):
        """Creates an instance from a :class:`zeroconf.ServiceInfo` object

        Arguments:
            info (:class:`zeroconf.ServiceInfo`):

        Returns:
            An instance of :class:`ServiceInfo`

        """
        kwargs = {}
        for attr in cls._attrs:
            val = getattr(info, attr)
            if attr == 'properties':
                val = convert_bytes_dict(val)
            elif attr == 'address':
                val = ipaddress.ip_address(val)
            kwargs[attr] = val
        return cls(**kwargs)
    @property
    def id(self):
        """Unique id for the service as a ``tuple`` of (:attr:`type`, :attr:`name`)
        """
        return (self.type, self.name)#, self.address, self.port)
    def to_zc_info(self):
        """Creates a copy as an instance of :class:`zeroconf.ServiceInfo`
        """
        kwargs = {}
        for attr in self._attrs:
            val = getattr(self, attr)
            if attr == 'properties':
                val = convert_dict_bytes(val)
            elif attr == 'address':
                if isinstance(val, ipaddress.IPv4Interface):
                    val = val.ip.packed
                elif isinstance(val, ipaddress.IPv4Address):
                    val = val.packed
                else:
                    val = ipaddress.ip_address(val).packed
            kwargs[attr] = val
        type_ = kwargs.pop('type')
        name = kwargs.pop('name')
        return zeroconf.ServiceInfo(type_, name, **kwargs)
    def update(self, other):
        """Updates the :attr:`properties` from another :class:`ServiceInfo` instance
        """
        if self.properties == other.properties:
            return
        self.properties = other.properties.copy()
    def __hash__(self):
        return hash(self.id)
    def __eq__(self, other):
        return self.id == other.id
    def __repr__(self):
        return '<{self.__class__.__name__}> {self}'.format(self=self)
    def __str__(self):
        return '{self.name}: {self.type} ({self.address}:{self.port}), properties={self.properties}'.format(self=self)

class Message(object):
    """A message to communicate actions to and from :class:`Listener`

    Attributes:
        info: The :class:`ServiceInfo` related to the message

    Note:
        This class and its subclasses are not meant to be used directly. They
        are used internally in :class:`Listener` methods.

    """
    def __init__(self, info):
        self.info = info
    def __repr__(self):
        return str(self)
    def __str__(self):
        return '{self.__class__.__name__}: {self.info}'.format(self=self)

class AddedMessage(Message):
    pass

class RemovedMessage(Message):
    pass

class PublishMessage(Message):
    def __init__(self, info, ttl=PUBLISH_TTL):
        super().__init__(info)
        self.ttl = ttl

class UnPublishMessage(Message):
    pass

class Listener(Dispatcher):
    """An async zeroconf service listener

    Allows async communication with :class:`zeroconf.Zeroconf` through
    :meth:`asyncio.AbstractEventLoop.run_in_executor` calls.

    Arguments:
        mainloop (:class:`asyncio.BaseEventLoop`): asyncio event loop instance
        service_type (str): The fully qualified service type name to subscribe to

    Attributes:
        services (dict): All services currently discovered as instances of
            :class:`ServiceInfo`. Stored using :attr:`ServiceInfo.id` as keys
        message_queue (:class:`asyncio.Queue`): Used to communicate actions and
            events with instances of :class:`Message`
        published_services (dict): Stores services that have been published
            using :meth:`publish_service` as :class:`ServiceInfo` instances.

    """
    _events_ = ['service_added', 'service_removed']
    services = DictProperty()
    def __init__(self, mainloop, service_type):
        self.mainloop = mainloop
        self.service_type = service_type
        self.running = False
        self.stopped = asyncio.Event()
        self.message_queue = asyncio.Queue()
        self.zeroconf = None
        self.published_services = {}
    async def start(self):
        """Starts the service listener

        Runs :class:`zeroconf.Zeroconf` in an :class:`~concurrent.futures.Executor`
        instance through `asyncio.AbstractEventLoop.run_in_executor`
        (see :meth:`run_zeroconf`).

        """
        await self.mainloop.run_in_executor(None, self.run_zeroconf)
        self.running = True
        self.run_future = asyncio.ensure_future(self.run(), loop=self.mainloop)
    async def run(self):
        """Main loop for communicating with :class:`zeroconf.Zeroconf`

        Waits for messages on the :attr:`message_queue` and processes them.
        The loop will exit if an object placed on the queue is not an instance
        of :class:`Message`.

        When the loop exits, the :class:`zeroconf.Zeroconf` instance will be
        closed.

        """
        while self.running:
            msg = await self.message_queue.get()
            self.message_queue.task_done()
            if not isinstance(msg, Message):
                self.running = False
                break
            elif isinstance(msg, AddedMessage):
                if msg.info.id in self.services:
                    self.services[msg.info.id].update(msg.info)
                else:
                    await self.add_service_info(msg.info)
            elif isinstance(msg, RemovedMessage):
                if msg.info.id in self.services:
                    await self.remove_service_info(msg.info)
            elif isinstance(msg, PublishMessage):
                if not ZEROCONF_AVAILABLE:
                    continue
                zc_info = msg.info.to_zc_info()
                await self.mainloop.run_in_executor(
                    None, self.zeroconf.register_service,
                    zc_info, msg.ttl,
                )
            elif isinstance(msg, UnPublishMessage):
                zc_info = msg.info.to_zc_info()
                await self.mainloop.run_in_executor(
                    None, self.zeroconf.unregister_service, zc_info,
                )
        await self.mainloop.run_in_executor(None, self.stop_zeroconf)
        self.stopped.set()
    async def stop(self):
        """Stops the loop in :meth:`run`
        """
        if not self.running:
            return
        self.message_queue.put_nowait(None)
        await self.stopped.wait()
    def run_zeroconf(self):
        """Starts :class:`zeroconf.Zeroconf` and :class:`zeroconf.ServiceBrowser` instances

        This is meant to be called inside of an :class:`concurrent.futures.Executor`
        and not used directly.

        """
        if not ZEROCONF_AVAILABLE:
            return
        self.zeroconf = zeroconf.Zeroconf()
        self.zeroconf.listener = self
        self.browser = zeroconf.ServiceBrowser(self.zeroconf, self.service_type, self)
    def stop_zeroconf(self):
        """Closes the :class:`zeroconf.Zeroconf` instance

        This is meant to be called inside of an :class:`concurrent.futures.Executor`
        and not used directly.

        """
        if self.zeroconf is None:
            return
        self.zeroconf.close()
    async def add_message(self, msg):
        """Adds a message to the :attr:`message_queue`

        Arguments:
            msg (:class:`Message`): Message to send

        """
        await self.message_queue.put(msg)
    async def add_service_info(self, info, **kwargs):
        self.services[info.id] = info
        self.emit('service_added', info, **kwargs)
    async def remove_service_info(self, info, **kwargs):
        del self.services[info.id]
        self.emit('service_removed', info, **kwargs)
    def remove_service(self, zc, type_, name):
        info = ServiceInfo(type=type_, name=name)
        msg = RemovedMessage(info)
        asyncio.run_coroutine_threadsafe(self.add_message(msg), loop=self.mainloop)
    def add_service(self, zc, type_, name):
        info = zc.get_service_info(type_, name)
        info = ServiceInfo.from_zc_info(info)
        msg = AddedMessage(info)
        asyncio.run_coroutine_threadsafe(self.add_message(msg), loop=self.mainloop)
    async def get_local_ifaces(self, refresh=False):
        ifaces = getattr(self, '_local_ifaces', None)
        if ifaces is not None and not refresh:
            return ifaces
        ifaces = self._local_ifaces = [iface for iface_name, iface in find_ip_addresses()]
        return ifaces
    async def get_local_hostname(self):
        name = getattr(self, '_local_hostname', None)
        if name is not None:
            return name
        name = None
        for iface in await self.get_local_ifaces():
            _name, srv = await self.mainloop.getnameinfo((str(iface.ip), 80))
            if _name is not None and _name != 'localhost':
                name = _name
                break
        if name is None:
            name = 'localhost'
        self._local_hostname = name
        return name
    async def publish_service(self, type_, port, name=None, addresses=None,
                              properties=None, ttl=PUBLISH_TTL):
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
        info_kwargs = {
            'type':type_,
            'port':port,
            'name':name,
            'properties':properties,
        }
        for addr in addresses:
            if not isinstance(addr, ipaddress.IPv4Address):
                addr = ipaddress.IPv4Address(addr)
            info_kwargs['address'] = addr
            info = ServiceInfo(**info_kwargs)
            if info.id not in self.published_services:
                self.published_services[info.id] = {}
            if info.address in self.published_services[info.id]:
                continue
            self.published_services[info.id][info.address] = info
            msg = PublishMessage(info, ttl)
            asyncio.run_coroutine_threadsafe(self.add_message(msg), loop=self.mainloop)
    async def unpublish_service(self, type_, port, name=None, addresses=None, properties=None):
        """Removes a service published through :meth:`publish_service`

        Arguments:
            type_ (str): Fully qualified service type
            port (int): The service port
            name (str, optional): Fully qualified service name. If not provided,
                this will be generated from the ``type_`` and the hostname
                detected by :meth:`get_local_hostname`
            addresses (optional): If provided, an ``iterable`` of IP addresses
                to unpublish. Can be :class:`ipaddress.IPv4Address` or any type
                that can be parsed by :func:`ipaddress.ip_address`
            properties (dict, optional): Custom properties for the service

        """
        hostname = await self.get_local_hostname()
        if name is None:
            name = '.'.join([hostname, type_])
        if addresses is None:
            addresses = await self.get_local_ifaces()
        if properties is None:
            properties = {}
        info_kwargs = {
            'type':type_,
            'port':port,
            'name':name,
            'properties':properties,
        }
        for addr in addresses:
            if not isinstance(addr, ipaddress.IPv4Address):
                addr = ipaddress.IPv4Address(addr)
            info_kwargs['address'] = addr
            info = ServiceInfo(**info_kwargs)
            if info.id not in self.published_services:
                continue
            if info.address not in self.published_services[info.id]:
                continue
            del self.published_services[info.id][info.address]
            msg = PublishMessage(info)
            asyncio.run_coroutine_threadsafe(self.add_message(msg), loop=self.mainloop)

class BMDDiscovery(Listener):
    """Zeroconf listener for Blackmagic devices

    Attributes:
        vidhubs (dict): Contains discovered Videohub devices.
            This :class:`~pydispatch.properties.DictProperty` can be used to
            subscribe to changes.
        smart_views (dict): Contains discovered SmartView devices.
            This :class:`~pydispatch.properties.DictProperty` can be used to
            subscribe to changes.
        smart_scopes (dict): Contains discovered SmartScope devices.
            This :class:`~pydispatch.properties.DictProperty` can be used to
            subscribe to changes.

    """
    vidhubs = DictProperty()
    smart_views = DictProperty()
    smart_scopes = DictProperty()
    def __init__(self, mainloop, service_type='_blackmagic._tcp.local.'):
        super().__init__(mainloop, service_type)
    async def add_service_info(self, info, **kwargs):
        device_cls = info.properties.get('class')
        bmd_id = info.properties.get('unique id', '').upper()
        if device_cls == 'Videohub':
            self.vidhubs[bmd_id] = info
            kwargs.update({'class':device_cls, 'id':bmd_id, 'device_type':'vidhub'})
        elif info.properties.get('class') == 'SmartView':
            if 'SmartScope' in info.properties.get('name', ''):
                self.smart_scopes[bmd_id] = info
                kwargs['device_type'] = 'smartscope'
            else:
                self.smart_views[bmd_id] = info
                kwargs['device_type'] = 'smartview'
            kwargs.update({'class':device_cls, 'id':bmd_id})
        await super().add_service_info(info, **kwargs)
    async def remove_service_info(self, info, **kwargs):
        device_cls = info.properties.get('class')
        bmd_id = info.properties.get('unique id', '').upper()
        if bmd_id in self.vidhubs and device_cls == 'Videohub':
            del self.vidhubs[bmd_id]
            kwargs.update({'class':device_cls, 'id':bmd_id, 'device_type':'vidhub'})
        elif bmd_id in self.smart_views and device_cls == 'SmartView':
            del self.smart_views[bmd_id]
            kwargs.update({'class':device_cls, 'id':bmd_id, 'device_type':'smartview'})
        elif bmd_id in self.smart_scopes and device_cls == 'SmartView':
            del self.smart_scopes[bmd_id]
            kwargs.update({'class':device_cls, 'id':bmd_id, 'device_type':'smartscope'})
        await super().remove_service_info(info, **kwargs)


def main():
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    listener = BMDDiscovery(loop)
    def on_service_added(info, **kwargs):
        print('Added: {}'.format(info))
    def on_service_removed(info, **kwargs):
        print('Removed: {}'.format(info))

    listener.bind(service_added=on_service_added, service_removed=on_service_removed)

    async def run():
        await listener.start()
        await asyncio.sleep(5)
        print(listener.services)
        await listener.stop()

    loop.run_until_complete(run())
    return listener

if __name__ == '__main__':
    main()
