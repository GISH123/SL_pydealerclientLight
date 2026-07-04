#encoding=utf-8

import struct

from twisted.internet import reactor
import pylogger as logger
from dealerfactory import DealerFactory
import cardmsg
import config
from cardinfo import CardInfo, SUITES_CLUB, SUITES_DIAMOND, SUITES_HAEART, SUITES_SPADE
from datamanager import DataMgrInstance
from scanresultsave import ScanRMgrInstance
import videomanager


def _pack_gmcode_14s(gmcode):
    if isinstance(gmcode, (tuple, list)):
        gmcode = gmcode[0] if gmcode else b''
    if isinstance(gmcode, (bytes, bytearray)):
        raw = bytes(gmcode)
    else:
        raw = str(gmcode).encode('utf-8', errors='ignore')
    return raw[:14].ljust(14, b'\x00')


class DealerClient(object):
    _SUIT_NAME = {
        SUITES_CLUB: 'club',
        SUITES_DIAMOND: 'diamond',
        SUITES_HAEART: 'heart',
        SUITES_SPADE: 'spade',
    }
    _RANKS = ('A','2','3','4','5','6','7','8','9','10','J','Q','K')

    def __init__(self, dealerIp, dealerPort, loginId):
        self.dealerIp = dealerIp
        self.dealerPort = dealerPort
        self.loginId = loginId
        self.dealerConnected = False
        self.auth = False
        self.gamecode = b''
        self.factory = None
        reactor.callLater(3, self.connectDealer)
        DataMgrInstance().register_senddata(self.sendPredictResult)

    def _fmt_cardid(self, cid: int) -> str:
        try:
            n = int(cid)
            if 1 <= n <= 13:
                suit, val = SUITES_CLUB, n
            elif 17 <= n <= 29:
                suit, val = SUITES_DIAMOND, n - 16
            elif 33 <= n <= 45:
                suit, val = SUITES_SPADE, n - 32
            elif 49 <= n <= 61:
                suit, val = SUITES_HAEART, n - 48
            else:
                return f'id{cid}'
            rank = self._RANKS[val - 1] if 1 <= val <= 13 else str(val)
            return f'{self._SUIT_NAME[suit]}_{rank}'
        except Exception:
            return str(cid)

    def sendPredictResult(self, resultlist):
        count = len(resultlist)
        if count == 0:
            logger.info('sendPredictResult, gmcode=%s, count=0' % (self.gamecode))
            return

        if isinstance(resultlist[0], CardInfo):
            gmcode14 = _pack_gmcode_14s(self.gamecode)
            body = struct.pack('!14sh', gmcode14, count)
            for res in resultlist:
                body += struct.pack('!2hd', int(res.index), int(res.dealer_classid), float(res.score))
            totalSize = cardmsg.CMD_HEAD_LEN + len(body)
            head = struct.pack('!3i', cardmsg.CMD_PREDICT_RESULT, totalSize, 0)
            data = head + body
            pretty = ', '.join([
                f'idx={res.index}:{self._fmt_cardid(res.dealer_classid)}#{res.dealer_classid}@{res.score:.4f}'
                for res in resultlist
            ])
            logger.info('sendPredictResult[BAC], gmcode=%s, count=%d, len=%d, cards=[%s]' %
                        (self.gamecode, count, len(data), pretty))
            if self.factory:
                self.factory.sendData(data)
            try:
                ScanRMgrInstance().saveFinaDeclareResult(self.gamecode, resultlist)
            except Exception as e:
                logger.error(f'saveFinaDeclareResult failed, gmcode={self.gamecode}, err={e}')
            return

        for result_dict in resultlist:
            logger.info(f'sendPredictResult, gmcode={self.gamecode}, groups={result_dict}')
            total_cards = sum(len(cards) for cards in result_dict.values())
            gmcode14 = _pack_gmcode_14s(self.gamecode)
            body = struct.pack('!14sh', gmcode14, total_cards)
            for group_key in sorted(result_dict.keys()):
                cards = result_dict[group_key]
                try:
                    group_idx = int(str(group_key).split('_')[-1])
                except Exception:
                    group_idx = 0
                for card_val, score in cards:
                    try:
                        if isinstance(card_val, str) and not card_val.strip().isdigit():
                            card_int = {'A': 1, 'J': 11, 'Q': 12, 'K': 13}.get(card_val.strip().upper(), 0)
                        else:
                            card_int = int(card_val)
                    except Exception:
                        card_int = 0
                    try:
                        score_f = float(score)
                    except Exception:
                        score_f = 0.0
                    body += struct.pack('!2hd', int(group_idx), int(card_int), float(score_f))
            totalSize = cardmsg.CMD_HEAD_LEN + len(body)
            head = struct.pack('!3i', cardmsg.CMD_PREDICT_RESULT, totalSize, 0)
            data = head + body
            logger.info('sendPredictResult, gmcode=%s, total_cards=%d, len=%d' % (self.gamecode, total_cards, len(data)))
            if self.factory:
                self.factory.sendData(data)

    def connectDealer(self):
        logger.info('connect dealer %s:%s ...' % (self.dealerIp, self.dealerPort))
        self.factory = DealerFactory(self, self.loginId)
        reactor.connectTCP(self.dealerIp, self.dealerPort, self.factory)

    def connectionDealerLost(self):
        reactor.callLater(config.TRY_CONNECT_DEALER_SECOND, self.connectDealer)
        self.dealerConnected = False

    def connectionDealerFailed(self):
        reactor.callLater(config.TRY_CONNECT_DEALER_SECOND, self.connectDealer)
        self.dealerConnected = False

    def connectionDealerMade(self):
        self.dealerConnected = True
        logger.info('connectionDealerMade...')

    def handleCmd(self, cmd, seq, body):
        logger.info('cmd=%s seq=%s body=%s(%d)' % (hex(cmd), seq, body, len(body)))
        if cardmsg.CMD_LOGIN_R == cmd:
            code, gmtype, vid = struct.unpack(cardmsg.FMT_BODY_PK_LOGIN_R, body)
            self.onLoginRet(code, gmtype, vid)
        elif cardmsg.CMD_START_PREDICT == cmd:
            gmcode, gmstate = struct.unpack(cardmsg.FMT_BODY_PK_START_PREDICT, body)
            self.onStartPredict(gmcode, gmstate)
        elif cardmsg.CMD_STOP_PREDICT == cmd:
            gmcode, gmstate = struct.unpack(cardmsg.FMT_BODY_PK_STOP_PREDICT, body)
            self.onStopPredict(gmcode, gmstate)
        elif cardmsg.CMD_SCAN_RESULT == cmd:
            mcode, index, cardVal = struct.unpack(cardmsg.FMT_BODY_SCAN_RESULT, body)
            logger.info('CMD_SCAN_RESULT, gmcode=%s index=%d cardVal=%d' % (str(mcode), index, cardVal))
            self.onSaveScanResult(mcode, index, cardVal)
        elif cardmsg.CMD_DISPATCH_INDEX == cmd:
            mcode, index = struct.unpack(cardmsg.FMT_BODY_DISPATCH_INDEX, body)
            logger.info('CMD_DISPATCH_INDEX, gmcode=%s index=%d' % (str(mcode), index))
            self.onDispatchCard(mcode, index)
        elif cardmsg.CMD_SAVE_RESULT == cmd:
            mcode = struct.unpack(cardmsg.FMT_BODY_SAVE_RESULT, body)
            logger.info('CMD_SAVE_RESULT, gmcode=%s' % (str(mcode)))
            self.onSaveFinalResult(mcode)
        elif cardmsg.CMD_CANCEL_RESULT == cmd:
            mcode = struct.unpack(cardmsg.FMT_BODY_CANCEL_RESULT, body)
            logger.info('CMD_DEL_RESULT, gmcode=%s' % (str(mcode)))
            self.onCanselResult(mcode)
        elif cardmsg.CMD_PREDICT_REF == cmd:
            mcode = struct.unpack(cardmsg.FMT_BODY_CANCEL_RESULT, body)
            logger.info('CMD_PREDICT_REF, gmcode=%s' % (str(mcode)))
            self.onPredictReference(mcode)
        else:
            logger.error('invalid cmd %s' % (hex(cmd)))

    def onLoginRet(self, code, gmtype, vid):
        if 0 == code:
            logger.info('login success, code=%d, gmtype=%s, vid=%s' % (code, gmtype, vid))
            self.auth = True
        else:
            logger.error('login failed, code=%d, gmtype=%s, vid=%s' % (code, gmtype, vid))
            self.auth = False

    def onStartPredict(self, gmcode, gmstate):
        if isinstance(gmcode, str):
            gmcode = gmcode.encode('utf-8')
        self.gamecode = gmcode
        logger.info('onStartPredict, gmcode=%s, gmstate=%d' % (str(gmcode), gmstate))
        DataMgrInstance().startPredict(self.gamecode, gmstate)

    def onDispatchCard(self, gmcode, index):
        if isinstance(gmcode, str):
            gmcode = gmcode.encode('utf-8')
        logger.info('onDispatchCard, gmcode=%s index=%d' % (gmcode, index))
        DataMgrInstance().dispatchCard(gmcode, index)

    def onStopPredict(self, gmcode, gmstate):
        if isinstance(gmcode, str):
            gmcode = gmcode.encode('utf-8')
        logger.info('onStopPredict, gmcode=%s, gmstate=%d' % (str(gmcode), gmstate))
        DataMgrInstance().stopPredict(gmcode, gmstate)
        try:
            gm_str = gmcode.decode('utf-8', errors='ignore') if isinstance(gmcode, (bytes, bytearray)) else str(gmcode)
            if DataMgrInstance().is_ball3() and int(gmstate) == 0:
                try:
                    videomanager.save_ball3_stop_image(gm_str)
                except Exception as e:
                    logger.error(f'BALL3 save_ball3_stop_image failed: {e}')
                ScanRMgrInstance().save_ball3_final_csv(gmcode)
            else:
                if DataMgrInstance().is_bac():
                    try:
                        if ScanRMgrInstance().HasPendingFinalResult(gmcode):
                            logger.info('onStopPredict[BAC] fallback SaveFinalResult on STOP')
                            ScanRMgrInstance().SaveFinalResult(gmcode)
                        else:
                            logger.info('onStopPredict[BAC] no pending final result to save')
                    except Exception as e:
                        logger.error(f'onStopPredict[BAC] fallback save failed: {e}')
                else:
                    logger.info('onStopPredict[BJ21], no final CSV flush on STOP')
        except Exception as e:
            logger.error(f'onStopPredict post-stop handling failed: {e}')

    def onSaveScanResult(self, gmcode, index, cardVal):
        logger.info('onSaveScanResult, gmcode=%s index=%d, cardVal=%d' % (gmcode, index, cardVal))
        ScanRMgrInstance().saveScanResult(gmcode, index, cardVal)

    def onSaveFinalResult(self, gmcode):
        logger.info('onSaveFinalResult, gmcode=%s' % (gmcode))
        try:
            ScanRMgrInstance().SaveFinalResult(gmcode)
        except Exception as e:
            logger.error(f'onSaveFinalResult failed, gmcode={gmcode}, err={e}')

    def onCanselResult(self, gmcode):
        logger.info('onCanselResult, gmcode=%s' % (gmcode))
        DataMgrInstance().ReScan(gmcode)
        ScanRMgrInstance().clearCardMap(gmcode)

    def onPredictReference(self, gmcode):
        logger.info('onPredictReference, gmcode=%s' % (gmcode))
