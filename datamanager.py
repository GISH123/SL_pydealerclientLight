# encoding=utf-8

import threading
import pylogger as logger

from cardlist import Cardlist_box
from config import cfg
from cardinfo import SUITES_CLUB, SUITES_DIAMOND, SUITES_HAEART, SUITES_SPADE
from scanresultsave import ScanRMgrInstance

_SUIT_NAME = {
    SUITES_CLUB: 'club',
    SUITES_DIAMOND: 'diamond',
    SUITES_HAEART: 'heart',
    SUITES_SPADE: 'spade',
}
_RANKS = ('A','2','3','4','5','6','7','8','9','10','J','Q','K')


def _fmt_cardid(cid: int) -> str:
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
        rank = _RANKS[val - 1] if 1 <= val <= 13 else str(val)
        return f'{_SUIT_NAME[suit]}_{rank}'
    except Exception:
        return str(cid)


def _normalize_gmcode_bytes(gmcode):
    if isinstance(gmcode, (tuple, list)):
        gmcode = gmcode[0] if gmcode else b''
    if isinstance(gmcode, (bytes, bytearray)):
        return bytes(gmcode).split(b'\x00', 1)[0]
    return str(gmcode).split('\x00', 1)[0].encode('utf-8', errors='ignore')


class DataManager(object):
    def __init__(self):
        self.gmcode = b''
        self.gmtype = ''
        self.predictFlag = False
        self.lock = threading.Lock()
        self.mapcard = {}
        self.isDirty = False
        self.detecttimes = cfg.detecttimes
        self.curcardlist = []
        self.imageSaver = None
        self.senddata = None
        self.gmstate = 0

    def setgametype(self, gmetype):
        self.gmtype = (gmetype or '').upper()
        logger.info(f'DataManager setgametype={self.gmtype}')

    def getgametype(self):
        with self.lock:
            return self.gmtype

    def is_ball3(self):
        return self.getgametype() == 'BALL3'

    def is_bac(self):
        return self.getgametype() == 'BAC'

    def getPredictFlag(self):
        with self.lock:
            return self.predictFlag

    def getGamecode(self):
        with self.lock:
            return self.gmcode

    def register_senddata(self, senddata):
        self.senddata = senddata

    def register_ImageSaver(self, imageSaver):
        self.imageSaver = imageSaver

    def notify_ImageSaver(self):
        if self.imageSaver:
            self.imageSaver.setSnapshotFlag()

    def addResultlist(self, gmcode, resultlist):
        if not resultlist:
            logger.error(f'addResultlist invalid, len=0, gmcode={gmcode}')
            return
        gmcode = _normalize_gmcode_bytes(gmcode)
        with self.lock:
            if gmcode != _normalize_gmcode_bytes(self.gmcode) or not self.predictFlag:
                return
            first = resultlist[0]
            if isinstance(first, dict):
                self._addResultlist_BJ21(gmcode, resultlist)
            else:
                self._addResultlist_BAC(gmcode, resultlist)

    def _addResultlist_BJ21(self, gmcode, groups_list):
        self.isDirty = True
        is_ball3 = (self.gmtype == 'BALL3')
        for groups_dict in groups_list:
            logger.info(f'addResultlist(groups) sending groups for gmcode={gmcode}: {groups_dict}')
            if is_ball3:
                ScanRMgrInstance().update_ball3_latest_from_groups(gmcode, groups_dict)
            if self.senddata:
                self.senddata([groups_dict])
            else:
                logger.error('No senddata callback registered')

    def _addResultlist_BAC(self, gmcode, resultlist):
        self.isDirty = True
        for result in resultlist:
            self.addCardNolock(result.index, result)
            logger.debug(f'BAC addResultlist gmcode={gmcode} index={result.index} dealer_classid={result.dealer_classid}, card={_fmt_cardid(result.dealer_classid)}')
            cardlist_box = self.mapcard.get(result.index)
            if cardlist_box is not None and cardlist_box.CardNum >= self.detecttimes:
                logger.debug(f'BAC addResultlist map[{result.index}].CardNum={cardlist_box.CardNum} >= detecttimes={self.detecttimes}')
                self.check_resultEx(result.index, cardlist_box.CardNum)
            elif cardlist_box is not None:
                logger.debug(f'BAC addResultlist map[{result.index}].CardNum now={cardlist_box.CardNum} (< detecttimes={self.detecttimes})')

    def addCardNolock(self, index, card):
        cardlist_box = self.mapcard.get(index)
        if cardlist_box is None:
            cardlist_box = Cardlist_box()
            self.mapcard[index] = cardlist_box
        cardlist_box.addcardEx(card)

    def _reset_index_nolock(self, index):
        self.mapcard[index] = Cardlist_box()

    def clearCardNolock(self):
        self.mapcard.clear()

    def _activate_index_nolock(self, index, reset_history=True):
        if reset_history or index not in self.mapcard:
            self._reset_index_nolock(index)
        if index not in self.curcardlist:
            self.curcardlist.append(index)

    def _deactivate_index_nolock(self, index):
        if index in self.curcardlist:
            self.curcardlist.remove(index)

    def check_resultEx(self, index, count):
        resultlist = self.getsendResultNolock(index, count)
        if resultlist and self.senddata:
            logger.info(f'BAC check_resultEx gmcode={self.gmcode} resultsize={len(resultlist)}')
            self.senddata(resultlist)

    def getsendResultNolock(self, cardindex, count):
        resultlist = []
        cardlist_box = self.mapcard.get(cardindex)
        if cardlist_box is not None:
            if count >= self.detecttimes and cardlist_box.getIsdispatch() is False:
                result = cardlist_box.bestcardEx(minCardCount=1)
                if result is not None:
                    resultlist.append(result)
                    cardlist_box.setIsDispatch(True)
                    self._deactivate_index_nolock(cardindex)
                    logger.info(
                        f'BAC getsendResultNolock choose dealer_classid={result.dealer_classid}, '
                        f'card=({_fmt_cardid(result.dealer_classid)}) gmcode={self.gmcode} '
                        f'count={count}, deactivate_index={cardindex}, remaining_active={self.curcardlist}'
                    )
                    return resultlist
            else:
                logger.debug(f'BAC getsendResultNolock not ready: count={count}, isDispatch={cardlist_box.getIsdispatch() if cardlist_box else None}')
        return resultlist

    def getIsDispatch(self, gmcode, index):
        gmcode = _normalize_gmcode_bytes(gmcode)
        with self.lock:
            if gmcode == _normalize_gmcode_bytes(self.gmcode):
                return self.getIsDispatchNolock(index)
            return False

    def getIsDispatchNolock(self, index):
        if index in self.mapcard:
            return self.mapcard[index].getIsdispatch()
        return False

    def startPredict(self, gmcode, gmstate):
        gmcode = _normalize_gmcode_bytes(gmcode)
        with self.lock:
            oldFlag = self.predictFlag
            logger.info(f'datamanager start predict, gmcode={gmcode}, old_gmcode={self.gmcode}, cardcount={len(self.mapcard)}, gmstate={gmstate}')
            self.gmcode = gmcode
            self.gmstate = gmstate
            self.predictFlag = True
            if oldFlag != self.predictFlag and gmstate == 0:
                self.clearCardNolock()
                self.curcardlist.clear()

    def stopPredict(self, gmcode, gmstate):
        gmcode = _normalize_gmcode_bytes(gmcode)
        with self.lock:
            logger.info(f'datamanager stopPredict, gmcode={gmcode}, current_gmcode={self.gmcode}, cardcount={len(self.mapcard)}, gmstate={gmstate}')
            if gmstate == 0:
                self.clearCardNolock()
                self.curcardlist.clear()
                self.gmcode = b''
            self.predictFlag = False

    def ReScan(self, gmcode):
        gmcode = _normalize_gmcode_bytes(gmcode)
        gt = self.gmtype
        self.curcardlist.clear()
        if gt == 'DT':
            for i in (1, 2, 3):
                self._reset_index_nolock(i)
                self.curcardlist.append(i)
        elif gt == 'BAC':
            for i in range(1, 7):
                self._reset_index_nolock(i)
                self.curcardlist.append(i)
        elif gt == 'NN':
            self.curcardlist.extend(range(1, 21))
        elif gt == 'VNN':
            self.curcardlist.extend(range(1, 11))
        elif gt == 'VBR':
            self.curcardlist.extend(range(1, 7))
        elif gt == 'DZ':
            self.curcardlist.extend(range(1, 10))
        elif gt == 'TEB':
            self.curcardlist.extend(range(1, 9))
        else:
            logger.error(f'invalid gmtype {gt}')

    def isincurCardList(self, gmcode, cardindex):
        gmcode = _normalize_gmcode_bytes(gmcode)
        with self.lock:
            if gmcode == _normalize_gmcode_bytes(self.gmcode):
                return self.isincurCardListNolock(cardindex)
            return False

    def isincurCardListNolock(self, cardindex):
        return cardindex in self.curcardlist

    def dispatchCard(self, gmcode, index, scan_full_list=False):
        gmcode = _normalize_gmcode_bytes(gmcode)
        with self.lock:
            self.dispatchCardNoLock(gmcode, index, scan_full_list)

    def dispatchCardNoLock(self, gmcode, index, scan_full_list):
        current_gmcode = _normalize_gmcode_bytes(self.gmcode)
        logger.info(
            f'dispatchCardNoLock BEFORE, gmcode={current_gmcode}, gmtype={self.gmtype}, '
            f'curcardlist={self.curcardlist}, recv_gmcode={gmcode}, index={index}, '
            f'scan_full_list={scan_full_list}'
        )
        if gmcode != current_gmcode:
            logger.warning(f'dispatchCardNoLock ignored: gmcode mismatch recv={gmcode}, current={current_gmcode}')
            return

        targets = []
        if self.gmtype == 'DT':
            if scan_full_list and index == 1:
                targets = [1, 2, 3]
            elif index in (1, 2, 3):
                targets = [index]
        elif self.gmtype == 'BAC':
            if scan_full_list and index == 1:
                targets = [1, 2, 3, 4, 5, 6]
            elif 1 <= index <= 6:
                targets = [index]
        else:
            logger.warning(f'dispatchCardNoLock unsupported gmtype={self.gmtype}, index={index}')
            return

        if not targets:
            logger.warning(f'dispatchCardNoLock no targets resolved, gmtype={self.gmtype}, index={index}, scan_full_list={scan_full_list}')
            return

        added_targets = []
        kept_targets = []
        for i in targets:
            already_active = (i in self.curcardlist)
            already_dispatched = self.getIsDispatchNolock(i)
            if already_active and not already_dispatched:
                kept_targets.append(i)
                continue
            self._activate_index_nolock(i, reset_history=True)
            if already_active:
                logger.info(f'dispatchCardNoLock re-activate index={i} after previous result/redispatch')
            else:
                added_targets.append(i)

        logger.info(
            f'dispatchCardNoLock AFTER, gmcode={self.gmcode}, gmtype={self.gmtype}, '
            f'index={index}, targets={targets}, added_targets={added_targets}, '
            f'kept_targets={kept_targets}, curcardlist={self.curcardlist}'
        )


dataMgr = DataManager()


def DataMgrInstance():
    return dataMgr
