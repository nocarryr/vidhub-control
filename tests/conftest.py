import os
import socket
import asyncio
import errno
import contextlib

import pytest

def get_vidhub_preamble():
    p = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(p, 'vidhub-preamble.txt'), 'rb') as f:
        s = f.read()
    assert type(s) is bytes
    return s

def get_smartview_preamble():
    p = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(p, 'smartview-preamble.txt'), 'rb') as f:
        s = f.read()
    assert type(s) is bytes
    return s

def get_smartscope_preamble():
    p = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(p, 'smartscope-preamble.txt'), 'rb') as f:
        s = f.read()
    assert type(s) is bytes
    return s

TELNET_HOSTADDR_GOOD = '127.0.0.1'
TELNET_HOSTADDR_BAD = '0.0.0.0'

VIDHUB_PREAMBLE = get_vidhub_preamble()
VIDHUB_DEVICE_ID = 'a0b2c3d4e5f6'
VIDHUB_PORT = 9990

SMARTVIEW_PREAMBLE = get_smartview_preamble()
SMARTVIEW_DEVICE_ID = 'a10203040506'
SMARTVIEW_PORT = 9991

SMARTSCOPE_PREAMBLE = get_smartscope_preamble()
SMARTSCOPE_DEVICE_ID = '0a1b2c3d4e5f'
SMARTSCOPE_PORT = 9992

PREAMBLES = {
    'vidhub':VIDHUB_PREAMBLE,
    'smartview':SMARTVIEW_PREAMBLE,
    'smartscope':SMARTSCOPE_PREAMBLE,
}

@pytest.fixture
def vidhub_telnet_responses():
    d = {
        'preamble':VIDHUB_PREAMBLE,
        'nak':b'NAK\n\n',
        'ack':b'ACK\n\n',
    }
    change_fmt = b'ACK\n\n{command}:\n{changes}\n'
    def get_change_response(command, *args):
        changes = []
        for out_idx, val in args:
            routes.append(b'{} {}'.format(out_idx, val))
        changes = b'\n'.join(changes)
        return change_fmt.format(command=command, changes=changes)
    def get_output_routing(*args):
        return get_change_response(b'VIDEO OUTPUT ROUTING', *args)
    def get_input_routing(*args):
        return get_change_response(b'VIDEO INPUT ROUTING', *args)
    def get_output_labels(*args):
        return get_change_response(b'OUTPUT LABELS', *args)
    def get_input_labels(*args):
        return get_change_response(b'INPUT LABELS', *args)

    d.update(dict(
        output_routing=get_output_routing,
        input_routing=get_input_routing,
        output_labels=get_output_labels,
        input_labels=get_input_labels,
    ))

    return d

@pytest.fixture
def vidhub_zeroconf_info():
    d = {
        'device_name':'Smart Videohub 12x12',
        'device_id':VIDHUB_DEVICE_ID.upper(),
        'info_args':['_blackmagic._tcp.local.', 9990],
        'info_kwargs':{
            'type_':'_blackmagic._tcp.local.',
            'port':VIDHUB_PORT,
            'name':'Smart Videohub 12x12-{}._blackmagic._tcp.local.'.format(VIDHUB_DEVICE_ID.upper()),
            'addresses':[b'\x7f\x00\x00\x01'],
            'properties':{
                b'name':b'Smart Videohub 12x12',
                b'protocol version':b'2.7',
                b'class':b'Videohub',
                b'unique id':VIDHUB_DEVICE_ID.encode(),
            },
        },
    }
    return d

@pytest.fixture
def smartview_zeroconf_info():
    d = {
        'device_name':'SmartView Something',
        'device_id':SMARTVIEW_DEVICE_ID.upper(),
        'info_args':['_blackmagic._tcp.local.', SMARTVIEW_PORT],
        'info_kwargs':{
            'type_':'_blackmagic._tcp.local.',
            'port':SMARTVIEW_PORT,
            'name':'SmartView Something-{}._blackmagic._tcp.local.'.format(SMARTVIEW_DEVICE_ID.upper()),
            'addresses':[b'\x7f\x00\x00\x01'],
            'properties':{
                b'name':b'SmartView Something',
                b'protocol version':b'1.3',
                b'class':b'SmartView',
                b'unique id':SMARTVIEW_DEVICE_ID.encode(),
            },
        },
    }
    return d

@pytest.fixture
def smartscope_zeroconf_info():
    d = {
        'device_name':'SmartScope Duo',
        'device_id':SMARTSCOPE_DEVICE_ID.upper(),
        'info_args':['_blackmagic._tcp.local.', SMARTSCOPE_PORT],
        'info_kwargs':{
            'type_':'_blackmagic._tcp.local.',
            'port':SMARTSCOPE_PORT,
            'name':'SmartScope Duo-{}._blackmagic._tcp.local.'.format(SMARTSCOPE_DEVICE_ID.upper()),
            'addresses':[b'\x7f\x00\x00\x01'],
            'properties':{
                b'name':b'SmartScope Duo 4K',
                b'protocol version':b'1.3',
                b'class':b'SmartView',
                b'unique id':SMARTSCOPE_DEVICE_ID.encode(),
            },
        },
    }
    return d

@pytest.fixture
def mocked_vidhub_telnet_device(monkeypatch, vidhub_telnet_responses):
    class Telnet(object):
        preamble = 'vidhub'
        disabled_ports = set()
        port_map = {
            'vidhub':VIDHUB_PORT,
            'smartview':SMARTVIEW_PORT,
            'smartscope':SMARTSCOPE_PORT,
        }
        def __init__(self, host=None, port=None, timeout=None, loop=None):
            self.host = host
            self.port = port
            self.loop = loop
            self.rx_bfr = b''
            self.tx_bfr = b''
            self.read_ready_event = asyncio.Event()
            self.tx_lock = asyncio.Lock()
        @property
        def port(self):
            return getattr(self, '_port', None)
        @port.setter
        def port(self, value):
            self._port = value
            for key, port in self.port_map.items():
                if value == port:
                    self.preamble = key
        @classmethod
        def set_port_enable(cls, port, value):
            if value:
                cls.disabled_ports.discard(port)
            else:
                cls.disabled_ports.add(port)
        async def open(self, host, port=0, timeout=0, loop=None):
            if self.port is None:
                self.port = port
            self.port
            if port in Telnet.disabled_ports:
                await asyncio.sleep(3)
                return
            if self.host == TELNET_HOSTADDR_BAD:
                # Raise a fake 'Connect call failed' exception
                raise OSError(errno.EHOSTUNREACH, (self.host, self.port))
            if not loop and not self.loop:
                loop = self.loop = asyncio.get_event_loop()
            async with self.tx_lock:
                self.tx_bfr = PREAMBLES[self.preamble]
                self.read_ready_event.set()
        def close(self):
            self.read_ready_event.set()
        async def close_async(self):
            self.close()
        async def wait_for_data(self):
            await self.read_ready_event.wait()
        async def write(self, bfr):
            if self.port in Telnet.disabled_ports:
                raise OSError(errno.ECONNREFUSED, (self.host, self.port))
            self.rx_bfr = b''.join([self.rx_bfr, bfr])
            if bfr.endswith(b'\n\n'):
                bfr = self.rx_bfr
                self.rx_bfr = b''
                await self.process_command(bfr)
        async def process_command(self, bfr):
            async with self.tx_lock:
                if self.preamble == 'vidhub':
                    tx_bfr = b''.join([vidhub_telnet_responses['ack'], bfr])
                else:
                    tx_bfr = vidhub_telnet_responses['ack']
                self.tx_bfr = b''.join([self.tx_bfr, tx_bfr])
                if len(self.tx_bfr):
                    self.read_ready_event.set()
        async def read_very_eager(self):
            if self.port in Telnet.disabled_ports:
                raise OSError(errno.ECONNREFUSED, (self.host, self.port))
            async with self.tx_lock:
                bfr = self.tx_bfr
                self.tx_bfr = b''
                self.read_ready_event.clear()
                return bfr

    monkeypatch.setattr('vidhubcontrol.aiotelnetlib._Telnet', Telnet)
    monkeypatch.setattr('vidhubcontrol.backends.telnet.aiotelnetlib._Telnet', Telnet)
    return Telnet

@pytest.fixture
def telnet_backend_factory(mocked_vidhub_telnet_device):
    from vidhubcontrol.backends.telnet import (
        TelnetBackend, SmartViewTelnetBackend, SmartScopeTelnetBackend
    )

    def inner(backend_name):
        d = {'backend_name':backend_name, 'kwargs':{'hostaddr':True}}
        if backend_name == 'vidhub':
            d['cls'] = TelnetBackend
            d['kwargs']['hostport'] = VIDHUB_PORT
            d.update({
                'device_id':VIDHUB_DEVICE_ID,
                'device_model':'Smart Videohub 12x12',
                'device_name':'Smart Videohub 12x12',
            })
        elif backend_name == 'smartview':
            d['cls'] = SmartViewTelnetBackend
            d['kwargs']['hostport'] = SMARTVIEW_PORT
            d.update({
                'device_id':SMARTVIEW_DEVICE_ID,
                'device_model':'SmartView Something',
                'device_name':'SmartView Something',
            })
        elif backend_name == 'smartscope':
            d['cls'] = SmartScopeTelnetBackend
            d['kwargs']['hostport'] = SMARTSCOPE_PORT
            d.update({
                'device_id':SMARTSCOPE_DEVICE_ID,
                'device_model':'SmartScope Duo 4K',
                'device_name':'SmartScope Duo',
            })
        return d
    return inner

@pytest.fixture
def tempconfig(tmpdir):
    return tmpdir.join('vidhubcontrol.json')

@pytest.fixture(params=[False, True])
def missing_netifaces(request, monkeypatch):
    import zeroconf
    import netifaces
    if request.param:
        monkeypatch.setattr('vidhubcontrol.discovery.ZEROCONF_AVAILABLE', False)
        monkeypatch.setattr('vidhubcontrol.utils.NETIFACES_AVAILABLE', False)
    else:
        monkeypatch.setattr('vidhubcontrol.discovery.ZEROCONF_AVAILABLE', True)
        monkeypatch.setattr('vidhubcontrol.utils.NETIFACES_AVAILABLE', True)

def _unused_udp_port():
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]

@pytest.fixture(scope='session')
def unused_udp_port_factory():
    produced = set()

    def factory():
        port = _unused_udp_port()
        while port in produced:
            port = _unused_udp_port()
        produced.add(port)
        return port
    return factory

@pytest.fixture
def unused_udp_port(unused_udp_port_factory):
    return unused_udp_port_factory()
