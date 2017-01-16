import jsonfactory

from pydispatch import Dispatcher, Property

from vidhubcontrol.interfaces.midi import events

class MapAction(Dispatcher):
    def __init__(self, **kwargs):
        pass
    def _serialize(self):
        return {'__class__':'.'.join([
            self.__class__.__module__, self.__class__.__qualname__
        ])}

class CrosspointAction(MapAction):
    output_index = Property()
    input_index = Property()
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.output_index = kwargs.get('output_index')
        self.input_index = kwargs.get('input_index')
    async def __call__(self, mapping, midi_event):
        out_idx = self.output_index
        in_idx = self.input_index
        if in_idx is None:
            in_idx = midi_event.value
        await mapping.vidhub.set_crosspoint(out_idx, in_idx)
    def _serialize(self):
        d = super()._serialize()
        d.update({k:getattr(self, k) for k in ['output_index', 'input_index']})
        return d

class PresetAction(MapAction):
    preset_index = Property()
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.preset_index = kwargs.get('preset_index')
    def _serialize(self):
        d = super()._serialize()
        d['preset_index'] = self.preset_index
        return d

class PresetRecallAction(PresetAction):
    async def __call__(self, mapping, midi_event):
        preset_index = self.preset_index
        if preset_index is None:
            preset_index = midi_event.value
        try:
            preset = mapping.vidhub.presets[preset_index]
        except IndexError:
            preset = None
        if preset is None:
            return
        await preset.recall()

class PresetRecordAction(PresetAction):
    async def __call__(self, mapping, midi_event):
        preset_index = self.preset_index
        if preset_index is None:
            preset_index = midi_event.value
        await mapping.vidhub.store_preset(index=preset_index)

class MidiMapping(Dispatcher):
    midi_event = Property()
    action = Property()
    vidhub = Property()
    vidhub_id = Property()
    def __init__(self, **kwargs):
        self.midi_event = kwargs.get('midi_event')
        self.action = kwargs.get('action')
        self.vidhub_id = kwargs.get('vidhub_id')
        self.vidhub = kwargs.get('vidhub')
        if self.vidhub_id is None:
            if self.vidhub is not None:
                self.vidhub_id = self.vidhub.device_id
        self.bind(vidhub=self.on_vidhub)
    async def __call__(self, midi_event):
        if self.vidhub is None:
            return
        if self.midi_event is None:
            return
        if self.action is None:
            return
        if not midi_event.is_same_message_type(self.midi_event):
            return
        await self.action(self, midi_event)
    def on_vidhub(self, instance, value, **kwargs):
        if value is None:
            self.vidhub_id = None
        else:
            self.vidhub_id = value.device_id
    def _serialize(self):
        d = {'__class__':'.'.join([
            self.__class__.__module__, self.__class__.__qualname__
        ])}
        attrs = ['midi_event', 'action', 'vidhub_id']
        d.update({k:getattr(self, k) for k in attrs})
        return d

@jsonfactory.register
class JsonHandler(object):
    classes = (
        CrosspointAction,
        PresetAction,
        PresetRecallAction,
        PresetRecordAction,
        MidiMapping,
    )
    classes_by_name = {'.'.join([c.__module__, c.__qualname__]):c for c in classes}
    def encode(self, o):
        if isinstance(o, self.classes):
            return o._serialize()
    def decode(self, d):
        if '__class__' in d:
            cls = self.classes_by_name.get(d['__class__'])
            if cls is not None:
                return cls(**d)
        return d
