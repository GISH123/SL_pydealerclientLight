# encoding=utf-8

import threading
from cardlist import Cardlist_box
import time
import enum
import pylogger as logger
from twisted.internet.task import LoopingCall
from config import cfg

class DataManager(object):
	def __init__(self):
		'''
		初始化
		'''
		self.gmcode = ''
		self.gmtype = ''
		self.predictFlag = False
		self.lock = threading.Lock()
		self.mapcard = dict()
		'''
		mapcard = {1: Cardlist_box1, 2: Cardlist_box2, 3:Cardlist_box3, ...., 6: Cardlist_box6}, 1~6表index即六張牌框格
		'''
		self.isDirty = False
		self.lashCheckTimestamp = 0
		self.detecttimes = cfg.detecttimes
		self.curcardlist = [] # 紀錄目前第幾個index要預測
		self.imageSaver = None

	def setgametype(self, gmetype):
		self.gmtype = gmetype

	def getPredictFlag(self):
		'''
		获取预测标记
		:return:
		'''
		self.lock.acquire()
		predict = self.predictFlag
		self.lock.release()
		return predict

	def getGamecode(self):
		'''
		获取当前局号
		:return:
		'''
		self.lock.acquire()
		gmcode = self.gmcode
		self.lock.release()
		return gmcode

	def register_senddata(self, senddata):
		'''
		Register callback for sending prediction results to dealer client
		'''
		logger.info('Registering senddata callback')
		self.senddata = senddata

	def register_ImageSaver(self, imageSaver):
		self.imageSaver = imageSaver

	def notify_ImageSaver(self):
		if self.imageSaver:
			self.imageSaver.setSnapshotFlag()

	def addResultlist(self, gmcode, resultlist):
		'''
		Add new card detection results and trigger sending if conditions are met
		'''
		if len(resultlist) > 0:
			self.lock.acquire()
			try:
				if gmcode == self.gmcode and self.predictFlag:
					self.isDirty = True
					for result in resultlist:
						# Now result is a dictionary of card groups
						logger.info(f'Adding result for gmcode={gmcode}, groups={result}')
						# Send results immediately through registered callback
						if hasattr(self, 'senddata'):
							self.senddata([result])
						else:
							logger.error('No senddata callback registered')
			finally:
				self.lock.release()
		else:
			logger.error(f'addResultlist invalid, len=0, gmcode={gmcode}')

	def check_resultEx(self):
		'''
		Check if we have enough predictions to send.
		Sends the current state of all detected cards in their groups.
		'''
		if not self.predictFlag:
			return

		# Get current state of all groups
		resultlist = []
		for group_idx, cardlist_box in self.mapcard.items():
			if cardlist_box.getIsdispatch():
				continue
			
			# Get the current highest confidence predictions for this group
			current_group_cards = []
			for dealer_classid, card_list in cardlist_box.indexcardmap.items():
				if card_list:  # If we have any predictions for this card
					best_card = card_list[0]  # Take highest confidence prediction
					current_group_cards.append(best_card)
			
			# Only add group results if we have cards
			if current_group_cards:
				resultlist.extend(current_group_cards)

		# Send the current state if we have any valid predictions
		if len(resultlist) > 0:
			self.senddata(resultlist)
			# Mark these cards as dispatched
			for result in resultlist:
				if result.index in self.mapcard:
					self.mapcard[result.index].setIsDispatch(True)

	def startPredict(self, gmcode, gmstate):
		'''
		开始预测
		:param gmcode:
		:return:
		'''
		logger.info('datamanager start predict, gmcode=%s, cardcount=%d, gmstate=%d' % (
		self.gmcode, len(self.mapcard), gmstate))
		self.lock.acquire()
		self.gmcode = gmcode
		oldFlag = self.predictFlag
		self.predictFlag = True
		self.gmstate = gmstate
		if oldFlag != self.predictFlag:
			if gmstate == 0:
				self.clearCardNolock()
				self.curcardlist.clear()
		self.lock.release()

	def stopPredict(self, gmcode, gmstate):
		'''
		停止预测
		:param gmcode:
		:return:
		'''
		logger.info(
			'datamanager stopPredict, gmcode=%s, cardcount=%d, gmstate=%d' % (self.gmcode, len(self.mapcard), gmstate))
		self.lock.acquire()

		if gmstate == 0:
			self.clearCardNolock()
			self.curcardlist.clear()
			self.gmcode = ''
		self.predictFlag = False
		self.lock.release()

	def clearCardNolock(self):
		self.mapcard.clear()

	def getIsDispatch(self, gmcode, index):
		'''
		Check if a card has been dispatched for a given game code and position index
		'''
		isdispatch = False
		self.lock.acquire()
		if self.gmcode == gmcode:
			isdispatch = self.getIsDispatchNolock(index)
		self.lock.release()
		return isdispatch

	def getIsDispatchNolock(self, index):
		'''
		Helper method to check dispatch status without lock
		'''
		if index in self.mapcard:
			isDispatch = self.mapcard[index].getIsdispatch()
			return isDispatch
		return False

dataMgr = DataManager()

def DataMgrInstance():
	return dataMgr


