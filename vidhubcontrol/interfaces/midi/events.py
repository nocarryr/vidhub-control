import jsonfactory

from pydispatch import Dispatcher, Property
from pydispatch.properties import ListProperty


class MidiEvent(Dispatcher):
    status_msb = None
    data_bytes = 1
    all_status_msb = None
    @classmethod
    def iter_subclasses(cls):
        yield cls
        for subcls in cls.__subclasses__():
            yield subcls
            yield from subcls.iter_subclasses()
    @classmethod
    def parse_stream(cls, data):
        if not MidiEvent.all_status_msb:
            MidiEvent.all_status_msb = {}
            for _cls in MidiEvent.iter_subclasses():
                if _cls.status_msb is None:
                    continue
                MidiEvent.all_status_msb[_cls.status_msb] = _cls
        def iter_status_bytes():
            sysex_found = False
            for i, b in enumerate(data):
                if sysex_found:
                    if b == 0xF7:
                        sysex = data[sysex_start:i+1]
                        yield i, None, sysex
                        sysex_found = False
                    else:
                        continue
                if b == 0xF0:
                    sysex_found = True
                    sysex_start = i
                    continue
                if not b & 0x80:
                    continue
                yield i, b, None
        for i, status_byte, sysex_data in iter_status_bytes():
            if sysex_data is not None:
                yield SysExEvent(data=sysex_data)
                continue
            status_msb = status_byte & 0xF0
            msg_cls = MidiEvent.all_status_msb.get(status_msb)
            if msg_cls is None:
                continue
            msg_bytes = data[i:i+msg_cls.data_bytes+1]
            yield msg_cls.parse_message(msg_bytes)
    @classmethod
    def parse_message(cls, msg_bytes):
        raise NotImplementedError()
    def build_message(self):
        raise NotImplementedError()
    def _serialize(self):
        return {'__class__':'.'.join([
            self.__class__.__module__, self.__class__.__qualname__
        ])}
    def __repr__(self):
        return '<{self.__class__.__name__}> {self}'.format(self=self)

class MidiChannelEvent(MidiEvent):
    channel = Property()
    value = Property()
    def __init__(self, **kwargs):
        self.channel = kwargs.get('channel')
        self.value = kwargs.get('value')
    @classmethod
    def parse_message(cls, msg_bytes, **kwargs):
        kwargs['channel'] = msg_bytes[0] - cls.status_msb
        kwargs.setdefault('value', msg_bytes[-1])
        return cls(**kwargs)
    def build_message(self):
        msg = [0] * (self.data_bytes + 1)
        msg[0] = self.status_msb + self.channel
        msg[1] = self.value
        return msg
    def is_same_message_type(self, other):
        if self.__class__ is not other.__class__:
            return False
        if self.channel != other.channel:
            return False
        return True
    def __eq__(self, other):
        if self.__class__ is not other.__class__:
            return NotImplemented
        if self.channel != other.channel:
            return False
        if self.value != other.value:
            return False
        return True
    def _serialize(self):
        d = super()._serialize()
        d.update({'channel':self.channel, 'value':self.value})
        return d
    def __str__(self):
        return 'ch {self.channel}: {self.value}'.format(self=self)

class NoteEvent(MidiChannelEvent):
    data_bytes = 2
    velocity = Property()
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.velocity = kwargs.get('velocity')
    def build_message(self):
        msg = super().build_message()
        msg[2] = self.velocity
        return msg
    def is_same_message_type(self, other):
        if not super().is_same_message_type(other):
            return False
        return self.value == other.value
    @classmethod
    def parse_message(cls, msg_bytes, **kwargs):
        kwargs['value'] = msg_bytes[1]
        kwargs['velocity'] = msg_bytes[2]
        return super().parse_message(msg_bytes, **kwargs)
    def __eq__(self, other):
        if not super().__eq__(other):
            return False
        if self.velocity != other.velocity:
            return False
        return True
    def _serialize(self):
        d = super()._serialize()
        d['velocity'] = self.velocity
        return d
    def __str__(self):
        s = super().__str__()
        return '{} {}'.format(s, self.velocity)

class NoteDownEvent(NoteEvent):
    status_msb = 0x80

class NoteUpEvent(NoteEvent):
    status_msb = 0x90

class ControllerEvent(MidiChannelEvent):
    status_msb = 0xB0
    data_bytes = 2
    controller = Property()
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.controller = kwargs.get('controller')
    @classmethod
    def parse_message(cls, msg_bytes, **kwargs):
        kwargs['controller'] = msg_bytes[1]
        return super().parse_message(msg_bytes, **kwargs)
    def build_message(self):
        msg = super().build_message()
        msg[1] = self.controller
        msg[2] = self.value
        return msg
    def is_same_message_type(self, other):
        if not super().is_same_message_type(other):
            return False
        if self.controller != other.controller:
            return False
        return True
    def __eq__(self, other):
        if not super().__eq__(other):
            return False
        if self.controller != other.controller:
            return False
        return True
    def _serialize(self):
        d = super()._serialize()
        d['controller'] = self.controller
        return d

class ProgramChangeEvent(MidiChannelEvent):
    status_msb = 0xC0

class SysExEvent(MidiEvent):
    data = ListProperty()
    def __init__(self, **kwargs):
        self.data = kwargs.get('data')
    def build_message(self):
        return self.data
    def __eq__(self, other):
        if not isinstance(other, SysExEvent):
            return NotImplemented
        return self.data == other.data
    def _serialize(self):
        d = super()._serialize()
        d['data'] = self.data
        return d
    def __str__(self):
        return ' '.join(('{:X}'.format(v) for v in self.data))


@jsonfactory.register
class JsonHandler(object):
    classes = tuple(c for c in MidiEvent.iter_subclasses())
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
