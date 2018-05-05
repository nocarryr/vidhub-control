import asyncio
import time

from pythonosc import osc_server, osc_bundle, osc_message, osc_packet
from pythonosc.osc_bundle_builder import OscBundleBuilder
from pythonosc.osc_message_builder import OscMessageBuilder
import pythonosc.dispatcher

class OscDispatcher(pythonosc.dispatcher.Dispatcher):
    def __init__(self, server=None):
        super().__init__()
        self.server = server
        self.dispatch_queue = asyncio.Queue()
    async def send_message(self, node, client_address, *args, **kwargs):
        when = kwargs.get('when', time.time())
        builder = OscMessageBuilder(address=node.osc_address)
        for arg in args:
            builder.add_arg(arg)
        msg = builder.build()
        await self.server.sendto(msg, client_address, when)

async def _handle_callback(handler, osc_address, client_address, when=None, *messages):
    if when is not None:
        now = time.time()
        if when > now:
            await asyncio.sleep(when - now)
    if handler.args:
        handler.callback(osc_address, client_address, handler.args, *messages)
    else:
        handler.callback(osc_address, client_address, *messages)

async def _call_handlers_for_packet(data, client_address, dispatcher):
    handler_futures = []
    try:
        packet = osc_packet.OscPacket(data)
        for timed_msg in packet.messages:
            handlers = dispatcher.handlers_for_address(
                timed_msg.message.address)
            if not handlers:
                continue
            for handler in handlers:
                handler_futures.append(asyncio.ensure_future(_handle_callback(
                    handler,
                    timed_msg.message.address,
                    client_address,
                    timed_msg.time,
                    *timed_msg.message,
                )))
    except:# osc_packet.ParseError:
        # Pass? Probably not best, but this is a re-implementation for now
        #pass
        raise
    finally:
        if len(handler_futures):
            await asyncio.wait(handler_futures)

class OSCUDPServer(osc_server.AsyncIOOSCUDPServer):
    def __init__(self, server_address, dispatcher, loop=None):
        if loop is None:
            loop = asyncio.get_event_loop()
        super().__init__(server_address, dispatcher, loop)
        self.dispatcher.server = self
        self.tx_queue = asyncio.Queue()
        self.running = False
        self.transport = None
        self.protocol = None

    class _OSCProtocolFactory(asyncio.DatagramProtocol):
        def __init__(self, dispatcher, loop):
            self.dispatcher = dispatcher
            self._loop = loop
            self.closed = asyncio.Event()
        def connection_lost(self, exc):
            self.closed.set()
        def datagram_received(self, data, client_address):
            #asyncio.ensure_future(_call_handlers_for_packet(data, client_address, self.dispatcher))
            self.dispatcher.dispatch_queue.put_nowait((data, client_address))

    async def start(self):
        self.running = True
        fut = self._loop.create_datagram_endpoint(
            lambda: self._OSCProtocolFactory(self.dispatcher, self._loop),
            local_addr=self._server_address,
        )
        self.transport, self.protocol = await fut
        self.send_loop_future = asyncio.ensure_future(self.send_loop())
        self.dispatch_loop_future = asyncio.ensure_future(self.dispatch_loop())
    async def send_loop(self):
        def get_tx_items():
            while True:
                try:
                    tx_item = self.tx_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                self.tx_queue.task_done()
                yield tx_item
        def bundle_item(items_by_addr, tx_item):
            if tx_item['client_address'] not in items_by_addr:
                items_by_addr[tx_item['client_address']] = {'timestamp':tx_item['when'], 'items':[]}
            items_by_addr[tx_item['client_address']]['items'].append(tx_item['data'])
        while self.running:
            items_by_addr = {}
            tx_item = await self.tx_queue.get()
            self.tx_queue.task_done()
            if tx_item is None:
                break
            bundle_item(items_by_addr, tx_item)
            for tx_item in get_tx_items():
                data, client_address, when = tx_item
                if data is None:
                    break
                bundle_item(items_by_addr, tx_item)
            for client_address, d in items_by_addr.items():
                bundle = OscBundleBuilder(d['timestamp'])
                for message in d['items']:
                    bundle.add_content(message)
                data = bundle.build()
                self.transport.sendto(data.dgram, client_address)
    async def dispatch_loop(self):
        while self.running:
            item = await self.dispatcher.dispatch_queue.get()
            self.dispatcher.dispatch_queue.task_done()
            if item is None:
                break
            data, client_address = item
            await _call_handlers_for_packet(data, client_address, self.dispatcher)
    async def stop(self):
        self.running = False
        await self.dispatcher.dispatch_queue.put(None)
        await self.dispatch_loop_future
        await self.tx_queue.put(None)
        await self.send_loop_future
        self.transport.close()
        await self.protocol.closed.wait()
        self.transport = None
        self.protocol = None
    async def sendto(self, data, client_address, when=None):
        if when is None:
            when = time.time()
        await self.tx_queue.put({
            'data':data,
            'client_address':client_address,
            'when':when,
        })
