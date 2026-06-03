import os

BASE = r'E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip'

replacements = {
    'catalog.py': [
        ('<DeviceID>{device_id}</DeviceID>', '<DeviceID>{_xml_escape(device_id)}</DeviceID>'),
    ],
    'device_control.py': [
        ('<DeviceID>{channel_id}</DeviceID>', '<DeviceID>{_xml_escape(channel_id)}</DeviceID>'),
        ('<DeviceID>{device_id}</DeviceID>', '<DeviceID>{_xml_escape(device_id)}</DeviceID>'),
        ('<GuardCmd>{guard_cmd}</GuardCmd>', '<GuardCmd>{_xml_escape(guard_cmd)}</GuardCmd>'),
        ('<AlarmMethod>{alarm_method}</AlarmMethod>', '<AlarmMethod>{_xml_escape(alarm_method)}</AlarmMethod>'),
        ('<AlarmType>{alarm_type}</AlarmType>', '<AlarmType>{_xml_escape(alarm_type)}</AlarmType>'),
        ('<RecordCmd>{record_cmd}</RecordCmd>', '<RecordCmd>{_xml_escape(record_cmd)}</RecordCmd>'),
    ],
    'record.py': [
        ('<DeviceID>{channel_id}</DeviceID>', '<DeviceID>{_xml_escape(channel_id)}</DeviceID>'),
    ],
    'commander.py': [
        ('<DeviceID>{device_id}</DeviceID>', '<DeviceID>{_xml_escape(device_id)}</DeviceID>'),
        ('<DeviceID>{channel_id}</DeviceID>', '<DeviceID>{_xml_escape(channel_id)}</DeviceID>'),
        ('<DeviceID>{platform_gb_id}</DeviceID>', '<DeviceID>{_xml_escape(platform_gb_id)}</DeviceID>'),
        ('<DeviceID>{settings.SIP_ID}</DeviceID>', '<DeviceID>{_xml_escape(settings.SIP_ID)}</DeviceID>'),
        ('<TargetID>{channel_id}</TargetID>', '<TargetID>{_xml_escape(channel_id)}</TargetID>'),
        ('<SourceID>{settings.SIP_ID}</SourceID>', '<SourceID>{_xml_escape(settings.SIP_ID)}</SourceID>'),
    ],
}

for filename, reps in replacements.items():
    filepath = os.path.join(BASE, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    for old, new in reps:
        content = content.replace(old, new)
    with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)
    print(f'Fixed {filename}')

print('Done')
