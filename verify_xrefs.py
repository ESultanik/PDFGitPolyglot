#!/usr/bin/env python2

import os
import re
import subprocess
import tempfile

PDF_HEADER = r"%PDF-1.\d\s*\n%\xD0\xD4\xC5\xD8\s*\n"
EOF_STRING = '\n%%EOF\n'
FNULL = open(os.devnull, 'w')

def find_pdf_start(pdf_bytes):
    m = re.match(r"(.*?)" + PDF_HEADER,pdf_bytes,re.MULTILINE | re.DOTALL)
    if not m:
        raise Exception('Could not find PDF header!')
    return len(m.group(1))

def find_pdf_end(pdf_bytes, start_offset = 0):
    return pdf_bytes.rindex(EOF_STRING, start_offset) + len(EOF_STRING)

def verify_xrefs(pdf_bytes):
    pdf_header_offset = find_pdf_start(pdf_bytes)
    print "Found PDF header at offset %d" % pdf_header_offset
    pdf_end_offset = find_pdf_end(pdf_bytes, start_offset = pdf_header_offset)
    print "Found PDF trailer at offset %d" % pdf_end_offset
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(pdf_bytes[pdf_header_offset:pdf_end_offset])
        tmp.flush()
        subprocess.check_call(["/usr/bin/env", "qpdf", "-qdf", tmp.name, '-'], stdout=FNULL)
    print "PDF appears to be valid."
    return True
        
if __name__ == "__main__":
    import sys
    for path in sys.argv[1:]:
        with open(path, 'rb') as f:
            verify_xrefs(f.read())
