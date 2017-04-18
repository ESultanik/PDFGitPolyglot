#!/usr/bin/env python2

import fix_oversize_pdf
import hashlib
import re
import struct
import sys
import zlib

OBJ_OFS_DELTA=6
OBJ_REF_DELTA=7

class PackObject(object):
    def __init__(self, **kwargs):
        for k, v in kwargs.iteritems():
            setattr(self, k, v)

def parse_pack_object(data):
    obj_type = None
    length = 0
    header_bytes = 0
    kwargs = {}
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
    if obj_type == OBJ_REF_DELTA:
        header_bytes += 20
    elif obj_type == OBJ_OFS_DELTA:
        reference = 0
        reference_offset = header_bytes
        for i, c in enumerate(map(ord, data[header_bytes:])):
            header_bytes += 1
            reference += (c & 0b01111111) << (i * 7)
            if not (c & 0b10000000):
                break
        kwargs["reference"] = reference
        kwargs["reference_header_offset"] = reference_offset
        kwargs["reference_header_length"] = header_bytes - reference_offset
    d = zlib.decompressobj()
    try:
        decompressed = d.decompress(data[header_bytes:], length)
    except zlib.error as e:
        sys.stderr.write("Error decompressing pack object of type %d, decompressed length %d, and %d header bytes!\n" % (obj_type, length, header_bytes))
        raise e
    assert len(decompressed) == length
    compressed_length = len(data) - header_bytes - len(d.unused_data)
    kwargs["header_bytes"] = header_bytes
    kwargs["obj_type"] = obj_type
    kwargs["decompressed_length"] = length
    kwargs["compressed_length"] = compressed_length
    kwargs["decompressed"] = decompressed
    return PackObject(**kwargs)

def fix_pack_sha1(pdf_content, pdf_header_offset, fix = False):
    pack_offset = pdf_content.rindex("PACK", 0, pdf_header_offset)
    version, num_objects = struct.unpack("!II", pdf_content[pack_offset + 4:pack_offset + 12])
    print "Found git pack version %d containing %d objects" % (version, num_objects)
    start_offset = pack_offset + 12
    offset = start_offset
    bytes_since_pdf = None
    pdf_length = None
    offset_delta = 0
    for i in range(num_objects):
        #print "Offset: 0x%x" % offset
        obj = parse_pack_object(pdf_content[offset:])
        #print "Parsed pack object at offset 0x%x of type %d with a %d byte header, %d byte body (decompressed), and %d byte body (compressed)" % (offset, obj_type, header_bytes, decompressed_length, compressed_length)
        if fix:
            if bytes_since_pdf is not None and obj.obj_type == OBJ_OFS_DELTA:
                if obj.reference > bytes_since_pdf:
                    # we need to update the offset to account for the fact that the PDF was moved:
                    print "Updating offset delta object #%d from pointing %d bytes back to instead point %d bytes back..." % (i+1, obj.reference, obj.reference - pdf_length)
                    new_reference = []
                    remaining_value = obj.reference - pdf_length + offset_delta
                    while remaining_value > 0:
                        new_reference.append((remaining_value & 0b1111111) | 0b10000000)
                        remaining_value >>= 7
                    new_reference[-1] &= 0b01111111
                    length_before = len(pdf_content)
                    pdf_content = pdf_content[:offset + obj.reference_header_offset] + "".join(map(chr, new_reference)) + pdf_content[offset + obj.header_bytes:]
                    offset_delta += len(new_reference) - obj.reference_header_length
                    # Sanity check:
                    assert length_before == len(pdf_content) + len(new_reference) - obj.reference_header_length
                    obj = parse_pack_object(pdf_content[offset:])
            if offset + obj.header_bytes + 2 == pdf_header_offset - 5:
                # This is the object containing the PDF, so move it to the front, while we're at it.
                print "The PDF is contained within pack object %d" % (i+1)
                print "Moving the PDF object to the front of the pack..."
                pdf_content = pdf_content[:start_offset] + pdf_content[offset:offset + obj.header_bytes + obj.compressed_length] + pdf_content[start_offset:offset] + pdf_content[offset + obj.header_bytes + obj.compressed_length:]
                pdf_length = obj.header_bytes + obj.compressed_length
                bytes_since_pdf = pdf_length
            elif bytes_since_pdf is not None:
                bytes_since_pdf += obj.header_bytes + obj.compressed_length
        offset += obj.header_bytes + obj.compressed_length
    print "SHA1 should be at offset 0x%x" % offset
    sha1 = hashlib.sha1(pdf_content[pack_offset:offset])
    print sha1.hexdigest()
    if sha1.digest() == pdf_content[offset:offset+20]:
        print "SHA1 is valid!"
    else:
        print "SHA1 is not valid!"
        if fix:
            print "Repairing the SHA1..."
            pdf_content = pdf_content[:offset] + sha1.digest() + pdf_content[offset+20:]
    return pdf_content
    
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
    initial_repair = fix_pack_sha1(pdf_content, pdf_header_offset)
    assert initial_repair == pdf_content # Make sure the input has a valid SHA1
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
    pdf_content = fix_pack_sha1(pdf_content, pdf_header_offset, fix = True)
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
