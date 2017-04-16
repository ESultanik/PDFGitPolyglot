#!/usr/bin/env python2

import fix_oversize_pdf
import re
import sys

def read_deflate_header(header):
    last = bool(0b1 & ord(header[0]))
    length = (ord(header[2]) << 8) + ord(header[1])
    nlength = (ord(header[4]) << 8) + ord(header[3])
    if nlength ^ 0xFFFF != length:
        raise Exception("Corrupt DEFLATE header!")
    return last, length

def update_deflate_headers(pdf_content, output, first_block_size):
    m = re.match(r"(.*?)" + fix_oversize_pdf.PDF_HEADER,pdf_content,re.MULTILINE | re.DOTALL)
    if not m:
        raise Exception("Could not find PDF header!")
    pdf_header_offset = len(m.group(1))
    print "Found PDF header at offset %d" % pdf_header_offset
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
        print "Deleted DEFLATE header for a %d byte block at offset 0x%x" % (length, header_offset)
        header_offset += length
    print "Updating the first DEFLATE header..."
    pdf_content = pdf_content[:pdf_header_offset] + fix_oversize_pdf.make_deflate_header(False, first_block_size) + pdf_content[pdf_header_offset+5:]
    out.write(pdf_content)
    out.flush()

if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.stderr.write("Usage: %s PATH_TO_PDF OUTPUT_FILE FIRST_BLOCK_BYTES\n\n" % sys.argv[0])
        exit(1)

    with open(sys.argv[1], 'rb') as f:
        with open(sys.argv[2], 'wb') as out:
            update_deflate_headers(f.read(), out, int(sys.argv[3]))
