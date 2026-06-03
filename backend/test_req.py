import requests
res = requests.get('http://pygbsentry.jjtt.net/index/api/webrtc?app=live', allow_redirects=False, timeout=5)
print('status:', res.status_code)
print('headers:', res.headers)
print('content:', res.text[:200])
