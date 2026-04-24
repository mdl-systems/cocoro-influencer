import codecs
path = r'e:\antigravity\cocoro-server\frontend\src\app\page.tsx'
with codecs.open(path, 'r', 'utf-8') as f:
    lines = f.readlines()
results = []
for i, l in enumerate(lines):
    ll = l.lower()
    if 'walk' in ll or 'default_scene' in l or 'defaultscene' in ll or "pose:" in l:
        results.append(f'L{i+1}: {l.rstrip()}')
for r in results[:30]:
    print(r)
