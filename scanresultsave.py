#encoding=utf-8

import threading
import time
import pylogger as logger
import csvtool as csvtooler
from twisted.internet.task import LoopingCall
from config import cfg
from datamanager import DataMgrInstance
from datetime import datetime
from cardmsg import ScanResult
class ScanResultManager(object):
	def __init__(self):
		'''
		初始化
		'''
		self.gmcode = ''
		self.gmlastcode = ''
		self.predictFlag = False
		self.lock = threading.Lock()
		#扫描牌结果  aleck
		self.scanmapcard = dict()
		#保存每一张牌的csv
		self.csvmap = {}
		#保存最后结果的csv
		self.csvResutmap = {}
		#self.thread.start()
		#self._stop_event = threading.Event()
		self.tickTimer = LoopingCall(self.onTick)
		self.tickTimer.start(0.2, False)
		self.lashCheckTimestamp = 0
		self.detecttimes = cfg.detecttimes
		self.curDate = datetime.now().strftime('%Y-%m-%d')
		self.gmCount = 0

	def onRefresh(self, timestamp):
		if timestamp - self.lashCheckTimestamp >= 1:
			self.lashCheckTimestamp = timestamp

	#def onSaveCsv(self, timestamp):
		#if timestamp - self.lashCheckTimestamp >= 1:
			#self.lashCheckTimestamp = timestamp

	def onTick(self):
		self.onRefresh(int(time.time() * 1000))
		#self.onSaveCsv(int(time.time() * 5000))

	#======================================================================================================================================#

	def saveScanResult(self, gmcode, index, cardVal):
		self.saveScanResultNolock(gmcode, index, cardVal)

	def saveScanResultNolock(self, gmcode, index, cardVal):
		self.gmcode = gmcode
		logger.info('datamanager saveScanResult gmcode=%s, index=%d, cardVal=%d' % (gmcode, index, cardVal))
		self.scanmapcard[index] = cardVal


	#======================================================================================================================================#

	def SaveFinalResult(self, gmcode):
		curDate = datetime.now().strftime('%Y-%m-%d')
		if curDate == self.curDate:
			self.gmCount += 1
		else:
			self.curDate = curDate
			self.gmCount = 0
		logger.info('gmSaveFinalResult, gmcode=%s, len(scanmap)=%d, gmCount=%d' % (gmcode, len(self.scanmapcard), self.gmCount))
		# self.savetocsv()
		self.savetocsvfinaresult()
		self.clearCardMap(gmcode)
		DataMgrInstance().notify_ImageSaver()
	
	# 20241115 用不到，只用savetocsvfinaresult
	# def savetocsv(self):
	# 	self.lock.acquire()
	# 	#这里存csv数据,因为此时更保险，扫描值和预测值都存在
	# 	messagelist = []

	# 	# 遍历字典的项
	# 	if self.gmcode in self.csvmap.keys():
	# 		csvlistm = self.csvmap[self.gmcode]
	# 		logger.info(f"scanresultsave.py savetocsv(), csvlistm={csvlistm}")
	# 		# 如果字典里元素列表个数>1
	# 		for csvlist in csvlistm:
	# 			for (index,cardVal) in self.scanmapcard.items():
	# 				if csvlist[2] == index:
	# 					csvlist.insert(3, cardVal)
	# 			messagelist.append(csvlist)

	# 	if len(messagelist) > 0:
	# 		csvtooler.tocsv(messagelist, False)
	# 		logger.info(f"scanresultsave.py savetocsv(), csvtooler.tocsv, messagelist={messagelist}")
	# 	self.lock.release()

	def savetocsvfinaresult(self):
		self.lock.acquire()
		#这里存csv数据,因为此时更保险，扫描值和预测值都存在
		messagelist = []
		# 遍历字典的项
		if self.gmcode in self.csvResutmap.keys():
			csvlistm = self.csvResutmap[self.gmcode]
			logger.info('scanresultsave.py savetocsvfinaresult(), gmcode=%s,len(csvlistm)=%d'% (self.gmcode, len(csvlistm)))
			logger.info(f"csvlistm:  {csvlistm}")
			for csvlist in csvlistm:
				# for (index,cardVal) in self.scanmapcard.items():
				# 	#logger.info('savetocsvfinaresult_csvlistm gmcode=%s ,prdict_index = %d, predic_val=%d' %(self.gmcode,csvlist[1],csvlist[2]))
				# 	if csvlist[1] == index:
				# 		csvlist.insert(2, cardVal)
						# logger.info('savetocsvfinaresult gmcode=%s, scan_index = %d, prdict_index = %d, scan_cardVal = %d, predic_val=%d' % (self.gmcode, index, csvlist[1], csvlist[2], csvlist[3]))
				messagelist.append(csvlist)
		if len(messagelist) > 0:
			logger.info("scanresultsave.py savetocsvfinaresult(), csvtooler.tocsv to save csvfile.")
			csvtooler.tocsv(messagelist, True)
		self.lock.release()

	#======================================================================================================================================#

	def clearCardMap(self, gmcode):
		logger.info('clearCarMap, gmcode=%s' % (gmcode))
		self.lock.acquire()
		if len(self.csvmap) > 0:
			self.csvmap.clear()
		if len(self.csvResutmap) > 0:
			self.csvResutmap.clear()
		if len(self.scanmapcard) > 0:
			self.scanmapcard.clear()
		self.lock.release()

	#======================================================================================================================================#

	def saveFinaDeclareResult(self, gmcode, resultlist):
		self.lock.acquire()
		self.saveFinaDeclareResultNoLock(gmcode, resultlist)
		self.lock.release()
	def saveFinaDeclareResultNoLock(self, gmcode, resultlist):
		# 這邊將當前卡牌框格預測的最後結果儲存到messagelist裡面，主要是為了最後寫入到csv用
		strgmcode = self._toString(str(gmcode, encoding='utf-8'))
		messagelist = []
		
		# resultlist contains dictionaries of card groups
		for result_dict in resultlist:
			# For each group in sorted order (group_0, group_1, etc)
			for group_key in sorted(result_dict.keys()):
				group_idx = int(group_key.split('_')[1])  # Extract index from "group_X"
				cards = result_dict[group_key]
				
				# For each card tuple (value, score) in this group
				for card_val, score in cards:
					message = []
					message.append(strgmcode)           # gmcode
					message.append(group_idx)           # index = group_index
					message.append(card_val)            # dealer_classid = card number
					message.append(card_val)            # predict_classid = card number
					message.append(score)               # score from detection
					message.append(card_val)            # card_point = card number
					message.append(0)                   # endid placeholder
					messagelist.append(message)
					
					logger.info(f'saveFinaDeclareResultNoLock building message: gmcode={strgmcode}, '
							  f'group_idx={group_idx}, card_val={card_val}, score={score}')

		# Store in csvResutmap
		if len(messagelist) > 0:
			if gmcode in self.csvResutmap.keys():
				self.csvResutmap[gmcode].extend(messagelist)
				logger.info(f'saveFinaDeclareResultNoLock, gmcode in csvResutMaps, extended with {len(messagelist)} messages')
			else:
				self.csvResutmap[gmcode] = messagelist
				logger.info(f'saveFinaDeclareResultNoLock, gmcode NOT in csvResutMaps, added {len(messagelist)} messages')

	#======================================================================================================================================#

	def _toString(self, data):
		return ''.join([c for c in data if c != '\000'])

dataMgr = ScanResultManager()

def ScanRMgrInstance():
	return dataMgr



