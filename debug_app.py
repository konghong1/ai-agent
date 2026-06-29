fp = r'D:\workspace\ai-agent\web\src\App.tsx'
with open(fp, 'rb') as f:
    raw = f.read()

# Check BOM
if raw[:3] == b'\xef\xbb\xbf':
    print('Has UTF-8 BOM')
    text = raw[3:].decode('utf-8')
else:
    text = raw.decode('utf-8')

# Find Chinese chars and their byte positions
for i, c in enumerate(text):
    if '\u4e00' <= c <= '\u9fff':
        # Show surrounding context
        start = max(0, i - 10)
        end = min(len(text), i + 11)
        ctx = text[start:end]
        print('Char "{}" at pos {}: context="{}"'.format(c, i, ctx))
