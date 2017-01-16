import asyncio

from pydispatch import Dispatcher, Property
from pydispatch.properties import ListProperty, DictProperty

from vidhubcontrol.interfaces.midi import events, mapping

class QueuedMessage(object):
    def __init__(self, midi_event):
        self.midi_event = midi_event
        self.complete = asyncio.Event()
    def __await__(self):
        yield from self.complete.wait()

class MidiChannel(Dispatcher):
    index = Property()
    controller_values = ListProperty([0]*128, copy_on_change=True)
    notes = ListProperty([False]*128, copy_on_change=True)
    rx_enabled = Property(False)
    _events_ = ['on_controller', 'on_note_down', 'on_note_up']
    def __init__(self, *args, **kwargs):
        self.index = kwargs.get('index')
        self.interface = kwargs.get('interface')
        self.bind(
            controller_values=self.on_controller_values,
            notes=self.on_notes,
        )
    def on_controller_values(self, instance, value, **kwargs):
        keys = kwargs.get('keys')
        if keys is None:
            old = kwargs.get('old')
            keys = (i for i, v in enumerate(value) if old[i] != v)
            kwargs['keys'] = keys
        kwargs['channel'] = self
        values = [(key, value[key]) for key in keys]
        self.emit('on_controller', values, **kwargs)
    def on_notes(self, instance, value, **kwargs):
        keys = kwargs.get('keys')
        if keys is None:
            old = kwargs.get('old')
            keys = (i for i, v in enumerate(value) if old[i] != v)
            kwargs['keys'] = keys
        kwargs['channel'] = self
        notes_down = [key for key in keys if value[key]]
        notes_up = [key for key in keys if not value[key]]
        if len(notes_down):
            self.emit('on_note_down', notes_down, **kwargs)
        if len(notes_up):
            self.emit('on_note_up', notes_up, **kwargs)

class MidiInputChannel(MidiChannel):
    async def on_midi_event_received(self, midi_event, *args, **kwargs):
        if isinstance(midi_event, events.NoteEvent):
            value = isinstance(midi_event, events.NoteDownEvent)
            key = midi_event.value
            self.notes[key] = value
        elif isinstance(midi_event, events.ControllerEvent):
            self.controller_values[midi_event.controller] = midi_event.value

class MidiOutputChannel(MidiChannel):
    tx_enabled = Property(False)
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(
            on_controller=self.on_controller_event,
            on_note_down=self.on_note_down_event,
            on_note_up=self.on_note_up_event,
        )
    def on_controller_event(self, values, **kwargs):
        if not self.tx_enabled:
            return
        for controller, value in values:
            midi_event = events.ControllerEvent(
                channel=self.index,
                controller=controller,
                value=value,
            )
            self.interface.queue_message(midi_event)
    def on_note_down_event(self, notes_down, **kwargs):
        if not self.tx_enabled:
            return
        for note in notes_down:
            midi_event = events.NoteDownEvent(
                channel=self.index,
                value=note,
                velocity=100,
            )
            self.interface.queue_message(midi_event)
    def on_note_up_event(self, notes_up, **kwargs):
        if not self.tx_enabled:
            return
        for note in notes_up:
            midi_event = events.NoteUpEvent(
                channel=self.index,
                value=note,
                velocity=100,
            )
            self.interface.queue_message(midi_event)

class MidiInterfaceBase(Dispatcher):
    input_channels = DictProperty()
    output_channels = DictProperty()
    mappings = ListProperty()
    def __init__(self, *args, **kwargs):
        self.mappings = kwargs.get('mappings', [])
        self.event_tx_queue = asyncio.Queue()
        self.event_rx_queue = asyncio.Queue()
        self.running = False
        for i in range(16):
            ch = MidiInputChannel(index=i, interface=self)
            self.input_channels[i] = ch
            ch = MidiOutputChannel(index=i, interface=self)
            self.output_channels[i] = ch
    async def start(self, loop=None):
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop
        self.running = True
        self.run_coro = asyncio.ensure_future(self.run(), loop=loop)
    def get_io_loop_coroutines(self):
        async def io_loop(q, callback):
            while self.running:
                data = await q.get()
                q.task_done()
                if data is None:
                    break
                await callback(data)
        return [
            io_loop(self.event_rx_queue, self.process_rx_messages),
            io_loop(self.event_tx_queue, self.send_midi_data),
        ]
        return io_loop_coros
    async def run(self):
        io_loop_coros = self.get_io_loop_coroutines()
        await asyncio.wait(io_loop_coros)
    async def stop(self):
        self.running = False
        await self.event_tx_queue.put(None)
        await self.event_rx_queue.put(None)
        await self.run_coro
    async def dispatch_mappings(self, midi_event, **kwargs):
        for mapping in self.mappings:
            await mapping(midi_event)
    def queue_message(self, midi_event):
        msg = QueuedMessage(midi_event)
        self.event_tx_queue.put_nowait(msg)
        return msg
    async def send_message(self, midi_event):
        msg = QueuedMessage(midi_event)
        await self.event_tx_queue.put(msg)
        await msg
    async def send_midi_data(self, message):
        raise NotImplementedError()
    async def process_rx_messages(self, data):
        port_name, data = data
        for midi_event in events.MidiEvent.parse_stream(data):
            #print('RX ({}): {!r}'.format(port_name, midi_event))
            await self.dispatch_mappings(midi_event)
            if isinstance(midi_event, events.MidiChannelEvent):
                ch = self.input_channels[midi_event.channel]
            else:
                ch = self.input_channels[0]
            if not ch.rx_enabled:
                continue
            await ch.on_midi_event_received(midi_event)

class MidiInterface(MidiInterfaceBase):
    vidhubs = DictProperty()
    vidhubs_id_map = DictProperty()
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        for ch in self.input_channels.values():
            ch.bind(
                on_controller=self.on_input_controller,
                on_note_down=self.on_input_note_down,
                on_note_up=self.on_input_note_up,
            )
    async def add_vidhub(self, vidhub, midi_channel):
        self.vidhubs[midi_channel] = vidhub
        self.vidhubs_id_map[vidhub.device_id] = midi_channel
        self.input_channels[midi_channel].rx_enabled = False
        ch = self.output_channels[midi_channel]
        for out_idx, in_idx in enumerate(vidhub.crosspoints):
            ch.controller_values[out_idx] = in_idx
            e = events.ControllerEvent(channel=ch.index, controller=out_idx, value=in_idx)
            await self.send_message(e)
        active_presets = [preset.index for preset in vidhub.presets if preset.active]
        for i in range(128):
            active = i in active_presets
            ch.notes[i] = active
            if active:
                cls = events.NoteDownEvent
            else:
                cls = events.NoteUpEvent
            e = cls(channel=ch.index, value=i, velocity=100)
            await self.send_message(e)
        ch.tx_enabled = True
        self.input_channels[midi_channel].rx_enabled = True
        vidhub.bind(
            crosspoints=self.on_vidhub_crosspoints,
            on_preset_active=self.on_vidhub_preset_active,
        )
    def on_input_controller(self, controllers, **kwargs):
        if len(self.mappings):
            return
        ch = kwargs.get('channel')
        vidhub = self.vidhubs.get(ch.index)
        if vidhub is None:
            return
        asyncio.ensure_future(vidhub.set_crosspoints(*controllers))
    def on_input_note_down(self, notes, **kwargs):
        if len(self.mappings):
            return
        ch = kwargs.get('channel')
        vidhub = self.vidhubs.get(ch.index)
        if vidhub is None:
            return
        for preset_index in notes:
            if preset_index > 63:
                # Store
                preset_index -= 63
                asyncio.ensure_future(vidhub.store_preset(index=preset_index), loop=vidhub.event_loop)
            else:
                # Recall
                try:
                    preset = vidhub.presets[preset_index]
                except IndexError:
                    preset = None
                if preset is None:
                    continue
                asyncio.ensure_future(preset.recall(), loop=vidhub.event_loop)
    def on_input_note_up(self, notes, **kwargs):
        pass
    def on_vidhub_crosspoints(self, instance, value, **kwargs):
        ch_index = self.vidhubs_id_map.get(instance.device_id)
        if ch_index is None:
            return
        keys = kwargs.get('keys')
        if keys is None:
            keys = range(len(value))
        ch = self.output_channels[ch_index]
        for key in keys:
            ch.controller_values[key] = value[key]
    def on_vidhub_preset_active(self, *args, **kwargs):
        instance = kwargs.get('backend')
        preset = kwargs.get('preset')
        is_active = kwargs.get('value')
        ch_index = self.vidhubs_id_map.get(instance.device_id)
        if ch_index is None:
            return
        ch = self.output_channels[ch_index]
        ch.notes[preset.index] = is_active
