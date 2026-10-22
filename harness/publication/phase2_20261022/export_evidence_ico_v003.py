"""Validated ICO resources plus pinned v002 mixed-log export policy.

Only .ico or extensionless resources with an actual valid ICO container gain
binary support. All payload bytes still undergo the parent's binary secret scan.
"""
from contextlib import contextmanager
import argparse
from pathlib import Path
import re
import struct
import sys
import zlib

import export_evidence as base
import export_evidence_logtext_v002 as logs


PARENT_SHA256 = "fbbaea885afae45876d8f67e7b5aea298908e1b510d2a75c24d063857e001ec5"
LOG_WRAPPER_SHA256 = "788063e3ac8f9f26fd3b2cf611207951a223b49e3fa680c6030c5c5ed5e5464b"
ICO_MAGIC = b"\x00\x00\x01\x00"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def exact(stream,size):
    value=stream.read(size)
    if len(value)!=size: raise ValueError("truncated ICO structure requires explicit review")
    return value


def validate_png(stream,offset,size,width,height):
    stream.seek(offset)
    if exact(stream,8)!=PNG_MAGIC: raise ValueError("invalid embedded ICO PNG signature")
    end=offset+size; cursor=offset+8; first=True; seen_idat=False; seen_iend=False
    decoder=zlib.decompressobj(); decoded=0; bound=2*1024*1024
    while cursor+12<=end:
        stream.seek(cursor); length,kind=struct.unpack('>I4s',exact(stream,8))
        if length>end-cursor-12 or not re.fullmatch(rb'[A-Za-z]{4}',kind):
            raise ValueError("invalid embedded ICO PNG chunk bounds")
        if first and (kind!=b'IHDR' or length!=13): raise ValueError("ICO PNG must begin with IHDR")
        if not first and kind==b'IHDR': raise ValueError("duplicate ICO PNG IHDR")
        if kind[0]&32==0 and kind not in {b'IHDR',b'PLTE',b'IDAT',b'IEND'}:
            raise ValueError("unsupported critical ICO PNG chunk")
        checksum=zlib.crc32(kind); remaining=length; header=b''
        while remaining:
            chunk=exact(stream,min(base.CHUNK,remaining)); remaining-=len(chunk)
            checksum=zlib.crc32(chunk,checksum)
            if kind==b'IHDR': header+=chunk
            if kind==b'IDAT':
                seen_idat=True
                try: decoded+=len(decoder.decompress(chunk,bound-decoded+1))
                except zlib.error: raise ValueError("invalid ICO PNG raster stream") from None
                if decoded>bound or decoder.unconsumed_tail:
                    raise ValueError("oversized ICO PNG raster stream")
        if (checksum&0xffffffff)!=struct.unpack('>I',exact(stream,4))[0]:
            raise ValueError("ICO PNG checksum mismatch")
        if kind==b'IHDR':
            w,h,bits,color,compression,filtering,interlace=struct.unpack('>IIBBBBB',header)
            allowed={0:{1,2,4,8,16},2:{8,16},3:{1,2,4,8},4:{8,16},6:{8,16}}
            if (w,h)!=(width,height) or color not in allowed or bits not in allowed[color] or compression!=0 or filtering!=0 or interlace not in {0,1}:
                raise ValueError("invalid ICO PNG image header")
        cursor+=length+12; first=False
        if kind==b'IEND':
            if length!=0 or cursor!=end: raise ValueError("ICO PNG trailing bytes or malformed IEND")
            seen_iend=True; break
    if not seen_idat or not seen_iend or not decoder.eof or decoder.unused_data or decoded==0:
        raise ValueError("incomplete ICO PNG image")


def validate_ico(stream):
    stream.seek(0,2); total=stream.tell(); stream.seek(0)
    if total>base.MAX_MEMBER: raise ValueError("oversized ICO resource")
    reserved,kind,count=struct.unpack('<HHH',exact(stream,6))
    if reserved!=0 or kind!=1 or not 1<=count<=256: raise ValueError("invalid ICO header")
    directory_end=6+16*count
    if directory_end>total: raise ValueError("truncated ICO directory")
    entries=[]
    for _ in range(count):
        width,height,palette,padding,planes,bits,size,offset=struct.unpack('<BBBBHHII',exact(stream,16))
        width=width or 256; height=height or 256
        if padding!=0 or planes!=1 or bits!=32 or palette!=0 or size<8 or offset<directory_end or offset+size>total:
            raise ValueError("unsupported or malformed ICO directory entry")
        entries.append((offset,size,width,height))
    cursor=directory_end
    for offset,size,width,height in sorted(entries):
        if offset!=cursor: raise ValueError("ICO directory overlaps, gaps or unreferenced payload")
        cursor=offset+size
        stream.seek(offset); header=exact(stream,8)
        if header==PNG_MAGIC:
            validate_png(stream,offset,size,width,height)
        else:
            stream.seek(offset)
            if size<40: raise ValueError("truncated ICO DIB")
            h,w,dh,planes,bits,compression,image_bytes,_,_,used,_=struct.unpack('<IiiHHIIiiII',exact(stream,40))
            minimum=width*height*4+((width+31)//32)*4*height
            if h!=40 or w!=width or dh!=height*2 or planes!=1 or bits!=32 or compression!=0 or used!=0:
                raise ValueError("unsupported or malformed ICO DIB image")
            if size<40+minimum or image_bytes not in {0,size-40}:
                raise ValueError("ICO DIB image size mismatch")
    if cursor!=total: raise ValueError("unreferenced trailing ICO bytes")
    stream.seek(0)


def transform_ico(source,target,filename,counts,*,depth=0,archive_exclusions=None,logical_path=None):
    head=source.read(4); source.seek(0)
    if Path(filename).suffix.casefold() in {'.ico',''} and head==ICO_MAGIC:
        if depth>base.MAX_DEPTH: raise ValueError("nested archive limit")
        validate_ico(source)
        base._binary_copy(source,target)
        return False
    return logs.transform_log_text(source,target,filename,counts,depth=depth,archive_exclusions=archive_exclusions,logical_path=logical_path)


def write_with_lineage(path,value):
    if Path(path).name=='export-manifest.pending.json':
        value=dict(value)
        value['parent_generator_sha256']=value['generator_sha256']
        value['format_wrapper_parent_sha256']=LOG_WRAPPER_SHA256
        value['generator_sha256']=base.file_hash(Path(__file__))
        value['generator_version']='validated_ico_and_mixed_log_v003'
        value['format_policy']={'mixed_log_policy':'unchanged pinned v002',
                               'new_binary_format':'structurally validated ICO: 32bpp uncompressed BITMAPINFOHEADER40 DIB or validated embedded PNG',
                               'new_binary_scope':['.ico','extensionless ICO resources'],
                               'credential_scan':'entire ICO payload still uses parent binary secret scanner; all ZIP/text recursion retained',
                               'strict_structured_formats':'parent JSON/JSONL/trace/network unchanged'}
    logs.ORIGINAL_WRITE(path,value)


@contextmanager
def ico_policy():
    if base.file_hash(Path(base.__file__))!=PARENT_SHA256 or base.file_hash(Path(logs.__file__))!=LOG_WRAPPER_SHA256:
        raise ValueError("pinned parent exporter/wrapper SHA256 mismatch")
    old_transform,old_write=base.transform_stream,base.write_new
    base.transform_stream,base.write_new=transform_ico,write_with_lineage
    try: yield
    finally: base.transform_stream,base.write_new=old_transform,old_write


def main():
    if len(sys.argv)>1 and sys.argv[1]=='sharded-export':
        # Coordinator only; the unchanged runner invokes this same wrapper's
        # ordinary `export` subcommand for each isolated child process.
        import run_export_shards_v001 as runner
        parser=argparse.ArgumentParser(description='Failed-only ICO/log retry using the unchanged shard coordinator')
        parser.add_argument('command',choices=['sharded-export'])
        parser.add_argument('--source-root',type=Path,required=True)
        parser.add_argument('--inventory',type=Path,required=True)
        parser.add_argument('--inventory-sha256')
        parser.add_argument('--output-dir',type=Path,required=True)
        parser.add_argument('--shards',type=int,choices=range(1,9),default=8)
        parser.add_argument('--jobs',type=int,choices=range(1,9),default=8)
        args=parser.parse_args()
        result=runner.run_shards(args.source_root,args.inventory,args.output_dir,shards=args.shards,jobs=args.jobs,
                                 inventory_sha256=args.inventory_sha256,exporter=Path(__file__))
        raise SystemExit(0 if result['status']=='exported_pending_independent_approval' else 2)
    with ico_policy(): base.main()


if __name__=='__main__': main()
