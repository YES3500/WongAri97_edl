#!/usr/bin/env python3
import sys
from struct import unpack
from queue import Queue
try:
    from Library.utils import LogBase, print_progress
except Exception as e:
    import os,sys,inspect
    current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
    parent_dir = os.path.dirname(current_dir)
    sys.path.insert(0, parent_dir)
    from Library.utils import LogBase, print_progress


class QCSparse(metaclass=LogBase):
    def __init__(self,filename):
        self.rf=open(filename,'rb')
        self.data=Queue()
        self.offset=0
        self.tmpdata=bytearray()

    def readheader(self):
        header = unpack("<I4H4I", self.rf.read(0x1C))
        magic = header[0]
        self.major_version = header[1]
        self.minor_version = header[2]
        self.file_hdr_sz = header[3]
        self.chunk_hdr_sz = header[4]
        self.blk_sz = header[5]
        self.total_blks = header[6]
        self.total_chunks = header[7]
        self.image_checksum = header[8]
        if magic!=0xED26FF3A:
            return False
        if self.file_hdr_sz != 28:
            self.__logger.error("The file header size was expected to be 28, but is %u." % self.file_hdr_sz)
            return False
        if self.chunk_hdr_sz != 12:
            self.__logger.error("The chunk header size was expected to be 12, but is %u." % self.chunk_hdr_sz)
            return False
        return True

    def unsparse(self):
        if self.total_blks < self.offset:
            self.__logger.error("The header said we should have %u output blocks, but we saw %u" % (self.total_blks, self.offset))
            return -1
        header = unpack("<2H2I", self.rf.read(self.chunk_hdr_sz))
        chunk_type = header[0]
        chunk_sz = header[2]
        total_sz = header[3]
        data_sz = total_sz - 12
        if chunk_type == 0xCAC1:
            if data_sz != (chunk_sz * self.blk_sz):
                self.__logger.error("Raw chunk input size (%u) does not match output size (%u)" % (data_sz, chunk_sz * self.blk_sz))
                return -1
            else:
                self.__logger.debug("Raw data")
                data = self.rf.read(chunk_sz * self.blk_sz)
                self.offset += chunk_sz
                return data
        elif chunk_type == 0xCAC2:
            if data_sz != 4:
                self.__logger.error("Fill chunk should have 4 bytes of fill, but this has %u" % data_sz)
                return -1
            else:
                fill_bin = self.rf.read(4)
                fill = unpack("<I", fill_bin)
                self.__logger.debug(format("Fill with 0x%08X" % fill))
                data = fill_bin * (chunk_sz * self.blk_sz // 4)
                self.offset += chunk_sz
                return data
        elif chunk_type == 0xCAC3:
            data=b'\x00' * chunk_sz * self.blk_sz
            self.offset += chunk_sz
            return data
        elif chunk_type == 0xCAC4:
            if data_sz != 4:
                self.__logger.error("CRC32 chunk should have 4 bytes of CRC, but this has %u" % data_sz)
                return -1
            else:
                crc_bin = self.rf.read(4)
                crc = unpack("<I", crc_bin)
                self.__logger.debug(format("Unverified CRC32 0x%08X" % crc))
                return b""
        else:
            self.__logger.debug("Unknown chunk type 0x%04X" % chunk_type)
            return -1

    def read(self,length=None):
        if length==None:
            return self.unsparse()
        if length<=len(self.tmpdata):
            tdata=self.tmpdata[:length]
            self.tmpdata=self.tmpdata[length:]
            return tdata
        while len(self.tmpdata)<length:
            self.tmpdata.extend(self.unsparse())
            if length<=len(self.tmpdata):
                tdata = self.tmpdata[:length]
                self.tmpdata = self.tmpdata[length:]
                return tdata

if __name__=="__main__":
    if len(sys.argv)<3:
        print("./sparse.py <sparse_partition.img> <outfile>")
        sys.exit()
    sp=QCSparse(sys.argv[1])
    if sp.readheader():
        print("Extracting sectors to "+sys.argv[2])
        with open(sys.argv[2],"wb") as wf:
            old=0
            while sp.offset<sp.total_blks:
                prog=int(sp.offset / sp.total_blks * 100)
                if prog>old:
                    print_progress(prog, 100, prefix='Progress:', suffix='Complete', bar_length=50)
                    old=prog
                data=sp.read()
                if data==b"" or data==-1:
                    break
                wf.write(data)
            if len(sp.tmpdata)>0:
                wf.write(sp.tmpdata)
                sp.tmpdata=bytearray()
            print_progress(100, 100, prefix='Progress:', suffix='Complete', bar_length=50)
        print("Done.")