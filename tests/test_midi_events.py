import pytest
import jsonfactory

from vidhubcontrol.interfaces.midi import events

@pytest.fixture
def midi_events():
    velocity = 90
    tx_events = {}
    sysex_events = []
    data = []
    num_events = 0
    sysex_data = list(range(8)) * 8
    for ch in range(16):
        tx_events[ch] = {}
        for value in range(128):
            for cls in [events.NoteDownEvent, events.NoteUpEvent, events.ControllerEvent]:
                if cls is events.ControllerEvent:
                    e = cls(channel=ch, value=value, controller=velocity)
                else:
                    e = cls(channel=ch, value=value, velocity=velocity)
                data.extend(e.build_message())
                if cls not in tx_events[ch]:
                    tx_events[ch][cls] = {}
                tx_events[ch][cls][value] = e
                num_events += 1
        sysex_data = [syx + 1 for syx in sysex_data]
        sysex = events.SysExEvent(data=[0xF0]+sysex_data+[0xF7])
        data.extend(sysex.build_message())
        sysex_events.append(sysex)
        num_events += 1
    return {
        'velocity':velocity,
        'tx_events':tx_events,
        'sysex_events':sysex_events,
        'data':data,
        'num_events':num_events
    }

def test_event_parse(midi_events):
    num_parsed = 0
    sysex_iter = iter(midi_events['sysex_events'])
    for e in events.MidiEvent.parse_stream(midi_events['data']):
        if isinstance(e, events.SysExEvent):
            tx_event = next(sysex_iter)
            assert tx_event == e
        else:
            tx_event = midi_events['tx_events'][e.channel][e.__class__][e.value]
            assert tx_event.is_same_message_type(e)
            assert tx_event == e
            if isinstance(e, events.NoteEvent):
                e.velocity += 1
                assert tx_event.is_same_message_type(e)
                assert tx_event != e
                e.value += 1
                assert not tx_event.is_same_message_type(e)
                assert tx_event != e
                e.value = tx_event.value
                assert tx_event.is_same_message_type(e)
                e.channel += 1
                assert not tx_event.is_same_message_type(e)
                assert tx_event != e
            else:
                e.value += 1
                assert tx_event.is_same_message_type(e)
                assert tx_event != e
                e.value = tx_event.value
                assert tx_event == e
                e.controller += 1
                assert not tx_event.is_same_message_type(e)
                assert tx_event != e
                e.controller = tx_event.controller
                assert tx_event.is_same_message_type(e)
                assert tx_event == e
                e.channel += 1
                assert not tx_event.is_same_message_type(e)
                assert tx_event != e
        num_parsed += 1

    assert midi_events['num_events'] == num_parsed

def test_serialization(midi_events):

    @jsonfactory.decoder
    def decode_str_keys(d):
        keys = [key for key in d if isinstance(key, str) and key.isdigit()]
        if len(keys) == len(d.keys()):
            return {int(key):val for key, val in d.items()}
        return d

    # Convert class keys to str
    d = {'tx_events':{}, 'sysex_events':midi_events['sysex_events']}
    for ch, _d in midi_events['tx_events'].items():
        d['tx_events'][ch] = {}
        for cls, _dd in _d.items():
            d['tx_events'][ch][str(cls)] = _dd

    s = jsonfactory.dumps(d)
    deserialized = jsonfactory.loads(s)

    def iter_events(src_obj, test_obj):
        if isinstance(src_obj, dict):
            assert isinstance(test_obj, dict)
            assert set(src_obj.keys()) == set(test_obj.keys())
            for key in src_obj.keys():
                yield from iter_events(src_obj[key], test_obj[key])
        elif isinstance(src_obj, list):
            assert isinstance(test_obj, list)
            assert len(src_obj) == len(test_obj)
            for i in range(len(src_obj)):
                yield from iter_events(src_obj[i], test_obj[i])
        else:
            assert isinstance(src_obj, events.MidiEvent)
            assert isinstance(test_obj, events.MidiEvent)
            yield src_obj, test_obj

    num_tested = 0
    for tx_event, e in iter_events(d, deserialized):
        assert tx_event == e
        num_tested += 1
    assert num_tested == midi_events['num_events']
