import asyncio
import logging

from pydispatch import Property

from vidhubcontrol import aiotelnetlib
from vidhubcontrol.backends.base import BackendBase

logger = logging.getLogger(__name__)

class TelnetBackend(BackendBase):
    DEFAULT_PORT = 9990
    SECTION_NAMES = [
        'PROTOCOL PREAMBLE:',
        'VIDEOHUB DEVICE:',
        'INPUT LABELS:',
        'OUTPUT LABELS:',
        'VIDEO OUTPUT LOCKS:',
        'VIDEO OUTPUT ROUTING:',
        'CONFIGURATION:',
    ]
    def __init__(self, **kwargs):
        self.read_enabled = False
        self.current_section = None
        self.ack_or_nak = None
        self.read_coro = None
        super(TelnetBackend, self).__init__(**kwargs)
        self.hostaddr = kwargs.get('hostaddr')
        self.hostport = kwargs.get('hostport', self.DEFAULT_PORT)
        self.rx_bfr = b''
        self.response_ready = asyncio.Event()
    async def read_loop(self):
        while self.read_enabled:
            rx_bfr = await self.client.read_very_eager()
            if len(rx_bfr):
                self.rx_bfr += rx_bfr
                if True:#self.rx_bfr.endswith(b'\n\n'):
                    logger.debug(self.rx_bfr.decode('UTF-8'))
                    await self.parse_rx_bfr()
                    self.rx_bfr = b''
            await asyncio.sleep(.1)
    async def send_to_client(self, data):
        c = self.client
        if not self.connected:
            c = await self.connect()
        s = '\n'.join(['---> {}'.format(line) for line in data.decode('UTF-8').splitlines()])
        logger.debug(s)
        await c.write(data)
    async def do_connect(self):
        self.rx_bfr = b''
        logger.debug('connecting')
        c = self.client = await aiotelnetlib.Telnet(self.hostaddr, self.hostport)
        self.prelude_parsed = False
        self.read_enabled = True
        self.read_coro = asyncio.ensure_future(self.read_loop(), loop=self.event_loop)
        await self.wait_for_response(prelude=True)
        logger.debug('prelude parsed')
        return c
    async def do_disconnect(self):
        logger.debug('disconnecting')
        self.read_enabled = False
        if self.read_coro is not None:
            await asyncio.wait([self.read_coro], loop=self.event_loop)
            self.read_coro = None
        if self.client is not None:
            await self.client.close_async()
        self.client = None
        logger.debug('disconnected')
    async def wait_for_response(self, prelude=False):
        logger.debug('wait_for_response...')
        while self.read_enabled:
            await self.response_ready.wait()
            self.response_ready.clear()
            if prelude:
                if self.prelude_parsed:
                    return
                else:
                    await asyncio.sleep(.1)
            if self.ack_or_nak is not None:
                resp = self.ack_or_nak
                logger.debug('ack_or_nak: {}'.format(resp))
                self.ack_or_nak = None
                return resp
    async def parse_rx_bfr(self):
        def split_value(line):
            return line.split(':')[1].strip(' ')
        bfr = self.rx_bfr.decode('UTF-8')
        section_parsed = False
        for line_idx, line in enumerate(bfr.splitlines()):
            if 'END PRELUDE' in line:
                self.current_section = None
                self.rx_bfr = b''
                self.prelude_parsed = True
                break
            line = line.rstrip('\n')
            if not len(line):
                continue
            if line.startswith('ACK') or line.startswith('NAK'):
                self.ack_or_nak = line
                continue
            if line in self.SECTION_NAMES:
                self.current_section = line.rstrip(':')
                continue
            if self.current_section is None:
                continue
            elif self.current_section == 'PROTOCOL PREAMBLE':
                if line.startswith('Version:'):
                    self.device_version = split_value(line)
            elif self.current_section == 'VIDEOHUB DEVICE':
                if line.startswith('Model name:'):
                    self.device_model = split_value(line)
                elif line.startswith('Unique ID:'):
                    self.device_id = split_value(line)
                elif line.startswith('Video outputs:'):
                    self.num_outputs = int(split_value(line))
                elif line.startswith('Video inputs:'):
                    self.num_inputs = int(split_value(line))
            elif self.current_section == 'OUTPUT LABELS':
                i = int(line.split(' ')[0])
                self.output_labels[i] = ' '.join(line.split(' ')[1:])
                section_parsed = True
            elif self.current_section == 'INPUT LABELS':
                i = int(line.split(' ')[0])
                self.input_labels[i] = ' '.join(line.split(' ')[1:])
                section_parsed = True
            elif self.current_section == 'VIDEO OUTPUT ROUTING':
                out_idx, in_idx = [int(v) for v in line.split(' ')]
                self.crosspoints[out_idx] = in_idx
            else:
                section_parsed = True
        self.response_ready.set()
        if not self.prelude_parsed:
            return
        if self.current_section is not None and section_parsed:
            self.current_section = None
    async def get_status(self, *sections):
        if not len(sections):
            sections = [
                b'VIDEO OUTPUT ROUTING:\n\n',
                b'OUTPUT LABELS:\n\n',
                b'INPUT LABELS:\n\n',
            ]
        for section in sections:
            await self.send_to_client(section)
    async def set_crosspoint(self, out_idx, in_idx):
        return await self.set_crosspoints((out_idx, in_idx))
    async def set_crosspoints(self, *args):
        tx_lines = ['VIDEO OUTPUT ROUTING:']
        for arg in args:
            out_idx, in_idx = arg
            tx_lines.append('{} {}'.format(out_idx, in_idx))
        tx_bfr = bytes('\n'.join(tx_lines), 'UTF-8')
        tx_bfr += b'\n\n'
        await self.send_to_client(tx_bfr)
        r = await self.wait_for_response()
        if r is None or r.startswith('NAK'):
            return False
        return True
    async def set_output_label(self, out_idx, label):
        return await self.set_output_labels((out_idx, label))
    async def set_output_labels(self, *args):
        tx_lines = ['OUTPUT LABELS:']
        for arg in args:
            out_idx, label = arg
            tx_lines.append('{} {}'.format(out_idx, label))
        tx_bfr = bytes('\n'.join(tx_lines), 'UTF-8')
        tx_bfr += b'\n\n'
        await self.send_to_client(tx_bfr)
        r = await self.wait_for_response()
        if r is None or r.startswith('NAK'):
            return False
        return True
    async def set_input_label(self, in_idx, label):
        return await self.set_input_labels((in_idx, label))
    async def set_input_labels(self, *args):
        tx_lines = ['INPUT LABELS:']
        for arg in args:
            in_idx, label = arg
            tx_lines.append('{} {}'.format(in_idx, label))
        tx_bfr = bytes('\n'.join(tx_lines), 'UTF-8')
        tx_bfr += b'\n\n'
        await self.send_to_client(tx_bfr)
        r = await self.wait_for_response()
        if r is None or r.startswith('NAK'):
            return False
        return True

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--addr', dest='hostaddr')
    p.add_argument('--port', dest='hostport', default=9990)
    args = p.parse_args()
    o = vars(args)

    async def test(t):
        await asyncio.sleep(2)
        print('wakey wakey')

        xpts = []
        for i, xpt in enumerate(t.crosspoints):
            v = xpt + 1
            if v >= t.num_inputs - 1:
                v = 0
            xpts.append((i, v))
        orig_xpts = t.crosspoints[:]
        await t.set_crosspoints(*xpts)
        print('set_crosspoints: from {} to {}'.format(orig_xpts, t.crosspoints))

        lbls = []
        for i, lbl in enumerate(t.input_labels):
            if lbl.islower():
                lbl = lbl.upper()
            else:
                lbl = lbl.lower()
            lbls.append((i, lbl))
        orig_lbls = t.input_labels[:]
        await t.set_input_labels(*lbls)
        print('set input_labels from {} to {}'.format(orig_lbls, t.input_labels))

        lbls = []
        for i, lbl in enumerate(t.output_labels):
            if lbl.islower():
                lbl = lbl.upper()
            else:
                lbl = lbl.lower()
            lbls.append((i, lbl))
        orig_lbls = t.output_labels[:]
        await t.set_output_labels(*lbls)
        print('set output_labels from {} to {}'.format(orig_lbls, t.output_labels))

        await t.disconnect()

    t = TelnetBackend(**o)
    loop = t.event_loop
    loop.set_debug(True)
    loop.run_until_complete(test(t))
    print('crosspoints: {}'.format(t.crosspoints))
    print('outputs: {}'.format(t.output_labels))
    print('inputs: {}'.format(t.input_labels))
