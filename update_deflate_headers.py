#!/usr/bin/env python2

import fix_oversize_pdf
import re
import sys
import zlib

def read_deflate_header(header):
    last = bool(0b1 & ord(header[0]))
    length = (ord(header[2]) << 8) + ord(header[1])
    nlength = (ord(header[4]) << 8) + ord(header[3])
    if nlength ^ 0xFFFF != length:
        raise Exception("Corrupt DEFLATE header!")
    return last, length

def make_deflate_header(last, length):
    header = ["\0"] * 5
    if last:
        header[0] = "\x01"
    header[1] = chr(length & 0xFF)
    header[2] = chr((length & 0xFF00) >> 8)
    nlength = length ^ 0xFFFF
    header[3] = chr(nlength & 0xFF)
    header[4] = chr((nlength & 0xFF00) >> 8)    
    return "".join(header)

def update_deflate_headers(pdf_content, output, block_offsets):
    m = re.match(r"(.*?)" + fix_oversize_pdf.PDF_HEADER,pdf_content,re.MULTILINE | re.DOTALL)
    if not m:
        raise Exception("Could not find PDF header!")
    pdf_header_offset = len(m.group(1))
    print "Found PDF header at offset %d" % pdf_header_offset
    content_before = zlib.decompress(pdf_content[pdf_header_offset - 7:])
    deflate_header = pdf_content[:pdf_header_offset][-5:]
    last, length = read_deflate_header(deflate_header)
    if last:
        print "The entire PDF fits in a single DEFLATE block; nothing needed!"
        return
    print "Deleting the unwanted DEFLATE headers..."
    header_offset = pdf_header_offset + length
    while not last:
        header = pdf_content[header_offset:header_offset+5]
        try:
            last, length = read_deflate_header(header)
        except Exception as e:
            print " ".join(map(hex, map(ord, pdf_content[header_offset-5:header_offset+10])))
            raise e
        pdf_content = pdf_content[:header_offset] + pdf_content[header_offset + 5:]
        print "Deleted DEFLATE header at offset 0x%x for a %d byte block" % (header_offset, length)
        header_offset += length 
    print "Updating the first DEFLATE header..."
    pdf_content = pdf_content[:pdf_header_offset + block_offsets[0][0]] + make_deflate_header(False, block_offsets[0][1]) + pdf_content[pdf_header_offset:]
    print "Updating the injected DEFLATE headers..."
    for idx, block in enumerate(block_offsets[1:]):
        last = (idx == len(block_offsets) - 2)
        offset, length = block
        print "Injecting DEFLATE header at offset 0x%x for a %d byte block" % (pdf_header_offset + offset, length)
        pdf_content = pdf_content[:pdf_header_offset + offset] + make_deflate_header(last, length) + pdf_content[pdf_header_offset + offset:]
    content_after = zlib.decompress(pdf_content[pdf_header_offset - 7:])
    print "Validating the resulting DEFLATE headers..."
    if content_before != content_after:
        raise Exception("Error: the updated DEFLATE output is corrupt!")
    out.write(pdf_content)
    out.flush()

if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.stderr.write("Usage: %s PATH_TO_PDF OUTPUT_FILE BLOCK_OFFSETS\n\n" % sys.argv[0])
        exit(1)

    import json
        
    with open(sys.argv[1], 'rb') as f:
        with open(sys.argv[2], 'wb') as out:
            with open(sys.argv[3], 'r') as blocks:
                block_offsets = json.load(blocks)
                update_deflate_headers(f.read(), out, block_offsets)
