from pydispatch import Dispatcher, Property
from pydispatch.properties import ListProperty, DictProperty

class MidiChannel(Dispatcher):
    index = Property()
    controller_values = ListProperty([0]*128, copy_on_change=True)
    notes = ListProperty([False]*128, copy_on_change=True)
    _events_ = ['on_controller', 'on_note_down', 'on_note_up']
    def __init__(self, *args, **kwargs):
        self.index = kwargs.get('index')
        self.bind(
            controller_values=self.on_controller_values,
            notes=self.on_notes,
        )
    def on_controller_values(self, instance, value, **kwargs):
        keys = kwargs.get('keys')
        if keys is None:
            old = kwargs.get('old')
            keys = (i for i, v in enumerate(value) if old[i] != v)
        values = [(key, value[key]) for key in keys]
        self.emit('on_controller', values, channel=self)
    def on_notes(self, instance, value, **kwargs):
        keys = kwargs.get('keys')
        if keys is None:
            old = kwargs.get('old')
            keys = (i for i, v in enumerate(value) if old[i] != v)
        notes_down = [key for key in keys if value[key]]
        notes_up = [key for key in keys if not value[key]]
        if len(notes_down):
            self.emit('on_note_down', notes_down, channel=self)
        if len(notes_up):
            self.emit('on_note_up', notes_up, channel=self)

class MidiInputChannel(MidiChannel):
    pass

class MidiOutputChannel(MidiChannel):
    pass

class MidiInterface(Dispatcher):
    input_channels = DictProperty()
    output_channels = DictProperty()
    vidhubs = DictProperty()
    vidhubs_id_map = DictProperty()
    def __init__(self, *args, **kwargs):
        for i in range(16):
            ch = MidiInputChannel(index=i)
            self.input_channels[i] = ch
            ch.bind(
                on_controller=self.on_input_controller,
                on_note_down=self.on_input_note_down,
                on_note_up=self.on_input_note_up,
            )
            ch = MidiOutputChannel(index=i)
            self.output_channels[i] = ch
    def add_vidhub(self, vidhub, midi_channel):
        self.vidhubs[midi_channel] = vidhub
        self.vidhubs_id_map[vidhub.device_id] = midi_channel
        ch = self.output_channels[midi_channel]
        for out_idx, in_idx in enumerate(vidhub.crosspoints):
            ch.controller_values[out_idx] = in_idx
        active_presets = [preset.index for preset in vidhub.presets if preset.active]
        ch.notes = [i in active_presets for i in range(128)]
        vidhub.bind(
            crosspoints=self.on_vidhub_crosspoints,
            on_preset_active=self.on_vidhub_preset_active,
        )
    def on_input_controller(self, controllers, **kwargs):
        ch = kwargs.get('channel')
        vidhub = self.vidhubs.get(ch.index)
        if vidhub is None:
            return
        vidhub.set_crosspoints(*controllers)
    def on_input_note_down(self, notes, **kwargs):
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
