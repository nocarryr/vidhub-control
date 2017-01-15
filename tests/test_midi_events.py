import pytest

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
