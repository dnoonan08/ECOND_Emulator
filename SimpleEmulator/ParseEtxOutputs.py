import numpy as np
import crcmod,codecs

def toHex(x):
    if len(x)==0:
        return ''
    elif len(x)==16:
        return f'{int(x,2):04X}'
    elif len(x)==24:
        return f'{int(x,2):06X}'
    elif len(x)==32:
        return f'{int(x,2):08X}'
toHexV=np.vectorize(toHex)

def parseIdle(Idle):
    BuffStat=Idle&0x7
    Err=(Idle>>3)&0x7
    RR=(Idle>>6)&0b11
    Pattern=(Idle>>8)
    return Pattern, RR, Err, BuffStat

def parseHeaderWord0(HeaderWord0):
    HdrMarker=(HeaderWord0>>23)&0x1ff
    PayloadLength=(HeaderWord0>>14)&0x1ff
    P=(HeaderWord0>>13)&0x1
    E=(HeaderWord0>>12)&0x1
    HT=(HeaderWord0>>10)&0x3
    EBO=(HeaderWord0>>8)&0x3
    M=(HeaderWord0>>7)&0x1
    T=(HeaderWord0>>6)&0x1
    Hamming=(HeaderWord0>>0)&0x3f
    return HdrMarker, PayloadLength, P, E, HT, EBO, M, T, Hamming

def parseHeaderWord1(HeaderWord1):
    BX=(HeaderWord1>>20)&0xfff
    L1A=(HeaderWord1>>14)&0x3f
    Orb=(HeaderWord1>>11)&0x7
    S=(HeaderWord1>>10)&0x1
    RR=(HeaderWord1>>8)&0x3
    CRC=(HeaderWord1)&0xff
    return BX, L1A, Orb, S, RR, CRC

def parsePacketHeader(packetHeader0,packetHeader1=0,asHex=True):
    Stat=(packetHeader0>>29)&0x7
    Ham = (packetHeader0>>26)&0x7
    F=(packetHeader0>>25)&0x1
    CM0=(packetHeader0>>15)&0x3ff
    CM1=(packetHeader0>>5)&0x3ff
    if F==1:
        E=(packetHeader0>>4)&0x1
    else:
        E=0
    ChMap=((packetHeader0&0x1f)<<32)+packetHeader1
    if asHex:
        return f'{Stat:01x}',f'{Ham:01x}',f'{F:01x}',f'{CM0:03x}',f'{CM1:03x}',f'{E:01x}',f'{ChMap:010x}',
    else:
        return Stat, Ham, F, CM0, CM1, E, ChMap

crc = crcmod.mkCrcFun(0x104c11db7,initCrc=0, xorOut=0, rev=False)

def parseDAQLink(eLinkData):
    DAQ_eRx_int=np.vectorize(lambda x: int(x,16))(eLinkData)
    #parse header
    goodHeaderTrailer=(((((DAQ_eRx_int[:,0])&0b1111)==5) | (((DAQ_eRx_int[:,0])&0b1111)==2)) &
                       (((DAQ_eRx_int[:,0]>>28)&0b1111)==5))
    hammingErrors=(DAQ_eRx_int[:,0]>>4)&0b111
    orbitNum=(DAQ_eRx_int[:,0]>>7)&0b111
    eventNum=(DAQ_eRx_int[:,0]>>10)&0b111111
    bunchNum=(DAQ_eRx_int[:,0]>>16)&0xfff

    #parse CM
    CMHeaderCheck=((DAQ_eRx_int[:,1]>>30))==0b10
    CM0=(DAQ_eRx_int[:,1]>>10)&0x3ff
    CM1=DAQ_eRx_int[:,1]&0x3ff

    #parse
    Tc=(DAQ_eRx_int[:,2:39]>>31)
    Tp=(DAQ_eRx_int[:,2:39]>>30)&1
    ADCm1=(DAQ_eRx_int[:,2:39]>>20)&0x3ff
    ADCorTOT=(DAQ_eRx_int[:,2:39]>>10)&0x3ff
    TOA=(DAQ_eRx_int[:,2:39])&0x3ff


    crcGood=np.zeros(len(eLinkData),dtype=bool)
    for i in range(len(eLinkData)):
        crcGood[i]=crc(codecs.decode((''.join(eLinkData[i])), 'hex'))==0

    return goodHeaderTrailer, hammingErrors, orbitNum, eventNum, bunchNum, CM0, CM1, Tc, Tp, ADCm1, ADCorTOT, TOA, crcGood
