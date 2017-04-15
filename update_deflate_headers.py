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

def update_deflate_headers(pdf_content, output):
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
    print "Updating the injected DEFLATE headers..."
    previous_header_offset = pdf_header_offset - 5
    last = False
    i = 0
    while not last:
        i += 1
        next_header_offset = pdf_content.find(fix_oversize_pdf.DEFLATE_OBJ_PLACEHOLDER, previous_header_offset+5)
        if next_header_offset < 0:
            last = True
            # Find the end of the PDF:
            PDF_END_MAGIC = "%%EOF\x0A"
            next_header_offset = pdf_content.find(PDF_END_MAGIC, previous_header_offset+5)
            if next_header_offset < 0:
                raise Exception("Could not find the end of the PDF!")
            next_header_offset += len(PDF_END_MAGIC)
        length = next_header_offset - previous_header_offset - 5
        if length > 0xFFFF:
            raise Exception("The length of DEFLATE block %d is 0x%x bytes, which is over the maximum of 0xFFFF!" % (i, length))
        pdf_content = pdf_content[:previous_header_offset] + make_deflate_header(last, length) + pdf_content[previous_header_offset+5:]
        previous_header_offset = next_header_offset
        print "DEFLATE block header %d%s set to length %d" % (i, [""," (last)"][last], length)
    out.write(pdf_content)
    out.flush()

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.stderr.write("Usage: %s PATH_TO_PDF OUTPUT_FILE\n\n" % sys.argv[0])
        exit(1)

    with open(sys.argv[1], 'rb') as f:
        with open(sys.argv[2], 'wb') as out:
            update_deflate_headers(f.read(), out)
