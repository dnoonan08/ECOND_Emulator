import pandas as pd
import numpy as np

from .HeaderSyncCheck import headerSyncCheck
from .EBO_Counters import eboCounter
from .ROC_SM_StateDefinitions import StateToValMapping, packetStateProgression

def L1A_Predictor(L1A,
                  L1A_latency_HGCROC,
                  L1A_latency_Aligner,
                  N=-1
                 ):

    if N==-1:
        N=len(L1A)
    arr_Header_Predictor=np.array([0]*N,dtype=int)

    L1A_delay_counter = 0
    L1A_predictor_count = 0
    Total_L1A_Latency = L1A_latency_HGCROC + L1A_latency_Aligner
    L1A_withLatency = np.zeros_like(L1A)
    L1A_withLatency[Total_L1A_Latency:] = L1A[:-1*Total_L1A_Latency]

    for i in range(N):
        Header_Predictor=0
        if L1A_withLatency[i]==1:
            L1A_predictor_count += 1 #count how many L1A's would be in the predictor fifo

        if L1A_delay_counter==0:
            if L1A_predictor_count>0:
                Header_Predictor = 1
                L1A_predictor_count -= 1
                L1A_delay_counter = 40
        else:
            L1A_delay_counter -= 1
        arr_Header_Predictor[i] = Header_Predictor

    return arr_Header_Predictor

def StateMachine_Loop(simpleMode,
                      GoodHeaderWord,
                      GoodSyncWord,
                      LinkReset,
                      ChipSync,
                      EBR,
                      L1A,
                      NZS,
                      Event,
                      Bunch,
                      Orbit,
                      HardReset,
                      SoftReset,
                      L1A_Prediction,
                      PingPong_Flush=None,
                      ALIGNMENT_STEP1_PERIOD=255,
                      ALIGNMENT_STEP2_PERIOD=1,
                      N=-1):

    if N==-1:
        N=len(GoodHeaderWord)

    if PingPong_Flush is None:
        PingPong_Flush=np.zeros(N,dtype=bool)

    arr_state=np.array(['']*N,dtype='<U16')
    arr_topEvent=np.zeros(N,dtype=int)
    arr_topBunch=np.zeros(N,dtype=int)
    arr_topOrbit=np.zeros(N,dtype=int)
    arr_topNZS=np.zeros(N,dtype=int)
    arr_L1AFifoEmpty=np.zeros(N,dtype=bool)
    arr_L1AFifoFull=np.zeros(N,dtype=bool)
    arr_PacketComplete=np.zeros(N,dtype=int)
    arr_EmptyHeader=np.zeros(N,dtype=int)
    arr_EmptyHeaderFifo = np.array([[[-1,-1,-1,-1]]*8]*N,dtype=int)
    arr_PP_SM = np.array(['']*N,dtype='<U2')
    arr_PP_READ_STATE = np.array(['']*N,dtype='<U5')


    L1AFIFO = np.array([[-1,-1,-1,-1]]*129)
    writePointer = 0

    state='HOME'
    stateNext='HOME'
    L1A_FIFO_EMPTY=True
    L1A_FIFO_FULL=False
    Top_Event=-1
    Top_Bunch=-1
    Top_Orbit=-1
    Top_NZS=-1
    Header_Predictor=0

    emptyHeaderFifo = np.array([[-1,-1,-1,-1]]*9,dtype=int)
    EmptyHeaderFifoWritePointer = 0

    AlignmentCounter=-1

    PP_State='S0'
    PP_StateNext='S0'
    PP_Read_State='CLK0'
    PP_Read_StateNext='CLK0'

    HGCROC_Packet_Complete=False

    for i in range(N):

        ###########################
        # ROC DAQ STATE MACHINE
        ###########################
        if state == 'HOME':
            if not simpleMode:
                if (L1A_Prediction[i]==1) and (GoodHeaderWord[i]==0):
                    stateNext = 'EMPTYHEADER'
                elif (L1A_Prediction[i]==1) and (GoodHeaderWord[i]==1):
                    stateNext = 'STANDARDHEADER'
                elif (L1A_Prediction[i]==0) and (GoodHeaderWord[i]==1):
                    stateNext = 'UNEXPECTEDHEADER'
                elif (ChipSync[i]==1) or (EBR[i]==1):
                    stateNext = 'CSYNC'
                elif (LinkReset[i]==1) and (GoodSyncWord[i]==1):
                    stateNext = 'ALIGNRESET'
                else:
                    stateNext = 'HOME'
            else:
                if (GoodSyncWord[i]==0) and (GoodHeaderWord[i]==1) and (not L1A_FIFO_EMPTY):
                    stateNext = 'STANDARDHEADER'
                elif (GoodSyncWord[i]==0) and (GoodHeaderWord[i]==1) and (L1A_FIFO_EMPTY):
                    stateNext = 'UNEXPECTEDHEADER'
                elif (ChipSync[i]==1) or (EBR[i]==1):
                    stateNext = 'CSYNC'
                elif (LinkReset[i]==1) and (GoodSyncWord[i]==1):
                    stateNext = 'ALIGNRESET'
                else:
                    stateNext = 'HOME'
        elif state == 'EMPTYHEADER':
            if (L1A_Prediction[i]==0) and (GoodHeaderWord[i]==1):
                stateNext = 'UNEXPECTEDHEADER'
            else:
                stateNext = 'HOME'

        elif state == 'CSYNC':
            if GoodSyncWord[i]==1:
                stateNext = 'HOME'
            else:
                stateNext = 'CSYNC'
        elif state == 'ALIGNRESET':
            AlignmentCounter=0
            stateNext = 'ALIGNSTEP1'
        elif state == 'ALIGNSTEP1':
            if AlignmentCounter>ALIGNMENT_STEP1_PERIOD:
                stateNext = 'ALIGNSTEP2'
                AlignmentCounter=0
        elif state == 'ALIGNSTEP2':
            if AlignmentCounter>ALIGNMENT_STEP2_PERIOD:
                stateNext = 'HOME'
                AlignmentCounter=-1
        elif state in packetStateProgression:
            stateNext = packetStateProgression[state]
        else:
            print('Unknown State', state)
            #for now, just go back to home
            stateNext = 'HOME'

        if AlignmentCounter>=0:
            AlignmentCounter += 1

        #L1A FIFO
        if ((HardReset[i]==0) or (SoftReset[i]==0) or (EBR[i]==1) or (ChipSync[i]==1)):
            L1AFIFO = np.array([[-1,-1,-1,-1]]*129)
            writePointer = 0
            L1A_FIFO_EMPTY=True

        if (L1A[i]==1):
            L1AFIFO[writePointer] = [Event[i], Bunch[i], Orbit[i], NZS[i]]
            writePointer += 1

        if state=='CRC':
            #strip off top EBO
            L1AFIFO[:-1] = L1AFIFO[1:]
            writePointer = max(writePointer-1, 0)

        if state=='EMPTYHEADER':
            emptyHeaderFifo[EmptyHeaderFifoWritePointer] = L1AFIFO[0]
            EmptyHeaderFifoWritePointer += 1

            #strip off top EBO
            L1AFIFO[:-1] = L1AFIFO[1:]
            writePointer = max(writePointer-1, 0)


        EmptyHeader = EmptyHeaderFifoWritePointer>0


        ###########################
        # Ping Pong State Machine
        ###########################

        # PingPong State
        if PP_State=='S0':
            if HGCROC_Packet_Complete:
                PP_StateNext = 'S1'
            else:
                PP_StateNext = 'S0'
        elif PP_State=='S1':
            if HGCROC_Packet_Complete:
                PP_StateNext = 'S3'
            elif PingPong_Flush[i]:
                PP_StateNext = 'S2'
            else:
                PP_StateNext = 'S1'
        elif PP_State=='S2':
            if HGCROC_Packet_Complete:
                PP_StateNext = 'S3'
            else:
                PP_StateNext = 'S2'
        else:
            if HGCROC_Packet_Complete:
                PP_StateNext = 'S1'
            elif PingPong_Flush[i]:
                PP_StateNext = 'S0'
            else:
                PP_StateNext = 'S3'

        # PingPong Read State
        if PP_Read_State=='CLK0':
            if HGCROC_Packet_Complete:
                PP_Read_StateNext = 'CLK1'
            elif EmptyHeader:
                PP_Read_StateNext = 'EMPTYHDR'
            else:
                PP_Read_StateNext = 'CLK0'
        elif PP_Read_State=='EMPTYHDR':
            PP_Read_StateNext = 'CLK0'
            # peel off top of empty header fifo
            emptyHeaderFifo[:-1] = emptyHeaderFifo[1:]
            EmptyHeaderFifoWritePointer = max(EmptyHeaderFifoWritePointer-1,0)
            EmptyHeader = EmptyHeaderFifoWritePointer>0
        elif PP_Read_State=='CLK39':
            PP_Read_StateNext = 'CLK0'
        elif 'CLK' in PP_Read_State:
            n = int(PP_Read_State[3:])+1
            PP_Read_StateNext = f'CLK{n}'
        else:
            PP_Read_StateNext = 'CLK0'


        L1A_FIFO_EMPTY = (L1AFIFO==-1).all()
        L1A_FIFO_FULL = ~(L1AFIFO==-1).any()

        HGCROC_Packet_Complete = state=='CRC'
        state = stateNext
        PP_State = PP_StateNext
        PP_Read_State = PP_Read_StateNext

        #dump into arrays
        arr_state[i]=state
        arr_topEvent[i] = L1AFIFO[0][0]
        arr_topBunch[i] = L1AFIFO[0][1]
        arr_topOrbit[i] = L1AFIFO[0][2]
        arr_topNZS[i]   = L1AFIFO[0][3]
        arr_L1AFifoEmpty[i] = L1A_FIFO_EMPTY
        arr_L1AFifoFull[i]  = L1A_FIFO_FULL
        arr_EmptyHeaderFifo[i] = emptyHeaderFifo[:8]
        arr_PacketComplete[i] = HGCROC_Packet_Complete
        arr_EmptyHeader[i] = EmptyHeader

        arr_PP_SM[i] = PP_State
        arr_PP_READ_STATE[i] = PP_Read_State


    return arr_state, arr_topEvent, arr_topBunch, arr_topOrbit, arr_topNZS, arr_L1AFifoEmpty, arr_L1AFifoFull, arr_PacketComplete, arr_EmptyHeader, arr_EmptyHeaderFifo, arr_PP_SM, arr_PP_READ_STATE

def badWordCounter(State, GoodSyncWord, HardReset, SoftReset, ChipSync):
    BadWordCount = np.zeros_like(State,dtype=int)
    count = 0
    for i in range(len(State)):
        if State[i]=='HOME' and GoodSyncWord[i]==0:
            count += 1
        if HardReset[i]==0 or SoftReset[i]==0 or ChipSync[i]==1:
            count = 0
        BadWordCount[i] = count
    return BadWordCount


def ROC_DAQ_CONTROL(dfAlignerOutput,
                    dfFastCommands,
                    activeChannels,
                    idlePattern,
                    idleHeader,
                    idleHeaderBC0,
                    BCR_Bucket_Default,
                    L1A_HGCROC_Latency,
                    L1A_Aligner_Latency,
                    MatchThreshold,
                    BadWordThreshold,
                    ROC_SM_simpleMode,
                    Alignment_Step1_Period,
                    Alignment_Step2_Period):


    activeChannelMask = np.array([(activeChannels >> n) & 1 for n in range(12)], dtype=bool)

    dfHeaderSync = headerSyncCheck(dfAlignerOutput,
                                   idlePattern=idlePattern,
                                   idleHeader=idleHeader,
                                   idleHeaderBC0=idleHeaderBC0,
                                   MatchThreshold=MatchThreshold,
                                   activeChannelMask=activeChannelMask)

    dfEBO = eboCounter(dfFastCommands, BCR_Bucket_Default)

    dfInput = dfFastCommands.merge(dfEBO,left_index=True,right_index=True)
    dfInput[['GoodSyncWord','GoodHeaderWord']] = dfHeaderSync[['GoodSyncWord','GoodHeaderWord']]


    L1A_Header_Prediction = L1A_Predictor(L1A = dfInput.L1A.values,
                                          L1A_latency_HGCROC = L1A_HGCROC_Latency,
                                          L1A_latency_Aligner = L1A_Aligner_Latency)


    StateMachine_Outputs = StateMachine_Loop(simpleMode = ROC_SM_simpleMode,
                                             GoodHeaderWord = dfInput.GoodHeaderWord.values,
                                             GoodSyncWord = dfInput.GoodSyncWord.values,
                                             LinkReset = dfInput.LinkResetRocD.values,
                                             ChipSync = dfInput.ChipSync.values,
                                             EBR = dfInput.EBR.values,
                                             L1A = dfInput.L1A.values,
                                             NZS = dfInput.NZS.values,
                                             Event = dfInput.Event.values,
                                             Bunch = dfInput.Bunch.values,
                                             Orbit = dfInput.Orbit.values,
                                             HardReset = dfInput.HardReset.values,
                                             SoftReset = dfInput.SoftReset.values,
                                             L1A_Prediction=L1A_Header_Prediction,
                                             ALIGNMENT_STEP1_PERIOD=Alignment_Step1_Period,
                                             ALIGNMENT_STEP2_PERIOD=Alignment_Step2_Period)

    StateText, TopEvent, TopBunch, TopOrbit, TopNZS, L1AFifoEmpty, L1AFifoFull, PacketComplete, EmptyHeader, EmptyHeaderFifo, PP_State, PP_ReadState = StateMachine_Outputs

    BadWordCount = badWordCounter(State = StateText,
                                  GoodSyncWord = dfInput.GoodSyncWord.values,
                                  HardReset = dfInput.HardReset.values,
                                  SoftReset = dfInput.SoftReset.values,
                                  ChipSync = dfInput.ChipSync.values)

    #apply the mapping in StateToValMapping, to get the integer state from the Gray codes
    StateValue = np.vectorize(StateToValMapping.get)(StateText)

    #check for error flags (the last two should never actually occur in this emulator, but are none the less checked)
    ErrMissedPacket = (BadWordCount>= BadWordThreshold).astype(int)
    ErrBadBunch = (dfInput.Bunch.values>=3564).astype(int)
    ErrBadState = (StateValue==None)

    ErrFlags = (ErrBadBunch*1 + ErrBadState*2 + ErrMissedPacket*4)

    df_ROC_DAQ_Control = pd.DataFrame({'GoodHeaderWord' : dfInput.GoodHeaderWord.values,
                                       'GoodSyncWord' : dfInput.GoodSyncWord.values,
                                       'Event' : dfInput.Event.values,
                                       'Bunch' : dfInput.Bunch.values,
                                       'Orbit' : dfInput.Orbit.values,
                                       'StateText' : StateText,
                                       'State' : StateValue,
                                       'TopEvent' : TopEvent,
                                       'TopBunch' : TopBunch,
                                       'TopOrbit' : TopOrbit,
                                       'TopNZS' : TopNZS,
                                       'L1AFifoEmpty' : L1AFifoEmpty,
                                       'L1AFifoFull' : L1AFifoFull,
                                       'Header_Predictor' : L1A_Header_Prediction,
                                       'PacketComplete' : PacketComplete,
                                       'EmptyHeader' : EmptyHeader,
                                       'EmptyHeaderFifoTop' : EmptyHeaderFifo[:,0].tolist(),
                                       'PP_State' : PP_State,
                                       'PP_ReadState' : PP_ReadState,
                                       'Flag_Home' : (StateText=='HOME').astype(int),
                                       'Flag_Header' : ((StateText=='STANDARDHEADER')|(StateText=='UNEXPECTEDHEADER')).astype(int),
                                       'Flag_Unexpected' : (StateText=='UNEXPECTEDHEADER').astype(int),
                                       'Flag_Packet_Done' : (StateText=='CRC').astype(int),
                                       'Flag_EmptyHeader' : (StateText=='EMPTYHEADER').astype(int),
                                       'Flag_Alignment_Done' : (StateText=='ALIGNSTEP2').astype(int),
                                       'Flag_CSynch' : (StateText=='CSYNC').astype(int),
                                       'Error_Flags' : ErrFlags
                                      },
                                      index=dfInput.index
                                     )

    df_ROC_DAQ_Control['EmptyHeaderFIFOSize'] = 8-(EmptyHeaderFifo==-1).all(axis=2).sum(axis=1)
    
    return df_ROC_DAQ_Control, EmptyHeaderFifo
