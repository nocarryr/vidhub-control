from vidhubcontrol.interfaces.midi import events

def test_event_parse():
    velocity = 90
    tx_events = {}
    data = []
    num_events = 0
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
    num_parsed = 0
    for e in events.MidiEvent.parse_stream(data):
        tx_event = tx_events[e.channel][e.__class__][e.value]
        assert tx_event == e
        num_parsed += 1
    assert num_events == num_parsed
