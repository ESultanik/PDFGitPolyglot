#!/usr/bin/env python2

import fix_oversize_pdf
import hashlib
import re
import struct
import sys
import zlib

def parse_pack_object(data):
    obj_type = None
    length = 0
    header_bytes = 0
    for c in map(ord, data):
        if obj_type is None:
            # This is the first byte
            obj_type = (c >> 4) & 0b111
            length = c & 0b1111
        else:
            length += (c & 0b01111111) << ((header_bytes - 1)*7 + 4)
        header_bytes += 1
        if not (c & 0b10000000):
            break # This was the last byte
    if obj_type == 7:
        # OBJ_REF_DELTA
        header_bytes += 20
    elif obj_type == 6:
        # OBJ_OFS_DELTA
        for c in map(ord, data[header_bytes:]):
            header_bytes += 1
            if not (c & 0b10000000):
                break
    d = zlib.decompressobj()
    decompressed = d.decompress(data[header_bytes:], length)
    assert len(decompressed) == length
    compressed_length = len(data) - header_bytes - len(d.unused_data)
    return header_bytes, obj_type, length, compressed_length

def fix_pack_sha1(pdf_content, pdf_header_offset):
    pack_offset = pdf_content.rindex("PACK", 0, pdf_header_offset)
    version, num_objects = struct.unpack("!II", pdf_content[pack_offset + 4:pack_offset + 12])
    print "Found git pack version %d containing %d objects" % (version, num_objects)
    offset = pack_offset + 12
    for i in range(num_objects):
        #print "Offset: 0x%x" % offset
        header_bytes, obj_type, decompressed_length, compressed_length = parse_pack_object(pdf_content[offset:])
        #print "Parsed pack object at offset 0x%x of type %d with a %d byte header, %d byte body (decompressed), and %d byte body (compressed)" % (offset, obj_type, header_bytes, decompressed_length, compressed_length)
        offset += header_bytes + compressed_length
    print "SHA1 should be at offset 0x%x" % offset
    sha1 = hashlib.sha1(pdf_content[:offset])
    print sha1.hexdigest()
    if sha1.digest() == pdf_content[offset:offset+20]:
        print "SHA1 is valid!"
    else:
        print "SHA1 is not valid!"
    return offset
    # sha1 = None
    # last_percent = -1
    # for i in range(pack_offset + 12 + 20, len(pdf_content) - 20):
    #     percent = int(float(i - (pack_offset + 12 + 20)) / float(len(pdf_content)-20-(pack_offset + 12 + 20)) * 100.0)
    #     if percent > last_percent:
    #         sys.stdout.write('\r' + ' ' * 30 + "\rSearching for end of pack... %d%%" % percent)
    #         sys.stdout.flush()
    #         last_percent = percent
    #     pack_content = pdf_content[pack_offset:i]
    #     test = hashlib.sha1(pack_content)
    #     assert len(test.digest()) == 20
    #     #print test.digest(), pdf_content[i:i+20]
    #     if test.digest() == pdf_content[i:i+20]:
    #         sha1 = i
    #         break
    # if sha1 is not None:
    #     print "\nFound SHA1 at offset 0x%x!" % sha1
    # else:
    #     print "\nDid not find SHA1!"
    
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
    fix_pack_sha1(pdf_content, pdf_header_offset)
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
    fix_pack_sha1(pdf_content, pdf_header_offset)
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