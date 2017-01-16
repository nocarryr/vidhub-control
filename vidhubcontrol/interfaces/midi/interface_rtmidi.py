import asyncio
import signal
import argparse

import rtmidi

from vidhubcontrol.interfaces.midi.interface import MidiInterface

class RtMidiInterface(MidiInterface):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.out_ports = []
        self.in_ports = []
    async def start(self, loop=None):
        lookup_port = rtmidi.MidiOut()#b'Vidhub-MidiOut-Lookup')
        for i, port_name in enumerate(lookup_port.get_ports()):
            if 'RtMidi' in port_name:
                continue
            if 'Midi Through' in port_name:
                continue
            # if b'Vidhub' in port_name:
            #     continue
            #name = bytes('Vidhub-MidiOut-{}'.format(i), 'UTF-8')
            print('outport: ', port_name, i)
            out_port = rtmidi.MidiOut()
            out_port.open_port(i)
            self.out_ports.append((port_name, out_port))
        #lookup_port.close_port()

        lookup_port = rtmidi.MidiIn()#b'Vidhub-MidiIn-Lookup')
        for i, port_name in enumerate(lookup_port.get_ports()):
            if 'RtMidi' in port_name:
                continue
            if 'Midi Through' in port_name:
                continue
            # if b'Vidhub' in port_name:
            #     continue
            # name = bytes('Vidhub-MidiIn-{}'.format(i), 'UTF-8')
            print('inport: ', port_name, i)
            in_port = rtmidi.MidiIn()
            in_port.open_port(i)
            self.in_ports.append((port_name, in_port))
        #lookup_port.close_port()
        print('outports: ', self.out_ports)
        print('inports: ', self.in_ports)
        await super().start(loop=loop)
    def get_io_loop_coroutines(self):
        coros = super().get_io_loop_coroutines()
        coros.append(self.read_midi_in())
        return coros
    async def stop(self):
        self.running = False
        for port_name, port in self.out_ports:
            port.close_port()
        self.out_ports.clear()
        for port_name, port in self.in_ports:
            port.close_port()
        self.in_ports.clear()
        await super().stop()
    async def read_midi_in(self):
        while self.running:
            rx = False
            for port_name, port in self.in_ports:
                r = port.get_message()
                if r is not None:
                    msg, dt = r
                    #print(msg, dt)
                    await self.event_rx_queue.put((port_name, msg))
                    rx = True
            if not rx:
                await asyncio.sleep(.1)
        print('read_midi_in exit')
    async def send_midi_data(self, message):
        msg = message.midi_event.build_message()
        for port_name, port in self.out_ports:
            print('TX ({}): {!r}'.format(port_name, message.midi_event))
            port.send_message(msg)
        message.complete.set()

async def main(**kwargs):
    from vidhubcontrol.config import Config
    config = Config.load()
    vidhub = config.vidhubs['dummy'].backend
    interface = RtMidiInterface()
    await interface.start()
    print('adding interface')
    await interface.add_vidhub(vidhub, midi_channel=0)
    print('added')
    await asyncio.sleep(4)
    print('setting crosspoints')
    for i in range(5):
        vidhub.crosspoints = [i] * vidhub.num_outputs
    print('crosspoints set')
    await asyncio.sleep(2)
    if kwargs.get('listen'):
        running = True
        def stop_interface(interface):
            interface.running = False
        interface.loop.add_signal_handler(signal.SIGINT, stop_interface, interface)
        while interface.running:
            await asyncio.sleep(1)
        await interface.stop()
    else:
        print('stopping')
        await interface.stop()
    return interface

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--listen', dest='listen', action='store_true')
    args = p.parse_args()

    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    loop.run_until_complete(main(**vars(args)))
