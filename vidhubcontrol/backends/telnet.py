import asyncio
import logging
import string
import errno

from pydispatch import Property

from vidhubcontrol import aiotelnetlib
from .base import (
    VidhubBackendBase,
    SmartViewBackendBase,
    SmartScopeBackendBase,
    MONITOR_PROPERTY_MAP,
)

logger = logging.getLogger(__name__)

class TelnetBackendBase(object):
    hostaddr = Property()
    hostport = Property()
    def _telnet_init(self, **kwargs):
        self.read_enabled = False
        self.current_section = None
        self.ack_or_nak = None
        self.read_coro = None
        self.hostaddr = kwargs.get('hostaddr')
        self.hostport = kwargs.get('hostport', self.DEFAULT_PORT)
        self.rx_bfr = b''
    async def read_loop(self):
        while self.read_enabled:
            try:
                await self.client.wait_for_data()
            except Exception as e:
                logger.error(e)
                await self._close_client()
                self._catch_exception(e)
                return
            if not self.read_enabled:
                break
            try:
                rx_bfr = await self.client.read_very_eager()
            except Exception as e:
                logger.error(e)
                await self._close_client()
                self._catch_exception(e)
                return
            if len(rx_bfr):
                self.rx_bfr += rx_bfr
                logger.debug(self.rx_bfr.decode('UTF-8'))
                await self.parse_rx_bfr()
                self.rx_bfr = b''
    async def send_to_client(self, data):
        if not self.connected:
            c = await self.connect()
        c = self.client
        if not c:
            return
        s = '\n'.join(['---> {}'.format(line) for line in data.decode('UTF-8').splitlines()])
        logger.debug(s)
        try:
            await c.write(data)
        except Exception as e:
            logger.error(e)
            await self._close_client()
            self._catch_exception(e)
    async def do_connect(self):
        self.ack_or_nak_event = asyncio.Event()
        self.response_ready = asyncio.Event()
        self.rx_bfr = b''
        logger.debug('connecting')
        try:
            c = self.client = await aiotelnetlib.Telnet(self.hostaddr, self.hostport)
        except OSError as e:
            logger.error(e)
            self.client = None
            self._catch_exception(e)
            return False
        self.prelude_parsed = False
        self.read_enabled = True
        self.read_coro = asyncio.ensure_future(self.read_loop(), loop=self.event_loop)
        await self.wait_for_response(prelude=True)
        logger.debug('prelude parsed')
        return c
    async def _close_client(self):
        logger.info('close_client')
        self.read_enabled = False
        self.response_ready.set()
        if self.client is not None:
            try:
                await self.client.close_async()
            except Exception as e:
                logger.error(e)
            self.client = None
        self.connected = False
    async def do_disconnect(self):
        logger.debug('disconnecting')
        self.read_enabled = False
        if self.client is not None:
            await self.client.close_async()
        if self.read_coro is not None:
            await asyncio.wait([self.read_coro], loop=self.event_loop)
            self.read_coro = None
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
                self.ack_or_nak_event.clear()
                logger.debug('ack_or_nak: {}'.format(resp))
                self.ack_or_nak = None
                return resp
    async def wait_for_ack_or_nak(self):
        logger.debug('wait_for_ack_or_nak...')
        await self.ack_or_nak_event.wait()
        resp = self.ack_or_nak
        self.ack_or_nak = None
        self.ack_or_nak_event.clear()
        return resp.startswith('ACK')

class TelnetBackend(TelnetBackendBase, VidhubBackendBase):
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
        super().__init__(**kwargs)
        self._telnet_init(**kwargs)
    def _catch_exception(self, e):
        super()._catch_exception(e)
        if isinstance(e, OSError):
            err = e.args[0]
            if err in [errno.EHOSTUNREACH, errno.ECONNREFUSED]:
                self.connection_unavailable = True
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
                self.ack_or_nak_event.set()
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
                    self.device_id = split_value(line).upper()
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
        async with self.emission_lock('crosspoints'):
            await self.send_to_client(tx_bfr)
            r = await self.wait_for_ack_or_nak()
            if not r:
                return False
            xpts = self.crosspoints[:]
            for out_idx, in_idx in args:
                xpts[out_idx] = in_idx
            self.crosspoints[:] = xpts
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
        async with self.emission_lock('output_labels'):
            await self.send_to_client(tx_bfr)
            r = await self.wait_for_ack_or_nak()
            if not r:
                return False
            lbls = self.output_labels[:]
            for out_idx, label in args:
                lbls[out_idx] = label
            self.output_labels = lbls[:]
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
        async with self.emission_lock('input_labels'):
            await self.send_to_client(tx_bfr)
            r = await self.wait_for_ack_or_nak()
            if not r:
                return False
            lbls = self.input_labels[:]
            for in_idx, label in args:
                lbls[in_idx] = label
            self.input_labels = lbls[:]
        return True

class SmartViewTelnetBackendBase(TelnetBackendBase):
    DEFAULT_PORT = 9992
    SECTION_NAMES = [
        'PROTOCOL PREAMBLE:',
        'SMARTVIEW DEVICE:',
        'NETWORK:',
    ]
    async def parse_rx_bfr(self):
        def split_value(line):
            return line.split(':')[1].strip(' ')
        bfr = self.rx_bfr.decode('UTF-8')
        section_parsed = False
        for line_idx, line in enumerate(bfr.splitlines()):
            line = line.rstrip('\n')
            if not len(line):
                if self.current_section.startswith('MONITOR') and len(self.monitors) == self.num_monitors:
                    self.current_section = None
                    self.rx_bfr = b''
                    self.prelude_parsed = True
                    break
                continue
            if line.startswith('ACK') or line.startswith('NAK'):
                self.ack_or_nak = line
                self.ack_or_nak_event.set()
                if bfr.rstrip('\n') == line:
                    self.current_section = None
                    self.rx_bfr = b''
                    break
                continue
            if line in self.SECTION_NAMES:
                self.current_section = line.rstrip(':')
                continue
            if self.current_section is None:
                continue
            elif self.current_section == 'PROTOCOL PREAMBLE':
                if line.startswith('Version:'):
                    self.device_version = split_value(line)
            elif self.current_section == 'SMARTVIEW DEVICE':
                if line.startswith('Model:'):
                    self.device_model = split_value(line)
                elif line.startswith('Hostname:'):
                    self.device_id = split_value(line).split('-')[1].upper()
                elif line.startswith('Name:'):
                    if self.device_name is None or self.device_name == self.device_id:
                        self.device_name = split_value(line)
                elif line.startswith('Monitors:'):
                    self.num_monitors = int(split_value(line))
                    for c in string.ascii_uppercase[:self.num_monitors]:
                        s = 'MONITOR {}:'.format(c)
                        if s not in self.SECTION_NAMES:
                            self.SECTION_NAMES.append(s)
                elif line.startswith('Inverted:'):
                    self.inverted = split_value(line) == 'true'
            elif self.current_section == 'NETWORK':
                pass
            elif self.current_section.startswith('MONITOR '):
                monitor_name = self.current_section
                await self.parse_monitor_line(monitor_name, line, split_value(line))
            else:
                section_parsed = True
        self.response_ready.set()
        if not self.prelude_parsed:
            return
        if self.current_section is not None and section_parsed:
            self.current_section = None
    async def parse_monitor_line(self, monitor_name, line, value):
        monitor = None
        for _m in self.monitors:
            if _m.name == monitor_name:
                monitor = _m
                break
        if monitor is None:
            monitor = await self.add_monitor(name=monitor_name)
        prop = None
        for key, val in MONITOR_PROPERTY_MAP.items():
            if line.startswith('{}:'.format(val)):
                prop = key
                break
        if prop is None:
            return
        if value.isdigit():
            value = int(value)
        await monitor.set_property_from_backend(prop, value)
    async def set_monitor_property(self, monitor, name, value):
        key = MONITOR_PROPERTY_MAP[name]
        tx_lines = [
            '{}:'.format(monitor.name),
            '{}: {}'.format(key, value),
        ]
        tx_bfr = bytes('\n'.join(tx_lines), 'UTF-8')
        tx_bfr += b'\n\n'
        await self.send_to_client(tx_bfr)
        r = await self.wait_for_ack_or_nak()
        if r:
            await monitor.set_property_from_backend(name, value)
    def _on_monitors(self, *args, **kwargs):
        return

class SmartViewTelnetBackend(SmartViewTelnetBackendBase, SmartViewBackendBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._telnet_init(**kwargs)
    def _catch_exception(self, e):
        super()._catch_exception(e)
        if isinstance(e, OSError):
            err = e.args[0]
            if err in [errno.EHOSTUNREACH, errno.ECONNREFUSED]:
                self.connection_unavailable = True

class SmartScopeTelnetBackend(SmartViewTelnetBackendBase, SmartScopeBackendBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._telnet_init(**kwargs)
    def _catch_exception(self, e):
        super()._catch_exception(e)
        if isinstance(e, OSError):
            err = e.args[0]
            if err in [errno.EHOSTUNREACH, errno.ECONNREFUSED]:
                self.connection_unavailable = True
