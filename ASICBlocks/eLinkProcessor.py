import numpy as np
import pandas as pd


def findHeaderWord(vals):
    x = np.vectorize(int)(vals,16)
    GoodHeader = ((x>>28)==5) & ((x&15)==5)

    x_prevBX = np.append(x[-1:],x[:-1])
    previousIDLE = ((x_prevBX==2630667468) | (x_prevBX==2899102924))
    return GoodHeader & previousIDLE

def unpackHeader(vHex):
    x = int(vHex,16)
    hammingBits = (x>>4) & ((2**3) - 1)
    orbitNum = (x>>7) & ((2**3) - 1)
    eventNum = (x>>10) & ((2**6) - 1)
    bxNum    = (x>>16) & ((2**12) - 1)
    return bxNum, eventNum, orbitNum, hammingBits

def unpackCommonModes(vHex):
    x = int(vHex,16)
    CM1 = x & ((2**10)-1)
    CM2 = x & ((2**10)-1)
    return CM1, CM2

def unpackChannelData(vHex):
    x = int(vHex,16)

    tc = (x>>31) & 1
    tp = (x>>30) & 1

    adcm1 = (x>>20) & (2**10 - 1)
    adc_tot = (x>>10) & (2**10 - 1)
    toa = (x) & (2**10 - 1)

    return tc, tp, adcm1, adc_tot, toa

# TODO
# Order of this needs to be verified (just taking from wikipedia Hamming(7,4) page right now
hammingCodes = {'0000':'00000000',
                '1000':'11100001',
                '0100':'01111001',
                '1100':'01111000',
                '0010':'01010101',
                '1010':'10110100',
                '0110':'11001100',
                '1110':'00101101',
                '0001':'11010010',
                '1001':'00110011',
                '0101':'01001011',
                '1101':'10101010',
                '0011':'10000111',
                '1011':'01100110',
                '0111':'00011110',
                '1111':'11111111'}

def formatChannelData(row, k, lam, beta, CE, CI, CIm1):
    if row.Ch==-1: return '',''

    TC = row.TC==1
    TP = row.TP==1

    if TC: #Automatic full readout for TCTP=11 or Invalid Code (TCTCP=10)
        word = '{0:01b}'.format(TC)
        word += '{0:01b}'.format(TP)
        word += '{0:010b}'.format(row.ADCm1)
        word += '{0:010b}'.format(row.ADC_TOT)
        word += '{0:010b}'.format(row.TOA)

        if TP:
            word40 = word + hammingCodes['1100']
        else:
            word40 = word + hammingCodes['1000']

        return word, word40

    if TP: #No ZS or BX-1 ZS applied, but TOA suppresed for TCTP=01
        word = '0010'
        word += '{0:010b}'.format(row.ADCm1)
        word += '{0:010b}'.format(row.ADC_TOT)

        word40 = word + '00000000' + hammingCodes['0010']

        return word, word40

    threshold = ((int(lam*row.CMAvg)>>6) +
                 (int(k*row.ADCm1)>>5) +
                 CI[row.Ch] )

    passZS = (row.ADC_TOT + CE) > threshold

    if not passZS: #fails ZS
        word = ''

        word40 = '{0:032b}'.format(0) + hammingCodes['1111']

        return word, word40

    passZSm1 = row.ADCm1 > (8*CIm1[row.Ch] + (int(beta * row.CMAvg)>>7))

    passZSTOA = row.TOA>0

    if (passZSm1) and (not passZSTOA): #TOA ZS
        word = '0000'
        word += '{0:010b}'.format(row.ADCm1)
        word += '{0:010b}'.format(row.ADC_TOT)

        word40 = word + '00000000' + hammingCodes['0000']

        return word, word40

    if (not passZSm1) and (not passZSTOA): #ADC(-1) and TOA ZS
        word = '0001'
        word += '{0:010b}'.format(row.ADC_TOT)
        word += '00'

        word40 = word + '00000000' + '00000000' + hammingCodes['0001']

        return word, word40

    if (not passZSm1) and (passZSTOA): #ADC(-1) ZS
        word = '0011'
        word += '{0:010b}'.format(row.ADC_TOT)
        word += '{0:010b}'.format(row.TOA)

        word40 = word + '00000000' + hammingCodes['0011']

        return word, word40

    if passZSm1 and passZSTOA: #ADC(-1), ADC, TOA pass ZS
        word = '01'
        word += '{0:010b}'.format(row.ADCm1)
        word += '{0:010b}'.format(row.ADC_TOT)
        word += '{0:010b}'.format(row.TOA)

        word40 = word + hammingCodes['0100']

        return word, word40


def getReadCycle(vals):

    isDataStart = findHeaderWord(vals)

    N = len(vals)
    readPattern = np.array([70,80] + list(range(37)) + [90,99])


    readCycle = np.ones_like(vals)*-9

    readStart = np.arange(N)[isDataStart]
    readStop = readStart+41
    readStop[readStop>N] = N
    readLen = readStop-readStart

    for j in range(len(readStart)):
        readCycle[readStart[j]:readStop[j]] = readPattern[:readLen[j]]

    return readCycle

def getHeader(data, readCycle, i_eRx):
    # parse header information, setup columns for this data
    headerData = np.where(readCycle==70,
                          np.vectorize(unpackHeader)(data),
                          np.nan)

    dfHeader = pd.DataFrame(headerData.T,columns=[f'BX_eRx{i_eRx}',f'Evt_eRx{i_eRx}',f'Orbit_eRx{i_eRx}',f'Hamming_eRx{i_eRx}'])

    return dfHeader

def getCommonMode(data, readCycle, i_eRx):
    #parse common mode words, populating CM1, CM2, and CM
    CM = np.where(readCycle==80,
                  np.vectorize(unpackCommonModes)(data),
                  np.nan)
#                  np.where(readCycle<0,-1,np.nan))

    dfCommonMode = pd.DataFrame(CM.T,columns=[f'CM_{i_eRx*2}',f'CM_{i_eRx*2+1}'])

    return dfCommonMode


def getChannelData(data, readCycle):

    #unpack channel data
    chData = np.where((readCycle>=0) & (readCycle<37),
                      np.vectorize(unpackChannelData)(data),
                      -1)

    Ch = np.where((readCycle>=0) & (readCycle<37),
                  readCycle,
                  -1)

    dfChannel = pd.DataFrame(chData.T,columns=[f'TC',f'TP',f'ADCm1',f'ADC_TOT',f'TOA'])

    dfChannel[f'Ch'] = Ch

    return dfChannel

def commonModeMuxAndAvg(dfCommonMode, CM_MUX):
    #clean CM_MUX values
    CM_MUX[CM_MUX>23]=23
    CM_MUX[CM_MUX<0]=0

    muxOrderedColumns = [f'CM_{i}' for i in CM_MUX]
    dfCommonModeMuxed = dfCommonMode[muxOrderedColumns]
    dfCommonModeMuxed.columns = [f'CM_{i}' for i in range(24)]

    dfCommonModeMuxed['CM_AVG'] = dfCommonModeMuxed.mean(axis=1)

    #common mode average groupings
    cm_avg_group = [['CM_0','CM_1','CM_2','CM_3'],
                    ['CM_4','CM_5','CM_6','CM_7'],
                    ['CM_8','CM_9','CM_10','CM_11'],
                    ['CM_12','CM_13','CM_14','CM_15'],
                    ['CM_16','CM_17','CM_18','CM_19'],
                    ['CM_20','CM_21','CM_22','CM_23']]

    for i in range(6):
        dfCommonModeMuxed[f'CM_AVG_{i}'] = dfCommonModeMuxed[cm_avg_group[i]].mean(axis=1)

    return dfCommonModeMuxed[['CM_AVG'] + [f'CM_AVG_{i}' for i in range(6)]]

def eLinkProcessor(df_eRx, k=1., lam=1., beta=1., CE=10, CI=np.array([10]*37), CIm1=np.array([10]*37), CM_MUX=np.arange(24)):

    dfHeader = pd.DataFrame(index=df_eRx.index)
    dfCommonMode = pd.DataFrame(index=df_eRx.index)
    dfChannelData = [] #pd.DataFrame(index=df_eRx.index)

    data = df_eRx['eRx0'].values
    readCycle = getReadCycle(data)
    for i_eRx in range(12):
        data = df_eRx[f'eRx{i_eRx}'].values

        dfHeader = dfHeader.join(getHeader(data,readCycle,i_eRx))
        dfCommonMode = dfCommonMode.join(getCommonMode(data,readCycle,i_eRx))
        dfChannelData.append(getChannelData(data,readCycle))

    #compare all BX/Evt/Orbit numbers take most common
    dfHeader.dropna(how='all',inplace=True)
    dfHeader['BX'] = dfHeader[[f'BX_eRx{i}' for i in range(12)]].mode(axis=1)
    dfHeader['Evt'] = dfHeader[[f'Evt_eRx{i}' for i in range(12)]].mode(axis=1)
    dfHeader['Orbit'] = dfHeader[[f'Orbit_eRx{i}' for i in range(12)]].mode(axis=1)

    dfCommonMode.dropna(how='all',inplace=True)
    dfCM_AVG = commonModeMuxAndAvg(dfCommonMode, CM_MUX)

    # mapping to which CM average gets used for each eRx
    # Question: Is this going to be programmable, or will be fixed
    CM_AVG_Map = {0 : 'CM_AVG_0',
                  1 : 'CM_AVG_0',
                  2 : 'CM_AVG_1',
                  3 : 'CM_AVG_1',
                  4 : 'CM_AVG_2',
                  5 : 'CM_AVG_2',
                  6 : 'CM_AVG_3',
                  7 : 'CM_AVG_3',
                  8 : 'CM_AVG_4',
                  9 : 'CM_AVG_4',
                  10: 'CM_AVG_5',
                  11: 'CM_AVG_5'}

    dfDataList = []

    sramChannelMap=pd.read_csv("PingPongSRAMChannelMap.csv")[["eRx","Ch","SRAM"]]
    for i_eRx in range(12):
        dfLink = dfChannelData[i_eRx] #[f'TC_eRx{i_eRx}',f'TP_eRx{i_eRx}',f'ADCm1_eRx{i_eRx}',f'ADC_TOT_eRx{i_eRx}',f'TOA_eRx{i_eRx}',f'Ch_eRx{i_eRx}']]
        dfLink.columns = ['TC','TP','ADCm1','ADC_TOT','TOA','Ch']

        #get CM Avg, and forward fill to all of the following channels
        dfLink['CMAvg'] = dfCM_AVG[CM_AVG_Map[i_eRx]]
        dfLink['CMAvg'] = dfLink.CMAvg.fillna(method='ffill')

        channelData = dfLink.apply(formatChannelData,args=(k, lam, beta, CE, CI, CIm1),axis=1)

        ###FINISH FROM HERE
        dfLink[[f'ChData_Short',f'ChData']] = pd.DataFrame(channelData.tolist(),columns=[f'ChData_Short',f'ChData'])
        dfLink.loc[:,'eRx'] = i_eRx
        dfLink = dfLink[['eRx','Ch','ChData_Short','ChData']].reset_index()
        dfLink.columns = ['CLK','eRx','Ch','ChData_Short','ChData']
        dfDataList.append(dfLink)

    dfFormattedData = pd.concat(dfDataList)

    dfFormattedData= dfFormattedData.merge(sramChannelMap,on=['eRx','Ch'],how='left')[['CLK','Ch','SRAM','eRx','ChData_Short','ChData']]

    return dfHeader, dfCommonMode, dfCM_AVG, dfFormattedData

