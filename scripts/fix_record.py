import os, re

src_dir = r'e:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\frontend\src'

count = 0
for root, dirs, files in os.walk(src_dir):
    for fname in files:
        if not fname.endswith(('.vue', '.ts')):
            continue
        if fname == 'models.ts':
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        original = content
        
        # Replace import { Record } -> import { VideoRecord }
        content = content.replace("import { Record } from '@/types/models'", "import { VideoRecord } from '@/types/models'")
        content = content.replace("import type { Record } from '@/types/models'", "import type { VideoRecord } from '@/types/models'")
        
        # Replace in combined imports like { Channel, Record }
        content = re.sub(r"import type \{ (.*)Record(.*) \} from '@/types/models'", lambda m: "import type { " + m.group(1).rstrip() + ("VideoRecord" if not m.group(1).strip() else ", VideoRecord") + m.group(2) + " } from '@/types/models'", content)
        content = re.sub(r"import \{ (.*)Record(.*) \} from '@/types/models'", lambda m: "import { " + m.group(1).rstrip() + ("VideoRecord" if not m.group(1).strip() else ", VideoRecord") + m.group(2) + " } from '@/types/models'", content)
        
        # Replace type usages: ref<Record>, : Record, as Record, etc.
        # Only replace standalone "Record" that refers to the custom type, not Record<string, unknown>
        content = re.sub(r'\bRecord\b(?!\s*<)', 'VideoRecord', content)
        # Fix back any VideoRecord<string, unknown> -> Record<string, unknown>
        content = content.replace('VideoRecord<string, unknown>', 'Record<string, unknown>')
        content = content.replace('VideoRecord<string, string>', 'Record<string, string>')
        content = content.replace('VideoRecord<string, number>', 'Record<string, number>')
        content = content.replace('VideoRecord<string, boolean>', 'Record<string, boolean>')
        content = content.replace('VideoRecord<string, Record<string, unknown>>', 'Record<string, Record<string, unknown>>')
        content = content.replace('VideoRecord<string, unknown[]>', 'Record<string, unknown[]>')
        
        if content != original:
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(content)
            count += 1
            print(f'Fixed: {fname}')

print(f'Total files changed: {count}')
