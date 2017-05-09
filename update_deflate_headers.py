#!/usr/bin/env python2

import fix_oversize_pdf
import hashlib
import math
import re
import struct
import sys
import zlib

OBJ_OFS_DELTA=6
OBJ_REF_DELTA=7

def decode_obj_ref(data):
    # from the git docs:
    # "n bytes with MSB set in all but the last one.
    # The offset is then the number constructed by
    # concatenating the lower 7 bit of each byte, and
    # for n >= 2 adding 2^7 + 2^14 + ... + 2^(7*(n-1))
    # to the result."
    bytes_read = 0
    reference = 0
    for c in map(ord, data):
        bytes_read += 1
        reference <<= 7
        reference += c & 0b01111111
        if not (c & 0b10000000):
            break
    if bytes_read >= 2:
        reference += (1 << (7 * (bytes_read - 1)))
    return reference, bytes_read

def encode_obj_ref(offset):
    assert offset >= 0
    num_bits = int(math.ceil(math.log(offset) / math.log(2)))
    num_bytes = int(math.ceil(float(num_bits) / 7.0))
    extra = 0
    original_offset = offset
    if num_bytes >= 2:
        extra = (1 << (7 * (num_bytes - 1)))
        offset -= extra
    assert offset >= 0
    ret = []
    for i in range(num_bytes):
        ret.append(((offset >> ((num_bytes - i - 1)*7)) & 0b1111111) | 0b10000000)
    ret[-1] &= 0b01111111
    ret = "".join(map(chr, ret))
    # Sanity check:
    assert decode_obj_ref(ret)[0] == original_offset
    return ret

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
        reference, reference_bytes = decode_obj_ref(data[header_bytes:])
        reference_offset = header_bytes
        header_bytes += reference_bytes
        kwargs["reference"] = reference
        kwargs["reference_header_offset"] = reference_offset
        kwargs["reference_header_length"] = reference_bytes
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

def fix_pack_sha1(pdf_content, pdf_header_offset, fix = False, pdf_size_delta = 0):
    pack_offset = pdf_content.rindex("PACK", 0, pdf_header_offset)
    version, num_objects = struct.unpack("!II", pdf_content[pack_offset + 4:pack_offset + 12])
    print "Found git pack version %d containing %d objects" % (version, num_objects)
    start_offset = pack_offset + 12
    offset = start_offset
    bytes_since_pdf = None
    pdf_length = None
    offset_delta = pdf_size_delta
    for i in range(num_objects):
        #print "Offset: 0x%x" % offset
        obj = parse_pack_object(pdf_content[offset:])
        #print "Parsed pack object at offset 0x%x of type %d with a %d byte header, %d byte body (decompressed), and %d byte body (compressed)" % (offset, obj_type, header_bytes, decompressed_length, compressed_length)
        if fix:
            if obj.obj_type == OBJ_OFS_DELTA:
                raise Exception('We don\'t currently support fixing OBJ_OFS_DELTA objects! Try running `git pack-objects` with the delta-base-offset argument.')
            elif offset + obj.header_bytes + 2 == pdf_header_offset - 5:
                # This is the object containing the PDF, so move it to the front, while we're at it.
                print "The PDF is contained within pack object %d" % (i+1)
                print "Moving the PDF object to the front of the pack..."
                pdf_content = pdf_content[:start_offset] + pdf_content[offset:offset + obj.header_bytes + obj.compressed_length] + pdf_content[start_offset:offset] + pdf_content[offset + obj.header_bytes + obj.compressed_length:]
                pdf_length = obj.header_bytes + obj.compressed_length
                bytes_since_pdf = 0
            elif bytes_since_pdf is not None:
                bytes_since_pdf += obj.header_bytes + obj.compressed_length
        offset += obj.header_bytes + obj.compressed_length
    print "SHA1 should be at offset 0x%x" % offset
    sha1 = hashlib.sha1(pdf_content[pack_offset:offset])
    print sha1.hexdigest()
    if sha1.digest() == pdf_content[offset:offset+20]:
        print "SHA1 is valid!"
        return pdf_content
    else:
        print "SHA1 is not valid!"
        if fix:
            print "Repairing the SHA1..."
            pdf_content = pdf_content[:offset] + sha1.digest() + pdf_content[offset+20:]
            # Validate that we've repaired it:
            return fix_pack_sha1(pdf_content, pdf_header_offset)
        return None
    
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
    header = "".join(header)
    # Sanity check:
    assert read_deflate_header(header) == (last, length)
    return header

def find_deflate_headers(data):
    last = False
    offset = 0
    i = 0
    while not last:
        i += 1
        try:
            last, length = read_deflate_header(data[offset:offset + 5])
        except Exception as e:
            actual_header = None
            for j in reduce(lambda x, y : x + y, map(lambda n : (-n,n), range(1,0x8000))):
                try:
                    last, length = read_deflate_header(data[offset + j:offset + j + 5])
                    actual_header = j
                    break
                except Exception:
                    pass
            if actual_header is not None:
                raise Exception("Bad DEFLATE header (#%d) at offset %d; it looks like the length was off by %d" % (i, offset, actual_header));
            else:
                raise Exception("Bad DEFLATE header (#%d) at offset %d" % (i, offset));
        yield offset, last, length
        offset += 5 + length

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

    idx = 0
    for offset, last, length in find_deflate_headers(pdf_content[pdf_header_offset-5:]):
        if idx == 0:
            if last:
                print "The entire PDF fits in a single DEFLATE block; nothing needed!"
                return
            idx += 1
            continue
        elif idx == 1:
            print "Deleting the unwanted DEFLATE headers..."
            pdf_size_delta = 0
        header_offset = pdf_header_offset - 5 * idx + offset
        pdf_content = pdf_content[:header_offset] + pdf_content[header_offset + 5:]
        print "Deleted DEFLATE header at offset 0x%x for a %d byte block" % (header_offset, length)
        pdf_size_delta -= 5
        idx += 1
    
    print "Updating the first DEFLATE header..."
    pdf_content = pdf_content[:pdf_header_offset + block_offsets[0][0]] + make_deflate_header(False, block_offsets[0][1]) + pdf_content[pdf_header_offset:]
    print "Updating the injected DEFLATE headers..."
    for idx, block in enumerate(block_offsets[1:]):
        last = (idx == len(block_offsets) - 2)
        offset, length, added_bytes = block
        print "Injecting DEFLATE header at offset 0x%x for a %d byte block" % (pdf_header_offset + offset, length)
        # Sanity check: the injection position should be preceeded by a PDF comment
        assert pdf_content[pdf_header_offset + offset - 3:pdf_header_offset + offset] == '%% '
        pdf_content = pdf_content[:pdf_header_offset + offset] + make_deflate_header(last, length) + pdf_content[pdf_header_offset + offset:]
        pdf_size_delta += 5
    content_after = zlib.decompress(pdf_content[pdf_header_offset - 7:])
    print "Validating the resulting DEFLATE headers..."
    if content_before != content_after:
       raise Exception("Error: the updated DEFLATE output is corrupt!")
    sys.stdout.write("Updating the DEFLATE headers ")
    if pdf_size_delta == 0:
        sys.stdout.write("did not change the size of the PDF object\n")
    else:
        if pdf_size_delta > 0:
            sys.stdout.write("added %d bytes to" % pdf_size_delta)
        else:
            sys.stdout.write("removed %d bytes from" % (pdf_size_delta * -1))
        sys.stdout.write(" the PDF object\n")
    sys.stdout.flush()
    pdf_content = fix_pack_sha1(pdf_content, pdf_header_offset, fix = True, pdf_size_delta = pdf_size_delta)
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
