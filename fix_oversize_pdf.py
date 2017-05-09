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

def calculate_deflate_locations(objects, last_location = 0):
    if not objects:
        return []
    for i, obj in enumerate(objects):
        # should we put a deflate header before object i?
        if i == len(objects) - 1:
            next_location = obj[0] + obj[1]
        else:
            next_location = objects[i+1][0]
        if next_location - last_location + 9 > 0xFFFF:
            return [i] + map(lambda j : j+i, calculate_deflate_locations(objects[i:], last_location = obj[0]))
    return []

PDF_HEADER = r"%PDF-1.\d\s*\n%\xD0\xD4\xC5\xD8\s*\n"

def bytes_to_inject(length):
    """Calculates the number of bytes we need to inject after the DEFLATE header to make its length be valid within the PDF"""
    if length > 0xFFFF:
        raise Exception("A PDF object of length %d cannot be fixed!" % length)
    b1 = length & 0xFF
    b2 = (length & 0xFF00) >> 8
    n = ord('\n')
    if (b1 == n) or (b2 == n) or ((b1 ^ 0xFF) == n) or ((b2 ^ 0xFF) == n):
        return 1 + bytes_to_inject(length + 1)
    else:
        return 0

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
        if length > 0xFFFF - 5 - 4:
            raise Exception("The object at PDF offset %d is %d bytes, which is more than the maximum of %d! This PDF cannot be fixed." % (offset + start, length, 0xFFFF - 5 - 4))
        offset += start + length
    logger("Parsed %d PDF objects.\n" % len(objects))
    locations = calculate_deflate_locations(objects)
    first_block_size = len(pdf_content[start_offset:])
    block_offsets = [[-5, first_block_size, 0]]
    if not locations:
        logger("The PDF doesn't need fixing!\n")
        return block_offsets
    for idx, i in enumerate(locations):
        if idx >= len(locations) - 1:
            last = True
            length = len(pdf_content[objects[i][0]:])
        else:
            last = False
            length = objects[locations[idx+1]][0] - objects[i][0]
        injected_length = 1 # We always have to add a newline to end the comment
        if idx < len(locations) - 1:
            # We need to add three more bytes for the '%% ' before the next deflate block header:
            injected_length += 3
        extra_bytes = bytes_to_inject(length + injected_length)
        injected_length += extra_bytes
        length += extra_bytes
        if idx == 0:
            block_offsets[0][1] = objects[i][0] + 3 # +3 for the leading '%% '
        block_offsets.append([objects[i][0] + 5*idx + 3, length, injected_length]) # 5*idx is to account for the previously added 5-byte DEFLATE block headers, +3 for the leading '%% '
        logger("Inserting %s DEFLATE header comment for a %d byte block with %d extra bytes before existing object #%d...\n" % (["a", "the last"][last], length - extra_bytes, extra_bytes, i+1))
        new_obj = "%%%% %s\n" % (' ' * extra_bytes)
        pdf_content = pdf_content[:objects[i][0]] + new_obj + pdf_content[objects[i][0]:]
        for j in range(i,len(objects)):
            objects[j] = (objects[j][0] + len(new_obj), objects[j][1])
    # Fix the xrefs:
    pdf = pdf_content.splitlines(True)
    xrefoff = pdf.index("xref\n")
    startxrefoff = pdf[xrefoff:].index("startxref\n")
    nxref = int(pdf[xrefoff+1].split(" ")[1])
    output.write("".join(pdf[:xrefoff+3]))
    pdf = pdf[xrefoff+3:]
    offset = 0
    block_idx = 0
    xref_len_diff = 0
    for i in range(nxref-1):
        ref = pdf[0].split(" ")
        idx = int(ref[0])
        while block_idx < len(block_offsets) and block_offsets[block_idx][0] - offset <= idx:
            #offset += block_offsets[block_idx-1][2]
            block_idx += 1
        fixed_offset = "%010i" % (idx + offset)
        xref_len_diff += len(fixed_offset) - len(ref[0])
        ref[0] = fixed_offset
        output.write(" ".join(ref))
        pdf.pop(0)
    print "%d bytes added to the last block due to the xref fixes" % xref_len_diff
    block_offsets[-1][1] += xref_len_diff
    xrefoff = pdf.index("startxref\n")
    output.write("".join(pdf[:xrefoff+1]))
    output.write("%i\n" % (int(pdf[xrefoff+1]) + offset))
    pdf=pdf[xrefoff+2:]
    output.write("".join(pdf))
    return block_offsets

if __name__ == "__main__":
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        sys.stderr.write("Usage: %s PATH_TO_PDF [OUTPUT_FILE]\n\nA block offsets file used by update_deflate_headers.py\nwill alwasy be generated at PATH_TO_PDF.block_offsets\n\n" % sys.argv[0])
        exit(1)

    def log(msg):
        sys.stderr.write(msg)
        sys.stderr.flush()

    import json
        
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
                l.write(json.dumps(blocks))
        finally:
            if out is not None:
                out.close()
