import asyncio
import logging

from . import VidhubBackendBase, SmartViewBackendBase, SmartScopeBackendBase

class DummyBackend(VidhubBackendBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.device_id = kwargs.get('device_id', 'dummy')
    async def do_connect(self):
        self.num_outputs = 12
        self.num_inputs = 12
        self.output_labels = ['Output {}'.format(i+1) for i in range(self.num_outputs)]
        self.input_labels = ['Input {}'.format(i+1) for i in range(self.num_inputs)]
        self.prelude_parsed = True
        return True
    async def do_disconnect(self):
        pass # pragma: no cover
    async def get_status(self):
        pass # pragma: no cover
    async def set_crosspoint(self, out_idx, in_idx):
        return await self.set_crosspoints((out_idx, in_idx))
    async def set_crosspoints(self, *args):
        async with self.emission_lock('crosspoints'):
            for out_idx, in_idx in args:
                self.crosspoints[out_idx] = in_idx
    async def set_output_label(self, out_idx, lbl):
        return await self.set_output_labels((out_idx, lbl))
    async def set_output_labels(self, *args):
        async with self.emission_lock('output_labels'):
            for out_idx, lbl in args:
                self.output_labels[out_idx] = lbl
    async def set_input_label(self, in_idx, lbl):
        return await self.set_input_labels((in_idx, lbl))
    async def set_input_labels(self, *args):
        async with self.emission_lock('input_labels'):
            for in_idx, lbl in args:
                self.input_labels[in_idx] = lbl

class SmartViewDummyBackend(SmartViewBackendBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.device_id = kwargs.get('device_id', 'dummy_smartview')
    async def do_connect(self):
        for name in ['MONITOR A', 'MONITOR B']:
            await self.add_monitor(
                name=name,
                brightness=255,
                contrast=128,
                saturation=128,
                widescreen_sd='auto',
                audio_channel=0,
                identify='false',
                border='NONE',
            )
        self.prelude_parsed = True
        return True
    async def do_disconnect(self):
        pass # pragma: no cover
    async def get_status(self):
        pass # pragma: no cover
    async def set_monitor_property(self, monitor, name, value):
        await monitor.set_property_from_backend(name, value)

class SmartScopeDummyBackend(SmartScopeBackendBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.device_id = kwargs.get('device_id', 'dummy_smartscope')
    async def do_connect(self):
        for name, mode in [['MONITOR A', 'waveform'], ['MONITOR B', 'vector_100']]:
            await self.add_monitor(
                name=name,
                brightness=255,
                contrast=128,
                saturation=128,
                widescreen_sd='auto',
                audio_channel=0,
                identify='false',
                border='NONE',
                mode=mode,
            )
        self.prelude_parsed = True
        return True
    async def do_disconnect(self):
        pass # pragma: no cover
    async def get_status(self):
        pass # pragma: no cover
    async def set_monitor_property(self, monitor, name, value):
        await monitor.set_property_from_backend(name, value)
