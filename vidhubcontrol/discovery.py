import asyncio
import ipaddress

from pydispatch import Dispatcher, Property
from pydispatch.properties import DictProperty

import zeroconf

def convert_bytes_dict(d):
    return {str(k):str(d[k]) for k in d.keys()}

class ServiceInfo(Dispatcher):
    properties = DictProperty()
    _attrs = ['type', 'name', 'address', 'port', 'properties']
    def __init__(self, **kwargs):
        for attr in self._attrs:
            setattr(self, attr, kwargs.get(attr))
    @classmethod
    def from_zc_info(cls, info):
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
        return (self.type, self.name)#, self.address, self.port)
    def update(self, other):
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

class Listener(Dispatcher):
    _events_ = ['service_added', 'service_removed']
    services = DictProperty()
    def __init__(self, mainloop, service_type):
        self.mainloop = mainloop
        self.service_type = service_type
        self.running = False
        self.stopped = asyncio.Event()
        self.message_queue = asyncio.Queue()
        self.zeroconf = None
    async def start(self):
        await self.mainloop.run_in_executor(None, self.run_zeroconf)
        self.running = True
        self.run_future = asyncio.ensure_future(self.run(), loop=self.mainloop)
    async def run(self):
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
        await self.mainloop.run_in_executor(None, self.stop_zeroconf)
        self.stopped.set()
    async def stop(self):
        if not self.running:
            return
        self.message_queue.put_nowait(None)
        await self.stopped.wait()
    def run_zeroconf(self):
        self.zeroconf = zeroconf.Zeroconf()
        self.zeroconf.listener = self
        self.browser = zeroconf.ServiceBrowser(self.zeroconf, self.service_type, self)
    def stop_zeroconf(self):
        if self.zeroconf is None:
            return
        self.zeroconf.close()
    async def add_message(self, msg):
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

class BMDDiscovery(Listener):
    vidhubs = DictProperty()
    smart_views = DictProperty()
    def __init__(self, mainloop, service_type='_blackmagic._tcp.local.'):
        super().__init__(mainloop, service_type)
    async def add_service_info(self, info, **kwargs):
        if info.properties.get('class') == 'Videohub':
            self.vidhubs[info.properties['unique id']] = info
            kwargs.update({'class':info.properties['class'], 'id':info.properties['unique id']})
        elif info.properties.get('class') == 'SmartView':
            self.smart_views[info.properties['unique id']] = info
            kwargs.update({'class':info.properties['class'], 'id':info.properties['unique id']})
        await super().add_service_info(info, **kwargs)
    async def remove_service_info(self, info, **kwargs):
        bmd_id = info.properties.get('unique id')
        if bmd_id in self.vidhubs and info.properties.get('class') == 'Videohub':
            del self.vidhubs[bmd_id]
            kwargs.update({'class':info.properties['class'], 'id':info.properties['unique id']})
        elif bmd_id in self.smart_views and info.properties.get('class') == 'SmartView':
            del self.smart_views[bmd_id]
            kwargs.update({'class':info.properties['class'], 'id':info.properties['unique id']})
        await super().remove_service_info(info, **kwargs)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    listener = BMDDiscovery(loop)
    def on_service_added(info, **kwargs):
        print('Added: {}'.format(info))
    def on_service_removed(info, **kwargs):
        print('Removed: {}'.format(info))

    listener.bind(service_added=on_service_added, service_removed=on_service_removed)

    async def main():
        await listener.start()
        await asyncio.sleep(5)
        print(listener.services)
        await listener.stop()

    loop.run_until_complete(main())
