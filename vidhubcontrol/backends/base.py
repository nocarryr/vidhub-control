import asyncio

from pydispatch import Dispatcher, Property
from pydispatch.properties import ListProperty, DictProperty

class BackendBase(Dispatcher):
    crosspoints = ListProperty()
    output_labels = ListProperty()
    input_labels = ListProperty()
    device_model = Property()
    device_id = Property()
    device_version = Property()
    num_outputs = Property(0)
    num_inputs = Property(0)
    connected = Property(False)
    running = Property(False)
    prelude_parsed = Property(False)
    def __init__(self, **kwargs):
        self.client = None
        self.event_loop = kwargs.get('event_loop', asyncio.get_event_loop())
        self.bind(
            num_outputs=self.on_num_outputs,
            num_inputs=self.on_num_inputs,
            output_labels=self.on_prop_set,
            input_labels=self.on_prop_set,
            crosspoints=self.on_prop_set,
        )
        asyncio.ensure_future(self.connect(), loop=self.event_loop)
    async def connect(self):
        print('connecting...')
        if self.connected:
            return self.client
        self.connected = True
        r = await self.do_connect()
        print(r)
        if r is False:
            self.connected = False
        else:
            if self.client is not None:
                self.client = r
            print('connected')
        return r
    async def disconnect(self):
        if not self.connected:
            return
        await self.do_disconnect()
        self.client = None
        self.connected = False
    async def do_connect(self):
        raise NotImplementedError()
    async def do_disconnect(self):
        raise NotImplementedError()
    async def get_status(self):
        raise NotImplementedError()
    async def set_crosspoint(self, out_idx, in_idx):
        raise NotImplementedError()
    async def set_crosspoints(self, *args):
        raise NotImplementedError()
    async def set_output_label(self, out_idx, label):
        raise NotImplementedError()
    async def set_output_labels(self, *args):
        raise NotImplementedError()
    async def set_input_label(self, in_idx, label):
        raise NotImplementedError()
    async def set_input_labels(self, *args):
        raise NotImplementedError()
    def on_num_outputs(self, instance, value, **kwargs):
        if value == len(self.output_labels):
            return
        if value != len(self.crosspoints):
            self.crosspoints = [0] * value
        self.output_labels = [''] * value
    def on_num_inputs(self, instance, value, **kwargs):
        if value == len(self.input_labels):
            return
        if value != len(self.crosspoints):
            self.crosspoints = [0] * value
        self.input_labels = [''] * value
    def on_prop_set(self, instance, value, **kwargs):
        pass
        # if not self.connected:
        #     return
        # if not self.prelude_parsed:
        #     return
        # prop = kwargs.get('property')
        # if prop.name in self.pending_properties:
        #     return
        # coro = None
        # args = [(i, v) for i, v in enumerate(value)]
        # if prop.name == 'crosspoints':
        #     coro = self.set_crosspoints
        # elif prop.name == 'output_labels':
        #     coro = self.set_output_labels
        # elif prop.name == 'input_labels':
        #     coro = self.set_input_labels
        # if coro is not None:
        #     asyncio.run_coroutine_threadsafe(coro, *args, loop=self.event_loop)
