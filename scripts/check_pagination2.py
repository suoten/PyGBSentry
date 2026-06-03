import os

def check_files():
    search_dirs = [
        'e:\\硕腾网络\\PyGBSentry\\PyGBSentry\\editions\\open-source\\frontend\\src\\views',
        'e:\\硕腾网络\\PyGBSentry\\PyGBSentry\\editions\\server\\frontend\\src\\views'
    ]
    missing = []
    for d in search_dirs:
        if not os.path.exists(d):
            continue
        for root, dirs, files in os.walk(d):
            for file in files:
                if file.endswith('.vue'):
                    path = os.path.join(root, file)
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if '<el-table' in content and '<el-pagination' not in content:
                            missing.append(path)
    with open('missing_pagination.txt', 'w', encoding='utf-8') as f:
        for m in missing:
            f.write(m + '\n')

check_files()