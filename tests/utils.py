import random
import string
import asyncio

def random_string(num_chars=8):
    return ''.join((random.choice(string.printable) for i in range(num_chars)))

def get_random_values(n, value_type=None):
    if value_type is None:
        value_type = random.choice([str, int, float])
    if value_type is str:
        s = set((random_string() for i in range(n)))
        while len(s) < n:
            s.add(random_string())
    elif value_type is int:
        maxint = 100
        if n > maxint:
            maxint = n * 4
        s = set((random.randint(0, maxint) for i in range(n)))
        while len(s) < n:
            s.add(random.randint(0, maxint))
    elif value_type is float:
        s = set((random.random() * 100. for i in range(n)))
        while len(s) < n:
            s.add(random.random() * 100.)
    return s

class AsyncEventWaiter(object):
    def __init__(self, obj):
        self.obj = obj
        self._event = asyncio.Event()
        self._lock = asyncio.Lock()
        self.args = None
        self.kwargs = None
    def bind(self, event_name):
        self.obj.bind(**{event_name:self.on_event})
    def unbind(self):
        self.obj.unbind(self)
    def on_event(self, *args, **kwargs):
        async def trigger(_args, _kwargs):
            async with self._lock:
                self.args = _args
                self.kwargs = _kwargs
            self._event.set()
        asyncio.ensure_future(trigger(args, kwargs))
    async def wait(self):
        await self._event.wait()
        async with self._lock:
            args, kwargs = self.args, self.kwargs
            self.args = None
            self.kwargs = None
        self._event.clear()
        return args, kwargs
