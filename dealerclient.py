#encoding=utf-8

from twisted.internet import reactor, threads
import pylogger as logger
from dealerfactory import  DealerFactory
# from dev_mgr_factory import  DevMgrFactory
import cardmsg
import struct
from cardinfo import CardInfo
import config
import random

from datamanager import DataMgrInstance
from scanresultsave import ScanRMgrInstance

class DealerClient(object):
    '''
    This file likely handles client-specific logic
    處理荷官端特定的商業邏輯，如handleCMD，某些傳過來的packet代表的意思
    '''

    def __init__(self, dealerIp, dealerPort, loginId):
        self.dealerIp = dealerIp
        self.dealerPort = dealerPort
        self.loginId = loginId
        self.dealerConnected = False
        self.auth = False
        self.gamecode = ''
        reactor.callLater(3, self.connectDealer)
        DataMgrInstance().register_senddata(self.sendPredictResult)

    # =============================================================================================
    # 使用 DataMgrInstance  傳送預測結果給荷官端時 使用
    def sendPredictResult(self, resultlist):
        count = len(resultlist)
        if 0 == count:
            logger.info('sendPredictResult, gmcode=%s, count=0' % (self.gamecode))
            return
        
        # Since resultlist now contains dictionaries of card groups
        for result_dict in resultlist:
            # Log the groups we received
            logger.info(f'sendPredictResult, gmcode={self.gamecode}, groups={result_dict}')
            
            # Count total cards across all groups
            total_cards = sum(len(cards) for cards in result_dict.values())
            
            # Pack the header with total card count
            body = struct.pack('!14sh', self.gamecode, total_cards)
            
            # For each group in sorted order (group_0, group_1, etc)
            for group_key in sorted(result_dict.keys()):
                cards = result_dict[group_key]
                group_idx = int(group_key.split('_')[1])  # Extract index from "group_X"
                
                # For each card tuple (value, score) in this group
                for card_val, score in cards:
                    # Pack each card with its group index, card value, and its actual score
                    body += struct.pack('!2hd', group_idx, card_val, score)

            totalSize = cardmsg.CMD_HEAD_LEN + len(body)
            head = struct.pack('!3i', cardmsg.CMD_PREDICT_RESULT, totalSize, 0)
            data = head + body
            
            logger.info('sendPredictResult, gmcode=%s, total_cards=%d, len=%d' % 
                       (self.gamecode, total_cards, len(data)))

            if self.factory:
                self.factory.sendData(data)
                
            # Save the final results - wrap result_dict in a list since saveFinaDeclareResult expects a list
            ScanRMgrInstance().saveFinaDeclareResult(self.gamecode, [result_dict])

    # =============================================================================================

    # twisted connection

    def connectDealer(self):
        logger.info('connect dealer %s:%s ...' %(self.dealerIp,  self.dealerPort))
        self.factory = DealerFactory(self, self.loginId)
        reactor.connectTCP(self.dealerIp, self.dealerPort, self.factory)

    def connectionDealerLost(self):
        # 重新连接荷官端
        reactor.callLater(config.TRY_CONNECT_DEALER_SECOND, self.connectDealer)
        self.dealerConnected = False

    def connectionDealerFailed(self):
        # 重新连接荷官端
        reactor.callLater(config.TRY_CONNECT_DEALER_SECOND, self.connectDealer)
        self.dealerConnected = False

    def connectionDealerMade(self):
        self.dealerConnected = True
        logger.info('connectionDealerMade...')

    # =============================================================================================
    # 處理接收從荷官端發射訊號
    def handleCmd(self, cmd, seq, body):
        logger.info('cmd=%s seq=%s body=%s(%d)' % (hex(cmd), seq, body, len(body)))
        if cardmsg.CMD_LOGIN_R == cmd:
            code, gmtype, vid = struct.unpack(cardmsg.FMT_BODY_PK_LOGIN_R, body)
            self.onLoginRet(code, gmtype, vid)
        elif cardmsg.CMD_START_PREDICT == cmd:
            gmcode, gmstate = struct.unpack(cardmsg.FMT_BODY_PK_START_PREDICT, body)
            #gmcode = struct.unpack(cardmsg.FMT_BODY_PK_START_PREDICT, body)
            #gmstate = 1
            self.onStartPredict(gmcode, gmstate)
        elif cardmsg.CMD_STOP_PREDICT == cmd:
            gmcode, gmstate = struct.unpack(cardmsg.FMT_BODY_PK_STOP_PREDICT, body)
            #gmcode = struct.unpack(cardmsg.FMT_BODY_PK_STOP_PREDICT, body)
            #gmstate = 0
            self.onStopPredict(gmcode, gmstate)
        elif cardmsg.CMD_SCAN_RESULT == cmd:
            mcode, index, cardVal = struct.unpack(cardmsg.FMT_BODY_SCAN_RESULT,body)
            logger.info('CMD_SCAN_RESULT, gmcode=%s index=%d cardVal=%d' % (str(mcode), index, cardVal))
            self.onSaveScanResult(mcode, index, cardVal)
        elif cardmsg.CMD_DISPATCH_INDEX == cmd:
            mcode, index = struct.unpack(cardmsg.FMT_BODY_DISPATCH_INDEX,body)
            logger.info('CMD_DISPATCH_INDEX, gmcode=%s index=%d' % (str(mcode), index))
            self.onDispatchCard(mcode, index)
        elif cardmsg.CMD_SAVE_RESULT == cmd:
            mcode = struct.unpack(cardmsg.FMT_BODY_SAVE_RESULT,body)
            logger.info('CMD_SAVE_RESULT, gmcode=%s' % (str(mcode)))
            self.onSaveFinalResult(mcode)
        elif cardmsg.CMD_CANCEL_RESULT == cmd:
            mcode = struct.unpack(cardmsg.FMT_BODY_CANCEL_RESULT,body)
            logger.info('CMD_DEL_RESULT, gmcode=%s' % (str(mcode)))
            self.onCanselResult(mcode)
        elif cardmsg.CMD_PREDICT_REF == cmd:
            mcode = struct.unpack(cardmsg.FMT_BODY_CANCEL_RESULT,body)
            logger.info('CMD_PREDICT_REF, gmcode=%s' % (str(mcode)))
            self.onPredictReference(mcode)
        else:
            logger.error('invalid cmd %s' % (hex(cmd)))
    # =============================================================================================
    # helper function for handleCmd
    def onLoginRet(self, code, gmtype, vid):
        if 0 == code:
            logger.info('login success, code=%d, gmtype=%s, vid=%s' % (code, gmtype, vid))
            self.auth = True
        else:
            logger.error('login failed, code=%d, gmtype=%s, vid=%s' % (code, gmtype, vid))
            self.auth = False

    def onStartPredict(self, gmcode, gmstate):
        self.gamecode = gmcode
        logger.info('onStartPredict, gmcode=%s, gmstate=%d' % (str(gmcode),gmstate))
        DataMgrInstance().startPredict(self.gamecode, gmstate)

    def onDispatchCard(self, gmcode, index):
        logger.info('onDispatchCard, gmcode=%s index=%d' % (gmcode, index))
        DataMgrInstance().dispatchCard(gmcode, index)

    def onStopPredict(self, gmcode, gmstate):
        logger.info('onStopPredict, gmcode=%s, gmstate=%d' % (str(gmcode), gmstate))
        DataMgrInstance().stopPredict(gmcode, gmstate)

    def onSaveScanResult(self, gmcode, index, cardVal):
        logger.info('onSaveScanResult, gmcode=%s index=%d, cardVal=%d' % (gmcode, index,cardVal))
        ScanRMgrInstance().saveScanResult(gmcode, index, cardVal)

    def onSaveFinalResult(self, gmcode):
        logger.info('onSaveFinalResult, gmcode=%s' % (gmcode))
        ScanRMgrInstance().SaveFinalResult(gmcode)

    def onCanselResult(self, gmcode): # 20241114 這邊似乎沒用到
        logger.info('onCanselResult, gmcode=%s' % (gmcode))
        DataMgrInstance().ReScan(gmcode)
        ScanRMgrInstance().clearCardMap(gmcode)

    def onPredictReference(self, gmcode): # 20241114 這邊似乎沒用到
        logger.info('onPredictReference, gmcode=%s' % (gmcode))

    def _toString(self, data):
        return ''.join([c for c in data if c != '\000'])

    def _mapStripNull(self, s):
        return map(lambda x: self._toString(x) if type(x) is str else x, s)




