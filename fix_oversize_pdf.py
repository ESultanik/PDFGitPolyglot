#!/usr/bin/env python2

import re
import sys

def parse_obj(pdf_content, logger = None):
    if logger is None:
        logger = lambda s : None
    bytes_skipped = 0
    for line in pdf_content.splitlines():
        if line.startswith('%'):
            bytes_skipped += len(line) + 1
            continue
        m = re.match(r"^\s*\d+\s+\d+\s+obj$", line)
        if not m:
            bytes_skipped += len(line) + 1
            continue
        after_obj = pdf_content[bytes_skipped+len(line)+1:]
        m = re.match(r"^\s*<<.*?\/Length\s+(\d+)\s*\n.*?>>.*?stream\n", after_obj, re.MULTILINE | re.DOTALL)
        if m:
            bytes_up_to_endstream = len(m.group(0)) + int(m.group(1))
            after_stream = after_obj[bytes_up_to_endstream:]
            m2 = re.match(r".*?\n*endstream\s*\nendobj\s*\n", after_stream, re.MULTILINE | re.DOTALL)
            if not m2:
                logger("Expected an endstream/endobj for \"%s\", but instead got \"%s\"" % (line, after_stream[:10]))
                exit(1)
            #print pdf_content[bytes_skipped + len(line) + 1 + bytes_up_to_endstream + len(m2.group(0)):][:50]
            return bytes_skipped, len(line) + 1 + bytes_up_to_endstream + len(m2.group(0))
        m2 = re.match(".*?\n?endobj\s*\n", after_obj, re.MULTILINE | re.DOTALL)
        if m2:
            return bytes_skipped, len(m2.group(0))
        else:
            logger("Error: did not find end of PDF \"%s\"!\n" % line)
    return None, None

DEFLATE_OBJ_START="%d 0 obj\n<<\n/Length 5\n>>\nstream\n"
DEFLATE_OBJ_PRE_LEN=len(DEFLATE_OBJ_START) + 2
DEFLATE_OBJ_END="endstream\nendobj\n"

def calculate_deflate_locations(objects, additional_bytes = 0):
    if not objects:
        return []
    length = additional_bytes
    for i, obj in enumerate(objects):
        # should we put a deflate header before object i?
        start, l = obj
        if length + l + DEFLATE_OBJ_PRE_LEN > 0xFFFF:
            return [i] + map(lambda j : j+i, calculate_deflate_locations(objects[i:], additional_bytes = len(DEFLATE_OBJ_END)))
        length += l
    return []

PDF_HEADER = r"%PDF-1.\d\s*\n%\xD0\xD4\xC5\xD8\s*\n"

def fix_pdf(pdf_content, output = None, logger = None):
    if output is None:
        output = sys.stdout
    if logger is None:
        logger = lambda s : None
    start_offset = None
    offset = 0
    for i in range(len(pdf_content)):
        m = re.match(PDF_HEADER,pdf_content[i:],re.MULTILINE | re.DOTALL)
        if m:
            start_offset = i
            logger("Found PDF header at offset %d\n" % start_offset)
            offset = len(m.group(0))
            break
    if start_offset is None:
        raise Exception("Did not find PDF header!")
    objects = []
    while True:
        start, length = parse_obj(pdf_content[offset:], logger = logger)
        if start is None:
            break
        objects.append((offset + start, length))
        if length > 0xFFFF - DEFLATE_OBJ_PRE_LEN:
            raise Exception("The object at PDF offset %d is more than %d bytes! This PDF cannot be fixed." % (0xFFFF - DEFLATE_OBJ_PRE_LEN))
        offset += start + length
    logger("Parsed %d PDF objects.\n" % len(objects))
    locations = calculate_deflate_locations(objects)
    first_block_size = 0
    if not locations:
        logger("The PDF doesn't need fixing!\n")
        return first_block_size
    if len(locations) > 10:
        raise Exception("Error: We currently only support up to 10 DEFLATE header objects! Edit fix_oversize_pdf.py to increase this amount.")
    for idx, i in enumerate(locations):
        if i >= len(locations) - 1:
            last = True
            length = len(pdf_content[objects[i][0]:])
        else:
            last = False
            length = objects[i+1][0] - objects[i][0]
        if idx == 0:
            first_block_size = length
        logger("Inserting %s DEFLATE header object for a %d byte block before existing object #%d...\n" % (["a", "the last"][last], length, i+1))
        new_obj = DEFLATE_OBJ_START % (9000+idx) + DEFLATE_OBJ_END
        pdf_content = pdf_content[:objects[i][0]] + new_obj + pdf_content[objects[i][0]:]
        for j in range(i,len(objects)):
            objects[j] = (objects[j][0] + len(new_obj), objects[j][1])
    # TODO: Fix the xrefs!
    output.write(pdf_content)
    return first_block_size

if __name__ == "__main__":
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        sys.stderr.write("Usage: %s PATH_TO_PDF [OUTPUT_FILE]\n\n" % sys.argv[0])
        exit(1)

    def log(msg):
        sys.stderr.write(msg)
        sys.stderr.flush()

    with open(sys.argv[1], 'rb') as f:
        kwargs = { "logger" : log }
        out = None
        try:
            content = f.read()
            if len(sys.argv) > 2:
                out = open(sys.argv[2], 'wb')
                kwargs["output"] = out
            blocks = fix_pdf(content, **kwargs)
            with open(sys.argv[1] + ".block_offsets", 'w') as l:
                l.write(" ".join(blocks))
        finally:
            if out is not None:
                out.close()
