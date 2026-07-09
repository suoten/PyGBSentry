import sys
path = r'e:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\frontend\src\components\AppErrorBoundary.vue'
data = open(path, 'r', encoding='utf-8').read()
lines = data.split('\n')
print('line 4 repr:', repr(lines[3]))
s = 'title="\u9875\u9762\u52a0\u8f7d\u5f02\u5e38" sub-title="\u8bf7\u5237\u65b0\u91cd\u8bd5"'
print('search string repr:', repr(s))
print('found:', s in data)
