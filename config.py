#encoding=utf-8

import xml.dom.minidom as xmldom
import pylogger as logger
import os
import xml.etree.ElementTree as ET  # <-- needed for savePredictImage parsing

TRY_CONNECT_DEALER_SECOND = 10
TRY_CONNECT_DEVMGR_SECOND = 10

'''
# 瑙嗛娴?
videoname = '0'

# 妯″瀷璺緞
fastrcnn_model = './models/frozen_inference_graph.pb'
fastrcnn_config = './models/graph_faster_rcnn.pbtxt'
position_filename = './models/8-11v2.xml'
'''

class CardPositon(object):
    def __init__(self, index, name, xmin, ymin, xmax, ymax):
        self.index = int(index)
        self.name = name
        self.xmin = int(xmin)
        self.ymin = int(ymin)
        self.xmax = int(xmax)
        self.ymax = int(ymax)

    def width(self):
        return self.xmax - self.xmin

    def height(self):
        return self.ymax - self.ymin

class AppConfig(object):
    def __init__(self, config_filename, video_filename, score_thresholdname):
        self.config_filename = config_filename
        self.video_filename = video_filename
        self.score_thresholdname = score_thresholdname
        self.position_filename = ''
        self.DETECT_FRAME = 20 # 妫€娴嬪抚鐜?
        self.devmgr_host = "127.0.0.1"
        self.devmgr_port = 1833

    # 鍒濆鍖栭厤缃?
    def load_config(self):

        bRet = self.read_base_config(self.config_filename)
        if not bRet:
            logger.error('load_config %s failed' %(self.config_filename))
            return False

        bRet = self.read_video_list(self.video_filename)
        if not bRet:
            logger.error('load_video_list %s failed' % (self.video_filename))
            return False

        bRet = self.read_position(self.position_filename)
        if not bRet:
            logger.error('read_position %s failed' % (self.position_filename))
            return False

        # bRet = self.read_scoreshold(self.score_thresholdname)
        # if not bRet:
        #     logger.error('read_scoreshold %s failed' % (self.read_scoreshold))
        #     return False

        return True

    # 璇诲彇鍩烘湰閰嶇疆
    def read_base_config(self, filename):
        xml_file = xmldom.parse(filename)
        root = xml_file.documentElement

        node_common = root.getElementsByTagName('common')[0]
        self.vid = node_common.getAttribute('vid')
        self.freq = int(node_common.getAttribute('freq'))
        self.onelabel = int(node_common.getAttribute('onelabel'))
        self.detecttimes = int(node_common.getAttribute('detecttimes'))
        self.saveimagescore = float(node_common.getAttribute('saveimagescore'))

        # BAC/DT repeated same-index dispatch protection.
        # This does NOT change the mock dealer send cadence.
        # It only controls how often pydealerLight will fully reset the same target
        # when the dealer keeps re-dispatching the same index.
        self.redispatch_reset_cooldown_s = 1.0
        if node_common.hasAttribute('redispatch_reset_cooldown_s'):
            self.redispatch_reset_cooldown_s = float(node_common.getAttribute('redispatch_reset_cooldown_s'))
        elif node_common.hasAttribute('same_index_redispatch_reset_cooldown_s'):
            self.redispatch_reset_cooldown_s = float(node_common.getAttribute('same_index_redispatch_reset_cooldown_s'))

        # Live stream reconnect watchdog knobs (optional).
        self.live_stall_timeout_s = 10.0
        if node_common.hasAttribute('live_stall_timeout_s'):
            self.live_stall_timeout_s = float(node_common.getAttribute('live_stall_timeout_s'))

        self.live_reopen_cooldown_s = 3.0
        if node_common.hasAttribute('live_reopen_cooldown_s'):
            self.live_reopen_cooldown_s = float(node_common.getAttribute('live_reopen_cooldown_s'))

        # BAC ROI preprocess before posting to external model API.
        # Optional config.xml node:
        # <bacPreprocess resize_enable="1" resize_min_w="320" resize_min_h="320" resize_target_w="320" resize_target_h="320" />
        # Behavior: when enabled, if cropped ROI width/height is smaller than min_w/min_h,
        # keep-ratio resize the posted image. The output image is not padded and may be non-square.
        self.bac_preprocess_resize_enable = True
        self.bac_preprocess_resize_min_w = 320
        self.bac_preprocess_resize_min_h = 320
        self.bac_preprocess_resize_target_w = 320
        self.bac_preprocess_resize_target_h = 320
        try:
            nodes_bac_preprocess = root.getElementsByTagName('bacPreprocess')
            if nodes_bac_preprocess:
                node_bac = nodes_bac_preprocess[0]
                if node_bac.hasAttribute('resize_enable'):
                    self.bac_preprocess_resize_enable = str(node_bac.getAttribute('resize_enable')).strip() in ('1', 'true', 'True')
                elif node_bac.hasAttribute('resize_enabled'):
                    self.bac_preprocess_resize_enable = str(node_bac.getAttribute('resize_enabled')).strip() in ('1', 'true', 'True')

                if node_bac.hasAttribute('resize_min_w'):
                    self.bac_preprocess_resize_min_w = int(node_bac.getAttribute('resize_min_w'))
                if node_bac.hasAttribute('resize_min_h'):
                    self.bac_preprocess_resize_min_h = int(node_bac.getAttribute('resize_min_h'))
                if node_bac.hasAttribute('resize_target_w'):
                    self.bac_preprocess_resize_target_w = int(node_bac.getAttribute('resize_target_w'))
                if node_bac.hasAttribute('resize_target_h'):
                    self.bac_preprocess_resize_target_h = int(node_bac.getAttribute('resize_target_h'))
        except Exception as e:
            logger.error(f"read bacPreprocess config failed: {e}")
            raise

        node_dealer = root.getElementsByTagName('dealer')[0]
        self.dealer_id = node_dealer.getAttribute('id')
        self.dealer_host = node_dealer.getAttribute('host')
        self.dealer_port = int(node_dealer.getAttribute('port'))
        node_save = root.getElementsByTagName('save')[0]
        save_folder = node_save.getAttribute('folder')

        # Check if the drive in save_folder exists
        drive = os.path.splitdrive(save_folder)[0]
        if drive and not os.path.exists(drive):
            logger.warning(f"Drive {drive} is not available")
            logger.info("Using local temp folder instead")
            self.save_folder = "./temp_folder_for_big_pic"
        else:
            self.save_folder = save_folder
        
        self.save_auto_upload = node_save.getAttribute('autoUpload')

        # Optional: small per-round predict images (BALL3)
        self.savePredictImage_enable = False
        self.savePredictImage_folder = './predict_images'
        try:
            nodes_pred = root.getElementsByTagName('savePredictImage')
            if nodes_pred:
                node_pred = nodes_pred[0]
                self.savePredictImage_folder = node_pred.getAttribute('folder') or self.savePredictImage_folder
                en = node_pred.getAttribute('enable') or node_pred.getAttribute('enabled')
                self.savePredictImage_enable = str(en).strip() in ('1', 'true', 'True')
                if self.savePredictImage_enable:
                    os.makedirs(self.savePredictImage_folder, exist_ok=True)
        except Exception as e:
            logger.error(f"read savePredictImage config failed: {e}")

        
        logger.info('read_base_config success, vid=%s, freq=%d, onelabel=%d, detecttimes=%d,saveimagescore=%.4f, id=%s, host=%s, port=%d' %
                    (self.vid, self.freq, self.onelabel, self.detecttimes, self.saveimagescore, self.dealer_id, self.dealer_host, self.dealer_port))
        logger.info(
            "save_folder={},save_auto_upload={}, savePredictImage_enable={}, savePredictImage_folder={}, "
            "redispatch_reset_cooldown_s={}, live_stall_timeout_s={}, live_reopen_cooldown_s={}, "
            "bac_preprocess_resize_enable={}, bac_preprocess_resize_min_wh=({},{}), bac_preprocess_resize_target_wh=({},{})".format(
                self.save_folder,
                self.save_auto_upload,
                getattr(self, "savePredictImage_enable", False),
                getattr(self, "savePredictImage_folder", ""),
                getattr(self, "redispatch_reset_cooldown_s", 1.0),
                getattr(self, "live_stall_timeout_s", 10.0),
                getattr(self, "live_reopen_cooldown_s", 3.0),
                getattr(self, "bac_preprocess_resize_enable", True),
                getattr(self, "bac_preprocess_resize_min_w", 320),
                getattr(self, "bac_preprocess_resize_min_h", 320),
                getattr(self, "bac_preprocess_resize_target_w", 320),
                getattr(self, "bac_preprocess_resize_target_h", 320),
            )
        )

        # HTTP config
        self.http_port = 9000
        self.https_port = 9001
        node_http_list = root.getElementsByTagName('http')
        if len(node_http_list) > 0:
            node_http = node_http_list[0]

            if node_http.hasAttribute('port'):
                self.http_port = int(node_http.getAttribute('port'))

            if node_http.hasAttribute('https_port'):
                self.https_port = int(node_http.getAttribute('https_port'))
        else:
            logger.warning("No <http> config found, using default ports 9000/9001")

        return True

    # 璇诲彇瑙嗛鍒楄〃
    def read_video_list(self, filename):
        xml_file = xmldom.parse(filename)
        root = xml_file.documentElement
        node_video_list = root.getElementsByTagName('videolist')[0]
        node_videos = node_video_list.getElementsByTagName('video')
        for node_video in node_videos:
            vid = node_video.getAttribute('vid')
            if vid == self.vid:
                self.gametype = node_video.getAttribute('gametype')
                self.stream = node_video.getAttribute('stream')
                #鏈夊彲鑳戒細鐢ㄩ噰闆嗗崱閲囬泦瑙嗛锛屽垯stream鐨勬牸寮忔槸0,1,2,3杩欑锛屽緱瑙ｆ瀽鎴恑nt绫诲瀷
                if len(self.stream) <= 2:
                    self.stream = int(self.stream)
                self.position_filename = node_video.getAttribute('position_file')
                self.videowidth = int(node_video.getAttribute('width'))
                self.videoheight = int(node_video.getAttribute('height'))
                # logger.info('read_video_list, gametype=%s, stream=%s, pos_file=%s, width=%d, height=%d' %
                #             (self.gametype, self.stream, self.position_filename, self.videowidth, self.videoheight))
                # 20250703 pydealerLight
                self.engine_api_url = node_video.getAttribute('engine_api_url')
                # --- detection cadence knobs ---
                # Historical behavior uses a single skip_freq. For BALL3 and mixed sources,
                # allow overriding cadence independently for live streams vs local files.
                # All attributes are optional and safely fall back.
                self.skip_freq = int(node_video.getAttribute("skip_freq") or 120)
                self.skip_freq_live = int(node_video.getAttribute("skip_freq_live") or self.skip_freq)
                self.skip_freq_file = int(node_video.getAttribute("skip_freq_file") or self.skip_freq)

                # "freq" is from config.xml <common freq=...> and is passed into VideoManager as config_freq
                # (higher cadence when something is being detected). Provide optional per-source overrides.
                self.freq_live = int(node_video.getAttribute("freq_live") or self.freq)
                self.freq_file = int(node_video.getAttribute("freq_file") or self.freq)

                # BALL3: prefer time-based cadence over frame skip. Optional overrides.
                try:
                    self.ball3_min_interval_live_s = float(node_video.getAttribute("ball3_min_interval_live_s") or 0.25)
                except Exception:
                    self.ball3_min_interval_live_s = 0.25
                try:
                    self.ball3_min_interval_file_s = float(node_video.getAttribute("ball3_min_interval_file_s") or 0.05)
                except Exception:
                    self.ball3_min_interval_file_s = 0.05
                # PNG compression (0 fastest, 9 smallest). Optional.
                try:
                    self.ball3_png_compression = int(node_video.getAttribute("ball3_png_compression") or 1)
                except Exception:
                    self.ball3_png_compression = 1
                logger.info(f'read_video_list, gametype={self.gametype}, stream={self.stream}, \
                    pos_file={self.position_filename}, width={self.videowidth}, height={self.videoheight}, engine_api_url = {self.engine_api_url}, \
                    skip_freq={self.skip_freq}, skip_freq_live={self.skip_freq_live}, skip_freq_file={self.skip_freq_file}, \
                    freq_live={self.freq_live}, freq_file={self.freq_file}, \
                    ball3_min_interval_live_s={self.ball3_min_interval_live_s}, ball3_min_interval_file_s={self.ball3_min_interval_file_s}, \
                    ball3_png_compression={self.ball3_png_compression}')
                return True
        logger.error('read_video_list failed, filename=%s, vid=%s' %(filename, self.vid))
        return False

    # 璇诲彇瀹氫綅鐨勯厤缃枃浠?
    def read_position(self, filename):
        self.pos_list = []
        xml_file = xmldom.parse(filename)
        root = xml_file.documentElement

        # Check for tilt_angle in the annotation file
        size_node = root.getElementsByTagName('size')[0]
        tilt_angle_node = size_node.getElementsByTagName('tilt_angle')
        if tilt_angle_node:
            self.tilt_angle = int(tilt_angle_node[0].childNodes[0].nodeValue)
        else:
            self.tilt_angle = 0  # Set to default value if not present
        logger.info(f'Read tilt_angle: {self.tilt_angle}')

        nodes = root.getElementsByTagName('object')
        for node in nodes:
            card_name = node.getElementsByTagName('name')[0].childNodes[0].nodeValue
            str = card_name.split('_', 1)
            index = str[1]
            bnd_box = node.getElementsByTagName('bndbox')
            xmin = 0
            ymin = 0
            xmax = 0
            ymax = 0
            for box in bnd_box:
                xmin = box.getElementsByTagName('xmin')[0].childNodes[0].nodeValue
                ymin = box.getElementsByTagName('ymin')[0].childNodes[0].nodeValue
                xmax = box.getElementsByTagName('xmax')[0].childNodes[0].nodeValue
                ymax = box.getElementsByTagName('ymax')[0].childNodes[0].nodeValue

            pos = CardPositon(index, card_name, xmin, ymin, xmax, ymax)
            self.pos_list.append(pos)

        logger.info('read_position success, filename=%s, gametype=%s, vid=%s, count=%d' %
                    (filename, self.gametype, self.vid, len(self.pos_list)))
        return True

    # 璇诲垎鏁板垪琛?
    def read_scoreshold(self, filename):
        self.scoremap = {}
        xml_file = xmldom.parse(filename)
        root = xml_file.documentElement
        nodes = root.getElementsByTagName('puke')
        for node in nodes:
            index = int(node.getElementsByTagName('index')[0].childNodes[0].nodeValue)
            score = float(node.getElementsByTagName('threshold')[0].childNodes[0].nodeValue)
            self.scoremap[index] = score
        logger.info('read_position success, filename=%s,count=%d' %
                    (filename, len(self.scoremap)))
        return True
cfg = AppConfig('./config.xml', './models/videolist.xml','./models/score-threshold.xml')
cfg.load_config()
