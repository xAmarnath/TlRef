import re
import json

src = open('gogram_errors.go', encoding='utf-8').read()

m = re.search(r'var errorMessages = map\[string\]string\{(.*?)\n\}', src, re.DOTALL)
if not m:
    raise SystemExit('no errorMessages map')
block = m.group(1)

entries = []
line_re = re.compile(r'\s*"([A-Z0-9_]+)"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,?\s*$')
for line in block.split('\n'):
    em = line_re.match(line)
    if em:
        msg = em.group(2).replace('\\"', '"').replace('\\\\', '\\')
        entries.append({'code': em.group(1), 'message': msg})
print('parsed errors:', len(entries))

m2 = re.search(r'var badMsgErrorCodes = map\[uint8\]string\{(.*?)\n\}', src, re.DOTALL)
bad = []
bad_re = re.compile(r'\s*(\d+)\s*:\s*"((?:[^"\\]|\\.)*)"\s*,?\s*$')
for line in m2.group(1).split('\n'):
    bm = bad_re.match(line)
    if bm:
        bad.append({'code': int(bm.group(1)), 'message': bm.group(2).replace('\\"', '"')})
print('badmsg codes:', len(bad))

m3 = re.search(r'var specificErrors = \[\]prefixSuffix\{(.*?)\n\}', src, re.DOTALL)
parameterized = []
ps_re = re.compile(r'\s*\{\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*reflect\.(\w+)\s*\}\s*,?\s*$')
for line in m3.group(1).split('\n'):
    pm = ps_re.match(line)
    if pm:
        parameterized.append({'prefix': pm.group(1), 'suffix': pm.group(2), 'kind': pm.group(3).lower()})
print('parameterized patterns:', len(parameterized))

raw = {'errors': entries, 'bad_msg_codes': bad, 'parameterized': parameterized}
with open('errors_raw.json', 'w', encoding='utf-8') as f:
    json.dump(raw, f, indent=2, ensure_ascii=False)
print('wrote errors_raw.json')

print('--- sample ---')
for e in entries[:5]:
    print(e)
