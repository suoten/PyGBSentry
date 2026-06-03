import re

fp = r'E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\frontend\src\views\ConfigCenter.vue'
with open(fp, 'r', encoding='utf-8') as f:
    content = f.read()

# Pattern 1: Simple GET fetch
# const res = await fetch('/api/v1/xxx')
# if (res.ok) { const data = await res.json() ... }
content = content.replace(
    "const res = await fetch('/api/v1/config-center/basic')\n    if (res.ok) {\n      const data = await res.json()",
    "const { data } = await api.get('/api/v1/config-center/basic')"
)
content = content.replace(
    "const res = await fetch('/api/v1/system-config/database')\n    if (res.ok) {\n      const data = await res.json()",
    "const { data } = await api.get('/api/v1/system-config/database')"
)
content = content.replace(
    "const res = await fetch('/api/v1/ops/db-compat-report')\n    if (res.ok) {\n      const data = await res.json()",
    "const { data } = await api.get('/api/v1/ops/db-compat-report')"
)
content = content.replace(
    "const res = await fetch('/api/v1/integrations/sources')\n    if (res.ok) {\n      const data = await res.json()",
    "const { data } = await api.get('/api/v1/integrations/sources')"
)
content = content.replace(
    "const res = await fetch('/api/v1/record-schedule/storage-config')\n    if (res.ok) {\n      const data = await res.json()",
    "const { data } = await api.get('/api/v1/record-schedule/storage-config')"
)
content = content.replace(
    "const res = await fetch('/api/v1/record-schedule/storage-nodes')\n    if (res.ok) {\n      const data = await res.json()",
    "const { data } = await api.get('/api/v1/record-schedule/storage-nodes')"
)

# Pattern 2: PUT fetch with body
content = content.replace(
    "const res = await fetch('/api/v1/config-center/basic', {\n      method: 'PUT',\n      headers: { 'Content-Type': 'application/json' },\n      body: JSON.stringify(basicForm.value)\n    })\n    if (res.ok)",
    "await api.put('/api/v1/config-center/basic', basicForm.value)\n    if (true)"
)

content = content.replace(
    "const res = await fetch('/api/v1/system-config/database', {\n      method: 'PUT',\n      headers: { 'Content-Type': 'application/json' },\n      body: JSON.stringify(dbForm.value)\n    })\n    if (res.ok)",
    "await api.put('/api/v1/system-config/database', dbForm.value)\n    if (true)"
)

# Pattern 3: POST fetch
content = content.replace(
    "const res = await fetch('/api/v1/system-config/database/test', {\n      method: 'POST',\n      headers: { 'Content-Type': 'application/json' },\n      body: JSON.stringify(dbForm.value)\n    })\n    if (res.ok) {\n      const data = await res.json()",
    "const { data } = await api.post('/api/v1/system-config/database/test', dbForm.value)"
)

content = content.replace(
    "const res = await fetch(`/api/v1/integrations/sources/${id}/test`, { method: 'POST' })\n    if (res.ok) {\n      const data = await res.json()",
    "const { data } = await api.post(`/api/v1/integrations/sources/${id}/test`)"
)

content = content.replace(
    "await fetch(`/api/v1/integrations/sources/${id}`, { method: 'DELETE' })",
    "await api.delete(`/api/v1/integrations/sources/${id}`)"
)

content = content.replace(
    "const res = await fetch(`/api/v1/integrations/sources/${id}/play`, { method: 'POST' })\n    if (res.ok) {\n      const data = await res.json()",
    "const { data } = await api.post(`/api/v1/integrations/sources/${id}/play`)"
)

content = content.replace(
    "      await fetch('/api/v1/stream/stop', {\n        method: 'POST',\n        headers: { 'Content-Type': 'application/json' },\n        body: JSON.stringify({ app: 'live', stream: previewStreamId.value })\n      })",
    "      await api.post('/api/v1/stream/stop', { app: 'live', stream: previewStreamId.value })"
)

# Pattern 4: POST with body and variable URL
content = content.replace(
    "const res = await fetch(url, {\n      method: 'POST',\n      headers: { 'Content-Type': 'application/json' },\n      body: JSON.stringify(form)\n    })\n    if (res.ok) {\n      const data = await res.json()",
    "const { data } = await api.post(url, form)"
)

# Pattern 5: GET with query params
content = content.replace(
    "const res = await fetch(`/api/v1/audit-center/logs?${params}`)\n    if (res.ok) {\n      const data = await res.json()",
    "const { data } = await api.get(`/api/v1/audit-center/logs?${params}`)"
)

# Pattern 6: PUT storage config
content = content.replace(
    "const res = await fetch('/api/v1/record-schedule/storage-config', {\n      method: 'PUT',\n      headers: { 'Content-Type': 'application/json' },\n      body: JSON.stringify(storageForm.value)\n    })\n    if (res.ok)",
    "await api.put('/api/v1/record-schedule/storage-config', storageForm.value)\n    if (true)"
)

# Pattern 7: PUT storage nodes
content = content.replace(
    "const res = await fetch('/api/v1/record-schedule/storage-nodes', {\n      method: 'PUT',\n      headers: { 'Content-Type': 'application/json' },\n      body: JSON.stringify(storageNodesForm.value)\n    })\n    if (res.ok)",
    "await api.put('/api/v1/record-schedule/storage-nodes', storageNodesForm.value)\n    if (true)"
)

# Remove remaining `if (res.ok)` blocks that are now unnecessary
# And clean up `const data = await res.json()` patterns that might remain

with open(fp, 'w', encoding='utf-8', newline='\n') as f:
    f.write(content)

# Verify no fetch calls remain
remaining = content.count('await fetch(')
print(f'Remaining fetch calls: {remaining}')
print('Done')
