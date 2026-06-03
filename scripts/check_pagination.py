import os, glob

def check_files():
    search_dirs = [
        'e:\\硕腾网络\\PyGBSentry\\PyGBSentry\\editions\\open-source\\frontend\\src\\views',
        'e:\\硕腾网络\\PyGBSentry\\PyGBSentry\\editions\\open-source\\frontend\\src\\components',
        'e:\\硕腾网络\\PyGBSentry\\PyGBSentry\\editions\\server\\frontend\\src\\views'
    ]
    missing = []
    for d in search_dirs:
        for root, dirs, files in os.walk(d):
            for file in files:
                if file.endswith('.vue'):
                    path = os.path.join(root, file)
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if '<el-table' in content and '<el-pagination' not in content:
                            missing.append(path)
    for m in missing:
        print(m)

check_files()
