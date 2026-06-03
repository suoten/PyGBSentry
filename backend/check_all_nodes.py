import ast

with open('app/sip/invite.py', encoding='utf-8') as f:
    content = f.read()

tree = ast.parse(content)

for node in ast.walk(tree):
    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        name = getattr(node, 'name', '?')
        print(f'{node.__class__.__name__} {name} at lines {node.lineno}-{node.end_lineno}, col={node.col_offset}')
