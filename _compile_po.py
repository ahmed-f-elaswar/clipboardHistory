"""Compile .po files to .mo files, with logging to file."""
import os
import struct
import traceback

log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compile_log.txt")
log_f = open(log_path, "w", encoding="utf-8")

def log(msg):
    print(msg)
    log_f.write(msg + "\n")
    log_f.flush()

def compile_po_to_mo(po_path, mo_path):
    messages = []
    with open(po_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("msgid "):
            msgid = extract_str(line[6:])
            i += 1
            while i < len(lines) and lines[i].strip().startswith('"'):
                msgid += extract_str(lines[i].strip())
                i += 1
            if i < len(lines) and lines[i].strip().startswith("msgstr "):
                msgstr = extract_str(lines[i].strip()[7:])
                i += 1
                while i < len(lines) and lines[i].strip().startswith('"'):
                    msgstr += extract_str(lines[i].strip())
                    i += 1
                messages.append((msgid, msgstr))
            else:
                i += 1
        else:
            i += 1
    
    messages.sort(key=lambda x: x[0])
    n = len(messages)
    header_size = 28
    orig_off = header_size
    trans_off = orig_off + n * 8
    data_start = trans_off + n * 8
    
    orig_tbl = []
    trans_tbl = []
    data = bytearray()
    cur = data_start
    
    for msgid, msgstr in messages:
        eid = msgid.encode("utf-8")
        orig_tbl.append((len(eid), cur))
        data.extend(eid + b"\x00")
        cur += len(eid) + 1
        estr = msgstr.encode("utf-8")
        trans_tbl.append((len(estr), cur))
        data.extend(estr + b"\x00")
        cur += len(estr) + 1
    
    out = bytearray()
    out.extend(struct.pack("<I", 0x950412de))
    out.extend(struct.pack("<I", 0))
    out.extend(struct.pack("<I", n))
    out.extend(struct.pack("<I", orig_off))
    out.extend(struct.pack("<I", trans_off))
    out.extend(struct.pack("<I", 0))
    out.extend(struct.pack("<I", 0))
    for l, o in orig_tbl:
        out.extend(struct.pack("<II", l, o))
    for l, o in trans_tbl:
        out.extend(struct.pack("<II", l, o))
    out.extend(data)
    
    with open(mo_path, "wb") as f:
        f.write(out)
    log("OK: %s -> %s (%d strings)" % (po_path, mo_path, n))

def extract_str(s):
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
    s = s.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"').replace("\\\\", "\\")
    return s

try:
    base = os.path.dirname(os.path.abspath(__file__))
    locale_dir = os.path.join(base, "locale")
    log("Locale dir: " + locale_dir)
    log("Exists: " + str(os.path.exists(locale_dir)))
    for lang in os.listdir(locale_dir):
        lc = os.path.join(locale_dir, lang, "LC_MESSAGES")
        po = os.path.join(lc, "nvda.po")
        mo = os.path.join(lc, "nvda.mo")
        if os.path.exists(po):
            log("Processing: " + po)
            compile_po_to_mo(po, mo)
    log("All done!")
except Exception:
    log(traceback.format_exc())
finally:
    log_f.close()
