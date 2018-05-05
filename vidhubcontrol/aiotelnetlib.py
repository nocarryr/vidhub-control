import asyncio
import telnetlib

_DEFAULT_LIMIT = 2 ** 16

class ReaderProtocol(asyncio.streams.StreamReaderProtocol):
    def __init__(self, stream_reader, client_connected_cb=None, loop=None):
        super().__init__(stream_reader, client_connected_cb, loop)
        self.read_ready_event = asyncio.Event()
    def data_received(self, data):
        super().data_received(data)
        print('data_received')
        self.read_ready_event.set()

async def open_connection(host=None, port=None, *,
                          loop=None, limit=_DEFAULT_LIMIT, **kwds):
    if loop is None:
        loop = asyncio.get_event_loop()
    reader = asyncio.streams.StreamReader(limit=limit, loop=loop)
    protocol = ReaderProtocol(reader, loop=loop)
    transport, _ = await loop.create_connection(
        lambda: protocol, host, port, **kwds)
    writer = asyncio.streams.StreamWriter(transport, protocol, reader, loop)
    return reader, writer

class FakeSocket(object):
    '''Fake socket operations to avoid implementing Telnet.process_rawq
    '''
    def __init__(self, tn):
        self.telnet = tn
        self.running = False
        self.tx_queue = asyncio.Queue()
    async def run(self):
        self.running = True
        while self.running:
            data = await self.tx_queue.get()
            if data is None:
                break
            self.tx_queue.task_done()
            self.telnet.writer.write(data)
            await self.telnet.writer.drain()
    def close(self):
        self.running = False
        self.tx_queue.put_nowait(None)
    def sendall(self, data):
        self.tx_queue.put_nowait(data)

class _Telnet(telnetlib.Telnet):
    def __init__(self, host=None, port=0, timeout=0, loop=None):
        self.loop = loop
        self.reader = None
        self.writer = None
        super().__init__(timeout=timeout)

    async def open(self, host, port=0, timeout=0, loop=None):
        if not loop and not self.loop:
            loop = self.loop = asyncio.get_event_loop()
        self.eof = 0
        if not port:
            port = telnetlib.TELNET_PORT
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = FakeSocket(self)
        self.sock_fut = asyncio.ensure_future(self.sock.run())
        try:
            self.reader, self.writer = await open_connection(host, port, loop=loop)
        except:
            self.sock.close()
            await self.sock_fut
            self.sock = None
            raise

    def close(self):
        super().close()
        if self.writer:
            self.writer.close()
        if self.reader:
            self.reader._transport._protocol.read_ready_event.set()
        self.reader = None
        self.writer = None

    async def close_async(self):
        if self.sock:
            self.sock.close()
            await asyncio.wait([self.sock_fut])
        self.sock = None
        self.close()

    async def write(self, bfr):
        if telnetlib.IAC in bfr:
            bfr = bfr.replace(telnetlib.IAC, telnetlib.IAC+telnetlib.IAC)
        self.msg("send %r", bfr)
        self.writer.write(bfr)
        await self.writer.drain()

    async def wait_for_data(self):
        await self.reader._transport._protocol.read_ready_event.wait()

    async def read_until(self, match, timeout=None):
        """Read until a given string is encountered or until timeout.

        When no match is found, return whatever is available instead,
        possibly the empty string.  Raise EOFError if the connection
        is closed and no cooked data is available.

        """
        n = len(match)
        self.process_rawq()
        i = self.cookedq.find(match)
        if i >= 0:
            i = i+n
            buf = self.cookedq[:i]
            self.cookedq = self.cookedq[i:]
            return buf
        if timeout is not None:
            deadline = telnetlib._time() + timeout

        while not self.eof:
            if len(self.reader._buffer):
                i = max(0, len(self.cookedq)-n)
                await self.fill_rawq()
                self.process_rawq()
                i = self.cookedq.find(match, i)
                if i >= 0:
                    i = i+n
                    buf = self.cookedq[:i]
                    self.cookedq = self.cookedq[i:]
                    return buf
            if timeout is not None:
                timeout = deadline - telnetlib._time()
                if timeout < 0:
                    break
        return self.read_very_lazy()

    async def read_all(self):
        """Read all data until EOF; block until connection closed."""
        self.process_rawq()
        while not self.eof:
            await self.fill_rawq()
            self.process_rawq()
        buf = self.cookedq
        self.cookedq = b''
        return buf

    async def read_some(self):
        """Read at least one byte of cooked data unless EOF is hit.

        Return b'' if EOF is hit.  Block if no data is immediately
        available.

        """
        self.process_rawq()
        while not self.cookedq and not self.eof:
            await self.fill_rawq()
            self.process_rawq()
        buf = self.cookedq
        self.cookedq = b''
        return buf

    async def read_very_eager(self):
        """Read everything that's possible without blocking in I/O (eager).

        Raise EOFError if connection closed and no cooked data
        available.  Return b'' if no cooked data available otherwise.
        Don't block unless in the midst of an IAC sequence.

        """
        self.process_rawq()
        while not self.eof and self.sock_avail():
            await self.fill_rawq()
            self.process_rawq()
        return self.read_very_lazy()

    async def read_eager(self):
        """Read readily available data.

        Raise EOFError if connection closed and no cooked data
        available.  Return b'' if no cooked data available otherwise.
        Don't block unless in the midst of an IAC sequence.

        """
        self.process_rawq()
        while not self.cookedq and not self.eof and self.sock_avail():
            await self.fill_rawq()
            self.process_rawq()
        return self.read_very_lazy()

    async def fill_rawq(self):
        """Fill raw queue from exactly one recv() system call.

        Block if no data is immediately available.  Set self.eof when
        connection is closed.

        """
        if self.irawq >= len(self.rawq):
            self.rawq = b''
            self.irawq = 0
        # The buffer size should be fairly small so as to avoid quadratic
        # behavior in process_rawq() above
        buf = await self.reader.read(50)
        self.msg("recv %r", buf)
        self.eof = (not buf)
        self.rawq = self.rawq + buf

    def sock_avail(self):
        """Test whether data is available on the socket."""
        r = len(self.reader._buffer) > 0
        if not r:
            self.reader._transport._protocol.read_ready_event.clear()
        return r

async def Telnet(host=None, port=0, timeout=0, loop=None):
    '''Wrap the init in a coroutine so ``open`` can be awaited
    '''
    tn = _Telnet(host, port, timeout, loop)
    if host is not None:
        await tn.open(host, port, timeout, loop)
    return tn
