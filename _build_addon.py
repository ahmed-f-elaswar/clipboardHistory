import zipfile
import os

addon_dir = r'D:\code\clipboardHistory-addon'
output = r'D:\code\clipboardHistory-2.0.0.nvda-addon'

with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(addon_dir):
        # Skip .git and hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        # Skip build helper files
        for f in files:
            if f.startswith('_') or f.startswith('.'):
                continue
            if f == 'compile_log.txt':
                continue
            full_path = os.path.join(root, f)
            arc_name = os.path.relpath(full_path, addon_dir)
            zf.write(full_path, arc_name)
            print(f"  Added: {arc_name}")

print(f"\nCreated: {output}")
