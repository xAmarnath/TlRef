import json

# Verify extra.json is properly formatted
with open('extra.json', 'r') as f:
    extra = json.load(f)

print('✓ extra.json structure:')
print(f'  - Methods: {len(extra["methods"])}')
print(f'  - Constructors: {len(extra["constructors"])}')
print(f'  - Types: {len(extra["types"])}')

# Show structure of first method
if extra['methods']:
    m = extra['methods'][0]
    print(f'\n✓ Sample method ({m["name"]}):')
    print(f'  - description: {len(m.get("description", ""))} chars')
    print(f'  - params: {len(m.get("params", []))}')
    print(f'  - returns: {m.get("returns")}')
    print(f'  - can_be_used_by: {m.get("can_be_used_by")}')

# Show structure of first constructor
if extra['constructors']:
    c = extra['constructors'][0]
    print(f'\n✓ Sample constructor ({c["name"]}):')
    print(f'  - description: {len(c.get("description", ""))} chars')
    print(f'  - fields: {len(c.get("fields", []))}')
    if c['fields']:
        f = c['fields'][0]
        print(f'  - field[0]: {f["name"]} ({f["type"]}) - {len(f.get("description", ""))} chars desc')
    print(f'  - can_be_used_by: {c.get("can_be_used_by")}')

print('\n✓ build_html.py updated with:')
print('  - load_extra_documentation() function')
print('  - merge_with_extra() function')
print('  - Integration in build_html_docs()')

# Verify build_html.py has the new functions
with open('build_html.py', 'r') as f:
    content = f.read()
    has_load_extra = 'def load_extra_documentation' in content
    has_merge = 'def merge_with_extra' in content
    has_merge_call = 'data = merge_with_extra(data, extra)' in content

print(f'\n✓ build_html.py function checks:')
print(f'  - load_extra_documentation(): {has_load_extra}')
print(f'  - merge_with_extra(): {has_merge}')
print(f'  - merge call in build_html_docs(): {has_merge_call}')

if all([has_load_extra, has_merge, has_merge_call]):
    print('\n✅ All integrations complete!')
