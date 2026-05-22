import markdown
import os

addon_dir = r'D:\code\clipboardHistory-addon\doc'

for lang in ['en', 'ar', 'fr', 'es']:
    md_path = os.path.join(addon_dir, lang, 'readme.md')
    html_path = os.path.join(addon_dir, lang, 'readme.html')
    with open(md_path, encoding='utf-8') as f:
        md_text = f.read()
    html_body = markdown.markdown(md_text, extensions=['tables'])
    direction = ' dir="rtl"' if lang == 'ar' else ''
    html_doc = (
        '<!DOCTYPE html>\n<html' + direction + '>\n<head>\n'
        '<meta charset="utf-8">\n'
        '<title>Clipboard History Manager</title>\n'
        '</head>\n<body>\n'
        + html_body +
        '\n</body>\n</html>'
    )
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_doc)
    print(f"Generated: {lang}/readme.html")

print("All HTML docs generated")
