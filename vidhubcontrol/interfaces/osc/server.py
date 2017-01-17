import asyncio

from pythonosc import osc_server, osc_bundle, osc_message, osc_packet

async def _handle_callback(handler, osc_address, client_address, when=None, *messages):
    if when is not None:
        now = asyncio.time()
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
                handler_futures.append(_handle_callback(
                    handler,
                    timed_msg.message.address,
                    client_address,
                    timed_msg.time,
                    *timed_msg.message,
                ))
    except osc_packet.ParseError:
        # Pass? Probably not best, but this is a re-implementation for now
        pass
    finally:
        if len(handler_futures):
            await asyncio.wait(handler_futures)

class OSCUDPServer(osc_server.AsyncIOOSCUDPServer):
    class _OSCProtocolFactory(asyncio.DatagramProtocol):
        def __init__(self, dispatcher):
            self.dispatcher = dispatcher
        def datagram_received(self, data, client_address):
            asyncio.ensure_future(
                _call_handlers_for_packet(data, client_address, self.dispatcher),
            )
