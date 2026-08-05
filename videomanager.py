# encoding=utf-8

import cv2
import numpy as np
from cardinfo import CardInfo, GetCardVal
from datamanager import DataMgrInstance
from scanresultsave import ScanRMgrInstance
import pylogger as logger
from twisted.internet import reactor
import time
from skimage.metrics import structural_similarity as compare_ssim  # tf2.1
from config import cfg
import subprocess

# 20241025 add a button for manual predict process
import tkinter as tk
from tkinter import Button
from twisted.internet import tksupport
# 20241029 put imageSaver code in here
import datetime as d
import datetime
import os
import sys
# 20250103 implement http_post_api
import base64
import requests
import json
import ast
import threading
import traceback
import re

API_NO_CARD = 0
API_ZERO_CARD = 53
# ---- BALL3 debug image cache (frame fed to engine; optional big image on STOP) ----
LAST_BALL3_FRAME = None
LAST_BALL3_FRAME_META = {"gmcode": None, "seq": None, "ts": None}
LAST_BALL3_POST_FRAME = None  # BGR frame that was fed to BALL3 engine (latest)
LAST_BALL3_POST_INFO  = {}

# stable result cache (frame that triggered 3 consecutive results)
LAST_BALL3_RESULT_FRAME = None
LAST_BALL3_RESULT_INFO = {"gmcode":None,"cards":[],"scores":[]}

# Global predict-image folder (set from VideoManager.__init__).
_PREDICT_SAVEDIR = None
_BALL3_CACHE_LOCK = threading.Lock()


def save_ball3_stop_image(gmcode_str, predict_dir=None):

    if isinstance(gmcode_str, bytes):
        gmcode_str = gmcode_str.decode()

    # Resolve predict image directory (base)
    global _PREDICT_SAVEDIR
    if predict_dir is None:
        predict_dir = _PREDICT_SAVEDIR or getattr(cfg, 'savePredictImage_folder', None) or './predict_images'

    # Keep per-day folder layout: <predict_dir>/<YYYY-MM-DD>/...
    day_folder = datetime.datetime.now().strftime("%Y-%m-%d")
    day_dir = os.path.join(predict_dir, day_folder)

    try:
        os.makedirs(day_dir, exist_ok=True)
    except Exception as e:
        logger.error(f"[BALL3 SAVE] cannot create day_dir={day_dir}: {e}")
        predict_dir = './predict_images'
        day_dir = os.path.join(predict_dir, day_folder)
        os.makedirs(day_dir, exist_ok=True)


    cards = LAST_BALL3_RESULT_INFO.get("cards", ["UNK","UNK","UNK"])
    scores = LAST_BALL3_RESULT_INFO.get("scores", [0,0,0])

    best_conf = max(scores) if scores else 0.0

    frame = LAST_BALL3_RESULT_FRAME if LAST_BALL3_RESULT_FRAME is not None else LAST_BALL3_POST_FRAME

    if frame is None:
        logger.error("[BALL3 SAVE] frame missing")
        return

    ts = datetime.datetime.now().strftime("%Y%m%d")

    card_str = "_".join(cards)

    fname = f"{ts}_{gmcode_str}_#{card_str}({best_conf:.4f}).jpg"

    outpath = os.path.join(day_dir, fname)

    ok = cv2.imwrite(outpath, frame)

    if ok:
        logger.info(f"[BALL3 SAVE] predict image saved : {outpath}")

        # -------------------------------
        # Save round_end image (STOP frame)
        # -------------------------------
        try:
            round_frame = LAST_BALL3_POST_FRAME

            if round_frame is not None:
                round_dir = os.path.join(".", "round_end_imgs", day_folder)
                os.makedirs(round_dir, exist_ok=True)

                round_path = os.path.join(round_dir, f"{gmcode_str}.jpg")

                ok2 = cv2.imwrite(round_path, round_frame)

                if ok2:
                    logger.info(f"[BALL3 SAVE] round_end image saved : {round_path}")
                else:
                    logger.error(f"[BALL3 SAVE] round_end cv2.imwrite failed : {round_path}")

            else:
                logger.warning("[BALL3 SAVE] round_end frame missing")

        except Exception as e:
            logger.error(f"[BALL3 SAVE] round_end save failed: {e}")

        # -------------------------------
        # Cleanup candidate file
        # -------------------------------
        try:
            safe_gm = re.sub(r'[^0-9A-Za-z_\-]+', '_', str(gmcode_str))
            cand_path = os.path.join(day_dir, "_candidates", f"{safe_gm}.jpg")

            if os.path.exists(cand_path):
                os.remove(cand_path)
                logger.info(f"[BALL3 CANDIDATE] cleanup : {cand_path}")

        except Exception as e:
            logger.warning(f"[BALL3 CANDIDATE] cleanup failed: {e}")

    else:
        logger.error(f"[BALL3 SAVE] cv2.imwrite failed : {outpath}")


def save_ball3_candidate_image(gmcode_str, frame, cards, scores, predict_dir=None):
    """Overwrite a per-round *temporary* image for BALL3.

    Why it exists:
      STOP_PREDICT can arrive ~500ms after the 3rd consecutive result due to inference + network delay.
      If we only save on STOP, we'll often save a *future* frame.

    Behavior:
      - Write to a hidden per-day subfolder so it doesn't clutter normal outputs.
      - Always overwrite the same file for the current gmcode.
      - The STOP handler will read this cached frame and save the final image.
    """
    if frame is None:
        return
    if isinstance(gmcode_str, bytes):
        gmcode_str = gmcode_str.decode(errors='ignore')
    global _PREDICT_SAVEDIR
    if predict_dir is None:
        predict_dir = _PREDICT_SAVEDIR or getattr(cfg, 'savePredictImage_folder', None) or './predict_images'

    # keep predictable, per-day structure like the original behavior
    day_folder = datetime.datetime.now().strftime("%Y-%m-%d")
    hidden_tmp_dir = os.path.join(predict_dir, day_folder, "_candidates")
    os.makedirs(hidden_tmp_dir, exist_ok=True)

    # keep filename stable (overwrite)
    safe_gm = re.sub(r'[^0-9A-Za-z_\-]+', '_', str(gmcode_str))
    outpath = os.path.join(hidden_tmp_dir, f"{safe_gm}.jpg")
    try:
        cv2.imwrite(outpath, frame)
        logger.info(f"[BALL3 CANDIDATE] overwrite : {outpath} cards={cards} scores={scores}")
    except Exception as e:
        logger.error(f"[BALL3 CANDIDATE] cv2.imwrite failed : {outpath}: {e}")


def _rank_from_any(cls_value):
    """Convert model output class to rank 1..13.

    Supports:
      - numeric API classes 1..52
      - numeric ranks 1..13
      - face strings: A,J,Q,K (case-insensitive)
    """
    if cls_value is None:
        return None

    # numeric path (including strings like "12" or "12.0")
    try:
        v = int(float(cls_value))
        # if already rank 1..13
        if 1 <= v <= 13:
            return v
        # else treat as API class 1..52
        return _api_rank_1_to_13(v)
    except Exception:
        pass

    # string path (A/J/Q/K)
    s = str(cls_value).strip().upper()
    face = {"A": 1, "J": 11, "Q": 12, "K": 13}
    if s in face:
        return face[s]
    return None


def _api_rank_1_to_13(api_cls):
    """Safe conversion of API class id to rank 1..13"""
    if api_cls is None:
        return None
    try:
        api_cls = int(api_cls)
    except Exception:
        return None
    if 1 <= api_cls <= 13:
        return api_cls
    if 14 <= api_cls <= 26:
        return api_cls - 13
    if 27 <= api_cls <= 39:
        return api_cls - 26
    if 40 <= api_cls <= 52:
        return api_cls - 39
    return None

def _api_to_phbac_class(api_cls: int):
    """
    Convert API class (1..52; 0=no-card, 53=zero-card) to PH_BAC dealer_classid
    as defined by cardinfo.GetCardVal() bases:
      club: base 0 -> 1..13
      diamond: base 16 -> 17..29
      spade: base 32 -> 33..45
      heart: base 48 -> 49..61
    """
    if api_cls in (API_NO_CARD, API_ZERO_CARD):
        return None
    # clubs 1..13 -> 1..13
    if 1 <= api_cls <= 13:
        return api_cls
    # diamonds 14..26 -> 17..29  (base 16 + rank)
    if 14 <= api_cls <= 26:
        return 16 + (api_cls - 13)
    # hearts 27..39 -> 49..61   (base 48 + rank)
    if 27 <= api_cls <= 39:
        return 48 + (api_cls - 26)
    # spades 40..52 -> 33..45   (base 32 + rank)
    if 40 <= api_cls <= 52:
        return 32 + (api_cls - 39)
    return None



class VideoManager(object):
    def __init__(self, gametype, stream, videowidth, videoheight, poslist, dealer,
                 imageSaver, onelabel, freq, tilt_angle, save_predictions, save_full_image,
                 savedir, predict_savedir,skip_freq, window_resize_width=640, window_resize_height=480):
        """
        This VideoManager now supports:
        - BJ21: whole-frame group detection (original Light logic)
        - BAC/dragonpoker: per-index single-card HTTP detection
        """
        self.gametype = (gametype or '').upper()
        self.stream = stream
        self.config_videowidth = videowidth
        self.config_videoheight = videoheight
        self.config_poslist = poslist
        self.dealer = dealer
        self.imageSaver = imageSaver
        self.onelabel = onelabel
        self.config_freq = freq
        # Base cadence from config (legacy):
        # - skip_freq: idle cadence (no detection)
        # - config_freq: detection cadence (when something is being detected)
        # For better tuning, allow independent live/file cadence. If config.xml/videolist.xml
        # doesn't provide these, they fall back to the legacy single values.
        self.skip_freq = skip_freq
        self.skip_freq_live = getattr(cfg, 'skip_freq_live', self.skip_freq)
        self.skip_freq_file = getattr(cfg, 'skip_freq_file', self.skip_freq)
        self.config_freq_live = getattr(cfg, 'freq_live', self.config_freq)
        self.config_freq_file = getattr(cfg, 'freq_file', self.config_freq)
        self.resultlist = []
        self.stopRun = False
        self.isExit = False
        self.resize_width = window_resize_width
        self.resize_height = window_resize_height
        # 20240926 tilt_angle
        self.tilt_angle = tilt_angle
        # pause mechanic
        self.paused = False
        self.last_click_time = 0
        # 20241025 manual predict toggle
        self.use_manual_flag = False
        self.predictFlag_manual = False
        self.root = None
        # 20241025 toggle save predictions
        self.save_predictions = save_predictions
        # Raw ROI copies under predict_images/<date>/original_crop.
        # Default is OFF when save_original_crop is omitted from config.xml.
        self.save_original_crop = bool(
            getattr(cfg, 'savePredictImage_save_original_crop', False)
        )
        self.save_full_image = save_full_image
        # 20241029 imageSaver
        self.auditDir = savedir
        # 20250829 where to store the small ROI images we POST to the model
        self.predict_savedir = predict_savedir

        # Make predict folder available to dealerclient callbacks (module-level helper)
        global _PREDICT_SAVEDIR
        _PREDICT_SAVEDIR = self.predict_savedir
        if self.save_predictions and self.predict_savedir and not os.path.exists(self.predict_savedir):
            try:
                os.makedirs(self.predict_savedir, exist_ok=True)
                logger.info(f'create predict_savedir: {self.predict_savedir}')
            except Exception as e:
                logger.error(f'create predict_savedir failed: {self.predict_savedir}, err={e}')
        # 20250703 add url for pydealerLight
        self.engine_api_url = cfg.engine_api_url

        # BAC ROI preprocess before posting to external model API.
        # Configurable from config.xml <bacPreprocess ... />.
        self.bac_preprocess_resize_enable = bool(getattr(cfg, 'bac_preprocess_resize_enable', True))
        self.bac_preprocess_resize_mode = str(
            getattr(cfg, 'bac_preprocess_resize_mode', 'keep_ratio_no_pad')
        ).strip().lower()
        self.bac_preprocess_resize_min_w = max(1, int(getattr(cfg, 'bac_preprocess_resize_min_w', 320)))
        self.bac_preprocess_resize_min_h = max(1, int(getattr(cfg, 'bac_preprocess_resize_min_h', 320)))
        self.bac_preprocess_resize_target_w = max(1, int(getattr(cfg, 'bac_preprocess_resize_target_w', 320)))
        self.bac_preprocess_resize_target_h = max(1, int(getattr(cfg, 'bac_preprocess_resize_target_h', 320)))
        logger.info(
            f"[BAC_PREPROCESS_CONFIG] resize_enable={self.bac_preprocess_resize_enable}, "
            f"resize_mode={self.bac_preprocess_resize_mode}, "
            f"resize_min_wh=({self.bac_preprocess_resize_min_w},{self.bac_preprocess_resize_min_h}), "
            f"resize_target_wh=({self.bac_preprocess_resize_target_w},{self.bac_preprocess_resize_target_h}), "
            f"save_original_crop={self.save_original_crop}"
        )

        # Reuse HTTP connection to reduce latency per request
        self._http_session = requests.Session()

        # BAC preprocess size audit log cache.
        # Log once per round/index/size pair to avoid flooding logs while still showing
        # the exact crop size before resize and the engine input size after resize.
        self._bac_preprocess_size_log_cache = set()
        self._bac_preprocess_payload_log_cache = set()

        # BALL3 inference cadence
        # Live streams are bursty and can flood the engine if we post on every grabbed frame,
        # so we keep a minimum interval there.
        # Local video files are stable and should feel much faster/responsive, so we allow
        # a higher cadence.
        # NOTE: Keep PNG for accuracy. Use low PNG compression to speed up encoding.
        self._ball3_min_interval_live_s = 0.0
        self._ball3_min_interval_file_s = 0.0
        self._ball3_min_interval_s = 0.0
        self._ball3_last_post_ts = 0.0
        self._ball3_png_compression = getattr(cfg, 'ball3_png_compression', 1)  # 0(fastest)~9(smallest). Recommend 0~2 for BALL3.

        # Track current source mode (set in playVideo)
        self._source_is_live = False
        self._ui_ball3_plus_rect = None
        self._ui_ball3_minus_rect = None

        # DataMgr registers
        DataMgrInstance().setgametype(self.gametype)
        DataMgrInstance().register_ImageSaver(imageSaver)
        # use dealer's callback
        DataMgrInstance().register_senddata(dealer.sendPredictResult)

        # Keep last boxes for drawing
        self.last_detected_boxes = []           # list of [x1,y1,x2,y2]
        self.last_detected_group_boxes = {}     # dict: group_idx -> [x1,y1,x2,y2]

        # --- realtime latest-frame buffer (for live streams) ---
        self._frame_lock = threading.Lock()
        self._latest_frame = None
        self._latest_frame_id = 0
        self._latest_ts = 0.0

        self._cap = None
        self._grab_thread = None
        self._infer_thread = None
        self._rt_skip_freq = self.skip_freq
        self._rt_nframe = 0
        self._rt_last_infer_frame_id = -1

        # BALL3: per-gmcode sequence for naming the saved predict_images frames
        self._ball3_seq_gmcode = None
        self._ball3_seq = 0

        # live reconnect watchdog
        self.live_stall_timeout_s = float(getattr(cfg, 'live_stall_timeout_s', 10.0))
        self.live_reopen_cooldown_s = float(getattr(cfg, 'live_reopen_cooldown_s', 3.0))
        self._live_last_reopen_ts = 0.0
        self._live_reconnect_needed = False
        self._live_reconnect_reason = ''
        self._live_reopening = False
        self._grab_fail_count = 0
        self._grab_fail_start_ts = 0.0
        self._grab_stop_request = False
        self._live_reopen_grace_until = 0.0


    def _rank_label(self, r: int) -> str:
        return {1: 'A', 11: 'J', 12: 'Q', 13: 'K'}.get(r, str(r))

    # ---------------- cadence helpers ----------------
    def _get_idle_skip_freq(self) -> int:
        return int(self.skip_freq_live if self._source_is_live else self.skip_freq_file)

    def _get_detect_skip_freq(self) -> int:
        return int(self.config_freq_live if self._source_is_live else self.config_freq_file)

    def _request_live_reconnect(self, reason: str):
        if not self._source_is_live:
            return
        now = time.time()
        if self._live_reopening:
            return
        if (now - self._live_last_reopen_ts) < self.live_reopen_cooldown_s:
            return
        self._live_reconnect_needed = True
        self._live_reconnect_reason = reason
        self._live_last_reopen_ts = now
        logger.warning(f'live reconnect requested: {reason}')

    def _reopen_live_capture(self):
        if not self._source_is_live or self._live_reopening:
            return False
        self._live_reopening = True
        reason = self._live_reconnect_reason or 'unknown'
        logger.warning(f'reopening live capture, reason={reason}')
        old_thread = self._grab_thread
        old_cap = self._cap
        try:
            # Tell the current grab loop to stop before swapping capture.
            self._grab_stop_request = True
            time.sleep(0.05)
            try:
                if old_cap is not None and old_cap.isOpened():
                    old_cap.release()
            except Exception:
                pass
            if old_thread is not None and old_thread.is_alive():
                try:
                    old_thread.join(timeout=0.5)
                except Exception:
                    pass
            time.sleep(0.2)
            new_cap = cv2.VideoCapture(self.stream)
            if not new_cap.isOpened():
                logger.error('live capture reopen failed: cap.isOpened() == False')
                return False
            try:
                new_cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
            self._cap = new_cap
            self._grab_fail_count = 0
            self._grab_fail_start_ts = 0.0
            self._live_reconnect_needed = False
            self._live_reconnect_reason = ''
            self._grab_stop_request = False
            # Clear stale snapshot so the UI loop does not instantly request reconnect again.
            with self._frame_lock:
                self._latest_frame = None
                self._latest_ts = 0.0
            self._live_reopen_grace_until = time.time() + 2.0
            self._grab_thread = threading.Thread(target=self._grab_loop, args=(new_cap,), daemon=True)
            self._grab_thread.start()
            logger.info('live capture reopened successfully')
            return True
        except Exception:
            logger.exception('_reopen_live_capture failed')
            return False
        finally:
            self._live_reopening = False

    # ---------------- BALL3 helpers ----------------
    def _ball3_next_seq(self, gmcode_show: str) -> int:
        """Return an increasing seq (0,1,2,...) for the current gmcode. Reset on gmcode change."""
        if gmcode_show != self._ball3_seq_gmcode:
            self._ball3_seq_gmcode = gmcode_show
            self._ball3_seq = 0
        seq = self._ball3_seq
        self._ball3_seq += 1
        return seq

    def _save_ball3_predict_frame(self, gmcode_show: str, frame_bgr, seq: int):
        """Save the exact frame fed to BALL3 engine. Filename must be {gmcode}_{seq}.jpg."""
        if not self.save_predictions:
            return
        base_dir = self.predict_savedir or './predict_images'
        day_dir = d.datetime.now().strftime('%Y-%m-%d')
        out_dir = os.path.join(base_dir, day_dir)
        os.makedirs(out_dir, exist_ok=True)
        fname = f"{gmcode_show}_{seq}.jpg"
        path = os.path.join(out_dir, fname)
        cv2.imwrite(path, frame_bgr)
        logger.info(f'write prediction image, image file path ={path}')


    def _predict_to_dealer(self, predict_classid: int):
        """
        Convert HTTP model class id (1..52; 0 & 53 are special) to
        (dealer_classid, suit_pinyin, rank_int).
        API suits order: 1..13 clubs, 14..26 diamonds, 27..39 hearts, 40..52 spades
        PH dealer offsets: mei(♣)=0, fang(♦)=16, hong(♥)=48, hei(♠)=32
        """
        if predict_classid in (0, 53) or predict_classid is None:
            return None

        suit_idx = (predict_classid - 1) // 13          # 0:clubs,1:diamonds,2:hearts,3:spades
        rank      = ((predict_classid - 1) % 13) + 1    # 1..13
        suit_key  = ['mei', 'fang', 'hong', 'hei'][suit_idx]
        base_off  = {'mei': 0, 'fang': 16, 'hong': 48, 'hei': 32}[suit_key]
        dealer_id = base_off + rank
        return dealer_id, suit_key, rank

    def _save_predict_patch(self, gmcode_show: str, index: int, patch_bgr, predict_classid: int=None, score: float=None, subfolder: str=None):
        """
        Save prediction patch image.
        Default path:
        <predict_savedir>/<YYYY-MM-DD>/
        Optional original-crop path example:
        <predict_savedir>/<YYYY-MM-DD>/original_crop/
        """
        try:
            if not self.save_predictions:
                return None

            # resolve folder (with daily subdir)
            base_dir = self.predict_savedir or './predict_images'
            day_dir  = d.datetime.now().strftime('%Y-%m-%d')
            out_dir  = os.path.join(base_dir, day_dir)
            save_type = 'engine_input'
            if subfolder:
                out_dir = os.path.join(out_dir, str(subfolder))
                save_type = str(subfolder)
            os.makedirs(out_dir, exist_ok=True)

            ts = d.datetime.now().strftime('%Y%m%d%H%M')
            fname_core = f"{ts}_{gmcode_show}_{index}"

            # enrich with prediction info when available
            if predict_classid is not None and score is not None:
                conv = self._predict_to_dealer(predict_classid)
                if conv is not None:
                    dealer_id, suit_key, rank_int = conv
                    rank_label = self._rank_label(rank_int)
                    fname = f"{fname_core}_#{dealer_id}_{suit_key}_{rank_label}@{predict_classid}({float(score):0.4f}).jpg"
                else:
                    # special/no-card -> still save, but without dealer mapping
                    fname = f"{fname_core}_@{predict_classid}({float(score):0.4f}).jpg"
            else:
                fname = f"{fname_core}.jpg"

            path = os.path.join(out_dir, fname)
            ok = cv2.imwrite(path, patch_bgr)
            if not ok:
                raise RuntimeError(f"cv2.imwrite returned False, path={path}")
            logger.info(f'[BAC_PREDICT_IMAGE_SAVE] type={save_type}, image_shape_hwc={patch_bgr.shape if patch_bgr is not None else None}, path={path}')
            return path
        except Exception as e:
            logger.exception(f'_save_predict_patch failed: subfolder={subfolder}, err={e}')
            return None

    # ---------------- UI ----------------
    def setup_ui(self):
        self.root = tk.Tk()
        self.root.title("Prediction Control")
        self.initial_manual_button = Button(self.root, text="Use manual predictFlag?",
                                            command=self.set_manual_flag)
        self.initial_manual_button.pack()

    def set_manual_flag(self):
        self.use_manual_flag = True
        logger.info('User chose to use manual predictFlag.')
        self.initial_manual_button.destroy()
        self.toggle_button = Button(self.root, text="Start Prediction", command=self.toggle_prediction)
        self.toggle_button.pack()

    def toggle_prediction(self):
        self.predictFlag_manual = not self.predictFlag_manual
        if self.predictFlag_manual:
            self.toggle_button.config(text="Stop Prediction")
            logger.info('Prediction started manually.')
        else:
            self.toggle_button.config(text="Start Prediction")
            logger.info('Prediction stopped manually.')

    def mouse_callback(self, event, x, y, flags, param):
        """Mouse callback for OpenCV window.
        - Double click: pause/resume
        - Single click on BALL3 +/- buttons: adjust post interval
        """
        if event == cv2.EVENT_LBUTTONDBLCLK:
            self.toggle_pause_resume()
            return

        # BALL3 speed buttons (bottom-right UI).
        if self.gametype == 'BALL3' and event == cv2.EVENT_LBUTTONDOWN:
            r_plus = getattr(self, '_ui_ball3_plus_rect', None)
            r_minus = getattr(self, '_ui_ball3_minus_rect', None)
            if r_plus and (r_plus[0] <= x <= r_plus[2]) and (r_plus[1] <= y <= r_plus[3]):
                self._ball3_adjust_interval(faster=True)
                return
            if r_minus and (r_minus[0] <= x <= r_minus[2]) and (r_minus[1] <= y <= r_minus[3]):
                self._ball3_adjust_interval(faster=False)
                return

    def _ball3_adjust_interval(self, faster: bool):
        """Adjust BALL3 post interval for current source (LIVE or FILE).
        This changes the *minimum* interval between HTTP posts. Actual throughput
        is still limited by model-engine latency (time cost).
        """
        step = 0.02
        if faster:
                    self._ball3_min_interval_s = 0.0
        else:
                    self._ball3_min_interval_s = 0.0

        if getattr(self, '_source_is_live', False):
                    self._ball3_min_interval_live_s = 0.0
        else:
                    self._ball3_min_interval_file_s = 0.0

        logger.info(f"[UI] BALL3 post interval now {self._ball3_min_interval_s:.2f}s (live={getattr(self, '_source_is_live', False)})")

    def toggle_pause_resume(self):
        if self.paused:
            self.paused = False
            logger.info('Resuming video and processes...')
        else:
            self.paused = True
            logger.info('Pausing video and processes...')

    # ---------------- lifecycle ----------------
    def start(self):
        if self.root:
            tksupport.install(self.root)
        reactor.callInThread(self.run)

    def run(self):
        playVideoCount = 0
        while not self.stopRun:
            ifopenVideo = self.playVideo(self.stream, self.config_poslist)
            if self.isExit or not ifopenVideo:
                self.cleanup(playVideoCount)
                break

    def cleanup(self, playVideoCount):
        if playVideoCount > 20:
            logger.info(f'openVideo failed, exit after {playVideoCount} attempts')
        self.stopRun = True
        cv2.destroyAllWindows()
        if self.imageSaver:
            try:
                self.imageSaver.stop()
            except Exception:
                pass
        reactor.callFromThread(reactor.stop)
        if self.root:
            self.root.quit()

    # ---------------- helpers ----------------
    def camera_check(self, cap):
        if cap.isOpened():
            success, frame = cap.read()
            if success and frame is not None:
                error_template = cv2.imread('./models/error_frame.jpg')
                if error_template is not None:
                    score = compare_ssim(cv2.GaussianBlur(frame, (11, 11), 0),
                                         error_template,
                                         multichannel=True)
                    return score < 0.99
            logger.info("Camera read failed or error frame comparison failed")
        return False

    def adjust_capture_settings(self, cap):
        counter = 0
        while counter <= 10:
            if cap.isOpened():
                cap.release()
            cap = cv2.VideoCapture(self.stream)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc('M','J','P','G'))
            cap.set(cv2.CAP_PROP_FPS, 30)
            stream_width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            stream_height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, stream_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, stream_height)
            logger.info(f"cv2.CAP_PROP_FRAME_WIDTH set to : {stream_width}, cv2.CAP_PROP_FRAME_HEIGHT set to : {stream_height}")
            if self.camera_check(cap):
                break
            counter += 1

    # ---------------- main loop ----------------
    def _is_live_stream(self, videoname):
        # int camera index => live
        if isinstance(videoname, int):
            return True
        if not isinstance(videoname, str):
            return False
        s = videoname.lower()
        return s.startswith(("rtsp://", "rtsps://", "http://", "https://", "rtmp://", "udp://"))

    

    def _grab_loop(self, cap):
        """Continuously grab newest frames and overwrite self._latest_frame."""
        while not self.stopRun and not self.isExit:
            if self._grab_stop_request:
                break
            # If a newer capture object has already replaced this one, exit quietly.
            if self._source_is_live and self._cap is not None and cap is not self._cap:
                break
            if cap is None or not cap.isOpened():
                time.sleep(0.01)
                continue
            try:
                ret, frame = cap.read()
                now = time.time()
                if (not ret) or frame is None:
                    if self._source_is_live:
                        if self._grab_fail_count == 0:
                            self._grab_fail_start_ts = now
                        self._grab_fail_count += 1
                        fail_dur = now - self._grab_fail_start_ts
                        if fail_dur >= self.live_stall_timeout_s:
                            self._request_live_reconnect(
                                f'grab_loop read failed for {fail_dur:.1f}s (count={self._grab_fail_count})'
                            )
                    time.sleep(0.005)
                    continue

                self._grab_fail_count = 0
                self._grab_fail_start_ts = 0.0

                if self.tilt_angle != 0:
                    frame = self.rotate_frame(frame, self.tilt_angle)

                with self._frame_lock:
                    self._latest_frame = frame
                    self._latest_frame_id += 1
                    self._latest_ts = now

                time.sleep(0.001)
            except cv2.error:
                # This can happen when another thread releases the old capture during reconnect.
                if self._live_reopening or self._grab_stop_request or (self._source_is_live and self._cap is not None and cap is not self._cap):
                    logger.warning('_grab_loop cv2.error during capture swap; exiting old grab loop')
                    break
                logger.exception('_grab_loop crashed')
                if self._source_is_live:
                    self._request_live_reconnect('_grab_loop cv2.error')
                time.sleep(0.2)
            except Exception:
                if self._live_reopening or self._grab_stop_request or (self._source_is_live and self._cap is not None and cap is not self._cap):
                    logger.warning('_grab_loop exception during capture swap; exiting old grab loop')
                    break
                logger.exception('_grab_loop crashed')
                if self._source_is_live:
                    self._request_live_reconnect('_grab_loop exception')
                time.sleep(0.2)

    def _infer_loop(self, poslist):
        """Background inference: always uses newest frame snapshot."""
        while not self.stopRun and not self.isExit:
            try:
                if self.paused:
                    time.sleep(0.01)
                    continue
    
                if self.use_manual_flag:
                    predictFlag = self.predictFlag_manual
                else:
                    predictFlag = DataMgrInstance().getPredictFlag()
    
                gmcode = DataMgrInstance().getGamecode()
                gmcode_show = gmcode
                if isinstance(gmcode, bytes):
                    gmcode_show = gmcode.decode('utf-8').rstrip('\x00')
    
                if not (predictFlag and gmcode):
                    time.sleep(0.01)
                    continue
    
                with self._frame_lock:
                    if self._latest_frame is None:
                        frame = None
                        fid = None
                    else:
                        fid = self._latest_frame_id
                        frame = self._latest_frame.copy()
    
                if frame is None:
                    time.sleep(0.005)
                    continue
    
                if fid == self._rt_last_infer_frame_id:
                    time.sleep(0.005)
                    continue
                self._rt_last_infer_frame_id = fid
    
                if self.gametype != 'BALL3':
                    self._rt_nframe += 1
                    isDetect = (self._rt_nframe >= self._rt_skip_freq)
                    if not isDetect:
                        continue
                    self._rt_nframe = 0
    
                self.resultlist = []
                new_card_boxes = None
                new_group_boxes = None
                is_card_detected = False
    
                if self.gametype == 'BJ21':
                    new_card_boxes, new_group_boxes, is_card_detected = self._process_frame_bj21(
                        frame, gmcode, gmcode_show, fid
                    )
                elif self.gametype == 'BALL3':
                    new_card_boxes, new_group_boxes, is_card_detected = self._process_frame_ball3(
                        frame, gmcode, gmcode_show, fid
                    )
                else:
                    new_card_boxes, is_card_detected = self._process_frame_bac(
                        frame, poslist, gmcode, gmcode_show, fid
                    )
                    new_group_boxes = None
    
                if new_card_boxes is not None:
                    self.last_detected_boxes = new_card_boxes
                if new_group_boxes is not None:
                    self.last_detected_group_boxes = new_group_boxes
    
                if len(self.resultlist) > 0:
                    DataMgrInstance().addResultlist(gmcode, self.resultlist)
    
                if self.gametype == 'BAC':
                    self._rt_skip_freq = self._get_detect_skip_freq()
                    if is_card_detected and self.save_full_image:
                        last_frame = frame.copy()
                        self.save_full_img(gmcode, last_frame, gmcode_show)
                else:
                    if is_card_detected:
                        self._rt_skip_freq = self._get_detect_skip_freq()
                        if self.save_full_image and self.gametype != 'BALL3':
                            last_frame = frame.copy()
                            self.save_full_img(gmcode, last_frame, gmcode_show)
                    else:
                        self._rt_skip_freq = self._get_idle_skip_freq()
    
            except Exception:
                logger.exception('_infer_loop crashed')
                time.sleep(0.2)
    
    def playVideo(self, videoname, poslist):
            logger.info(f'Starting video stream: {videoname}')
            cap = cv2.VideoCapture(videoname)
    
            self.stream_videowidth = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            self.stream_videoheight = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    
            if self.config_videowidth != self.stream_videowidth:
                logger.info(f"WARNING : config videowidth is {self.config_videowidth}, but the stream videowidth is {self.stream_videowidth}, exit program")
                reactor.callFromThread(reactor.stop)
                self.isExit = True
                raise ValueError('config videowidth and stream videowidth mismatch')
    
            if self.config_videoheight != self.stream_videoheight:
                logger.info(f"WARNING : config videoheight is {self.config_videoheight}, but the stream videoheight is {self.stream_videoheight}, exit program")
                reactor.callFromThread(reactor.stop)
                self.isExit = True
                raise ValueError('config videoheight and stream videoheight mismatch')
    
            if isinstance(videoname, int):
                self.adjust_capture_settings(cap)
    
            if not cap.isOpened():
                logger.info('cap.isOpened() failed')
                return False
    
            nframe = 0
            frame_id = 0
            # Per-source cadence
            self._source_is_live = self._is_live_stream(videoname)
            skip_freq = self._get_idle_skip_freq()
            winname = 'pydealerclientLight'
            cv2.namedWindow(winname)
    
            is_live = self._source_is_live
            # Local file looping: if videoname is a local video file, loop back to start when EOF.
            is_local_file = (not is_live) and isinstance(videoname, str) and os.path.exists(videoname)
            # BALL3 cadence: local files can run faster than live streams
            if self.gametype == 'BALL3':
                        self._ball3_min_interval_s = 0.0
            eof_loop_logged = False
            self._cap = cap
    
            if is_live:
                try:
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                except Exception:
                    pass
    
                # Init live cadence
                self._rt_skip_freq = self._get_idle_skip_freq()
    
                self._grab_thread = threading.Thread(target=self._grab_loop, args=(cap,), daemon=True)
                self._infer_thread = threading.Thread(target=self._infer_loop, args=(poslist,), daemon=True)
                self._grab_thread.start()
                self._infer_thread.start()
    
            while True:
                if not self.paused:
                    if is_live:
                        if self._live_reconnect_needed:
                            self._reopen_live_capture()
    
                        with self._frame_lock:
                            if self._latest_frame is None:
                                frame = None
                                fid = frame_id
                                latest_ts = self._latest_ts
                            else:
                                frame = self._latest_frame.copy()
                                fid = self._latest_frame_id
                                latest_ts = self._latest_ts
    
                        now = time.time()
                        if now >= self._live_reopen_grace_until and latest_ts > 0:
                            stale_dur = now - latest_ts
                            if stale_dur >= self.live_stall_timeout_s:
                                self._request_live_reconnect(
                                    f'no new live frame for {stale_dur:.1f}s (latest_frame_id={self._latest_frame_id})'
                                )
    
                        if frame is not None:
                            gmcode = DataMgrInstance().getGamecode()
                            gmcode_show = gmcode
                            if isinstance(gmcode, bytes):
                                gmcode_show = gmcode.decode('utf-8').rstrip('\x00')
    
                            self.display_frame(frame, winname, gmcode, gmcode_show, fid)
    
                    else:
                        # Throttle repeated read failures to avoid log spam.
                        # (stream hiccups / EOF / reconnect issues can produce thousands of identical lines)
                        if not hasattr(self, "_read_fail_count"):
                            self._read_fail_count = 0
                            self._read_fail_last_log_ts = 0.0
    
                        ret, frame = cap.read()
                        frame_id += 1
                        if not ret or frame is None:
                            # If this is a local video file, we auto-loop when reaching EOF.
                            if is_local_file:
                                if not eof_loop_logged:
                                    logger.info('Video EOF reached, looping back to start (local file)')
                                    eof_loop_logged = True
                                try:
                                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                                except Exception:
                                    pass
                                # reset counters so detection cadence stays consistent after loop
                                frame_id = 0
                                nframe = 0
                                skip_freq = self.skip_freq
                                time.sleep(0.01)
                                continue
    
                            # For stream / non-local: log at most once per ~5s, with suppression count.
                            now = time.time()
                            self._read_fail_count += 1
                            if (now - self._read_fail_last_log_ts) >= 30.0:
                                if self._read_fail_count == 1:
                                    logger.warning('Failed to read frame from video')
                                else:
                                    logger.warning(
                                        f'Failed to read frame from video (x{self._read_fail_count} in last ~30s)'
                                    )
                                self._read_fail_last_log_ts = now
                                self._read_fail_count = 0
                            continue
    
                        # Recover log (only once) after a failure streak.
                        if getattr(self, "_read_fail_count", 0) != 0:
                            logger.info('Video frame read recovered')
                            self._read_fail_count = 0
                            self._read_fail_last_log_ts = 0.0
                        eof_loop_logged = False
    
                        if self.tilt_angle != 0:
                            frame = self.rotate_frame(frame, self.tilt_angle)
    
                        gmcode = DataMgrInstance().getGamecode()
                        gmcode_show = gmcode
                        if isinstance(gmcode, bytes):
                            gmcode_show = gmcode.decode('utf-8').rstrip('\x00')
    
                        nframe += 1
                        isDetect = (nframe >= skip_freq)
                        if isDetect:
                            nframe = 0
    
                        # BALL3: use time-based cadence to avoid slow skip_freq waits
                        if self.gametype == 'BALL3':
                            now = time.time()
                            if not hasattr(self, '_ball3_local_last_post_ts'):
                                self._ball3_local_last_post_ts = 0.0
                            if (now - self._ball3_local_last_post_ts) >= self._ball3_min_interval_s:
                                isDetect = True
                                self._ball3_local_last_post_ts = now
                            else:
                                isDetect = False
    
                        if self.use_manual_flag:
                            predictFlag = self.predictFlag_manual
                        else:
                            predictFlag = DataMgrInstance().getPredictFlag()
    
                        new_card_boxes = None
                        new_group_boxes = None
                        is_card_detected = False
    
                        if predictFlag and gmcode and isDetect:
                            self.resultlist = []
                            if self.gametype == 'BJ21':
                                new_card_boxes, new_group_boxes, is_card_detected = self._process_frame_bj21(
                                    frame, gmcode, gmcode_show, frame_id
                                )
                            elif self.gametype == 'BALL3':
                                new_card_boxes, new_group_boxes, is_card_detected = self._process_frame_ball3(
                                    frame, gmcode, gmcode_show, frame_id
                                )
                            else:
                                new_card_boxes, is_card_detected = self._process_frame_bac(
                                    frame, poslist, gmcode, gmcode_show, frame_id
                                )
                                new_group_boxes = None
    
                            if new_card_boxes is not None:
                                self.last_detected_boxes = new_card_boxes
                            if new_group_boxes is not None:
                                self.last_detected_group_boxes = new_group_boxes
    
                            if len(self.resultlist) > 0:
                                DataMgrInstance().addResultlist(gmcode, self.resultlist)
    
                            if self.gametype == 'BAC':
                                skip_freq = self._get_detect_skip_freq()
                                if is_card_detected and self.save_full_image:
                                    last_frame = frame.copy()
                                    self.save_full_img(gmcode, last_frame, gmcode_show)
                            else:
                                if is_card_detected:
                                    skip_freq = self._get_detect_skip_freq()
                                    # Requirement: BALL3 big image should be saved only when STOP predict is received
                                    if self.save_full_image and self.gametype != 'BALL3':
                                        last_frame = frame.copy()
                                        self.save_full_img(gmcode, last_frame, gmcode_show)
                                else:
                                    skip_freq = self._get_idle_skip_freq()
    
                        self.display_frame(frame, winname, gmcode, gmcode_show, frame_id)
    
                key = cv2.waitKey(1)
                # Runtime tuning hotkeys (keep minimal, no UI redesign):
                #   '=' or '+' : faster (lower skip_freq / lower BALL3 interval)
    
                if key & 0xFF == ord('q') or cv2.getWindowProperty(winname, cv2.WND_PROP_AUTOSIZE) < 1:
                    self.stopRun = True
                    logger.error('Exiting...')
                    cv2.destroyAllWindows()
                    reactor.callFromThread(reactor.stop)
                    self.isExit = True
                    break
    
            active_cap = self._cap if self._cap is not None else cap
            try:
                if active_cap is not None and active_cap.isOpened():
                    active_cap.release()
            except Exception:
                pass
            return True
    
        # ---------------- HTTP helpers ----------------
    
    def _encode_frame_base64(self, frame, ext='.jpg', imencode_params=None):
        if frame is None or frame.size == 0:
            raise RuntimeError('empty frame passed to _encode_frame_base64')
        ext = (ext or '.jpg').lower()
        if imencode_params is None:
            if ext == '.png':
                imencode_params = [int(cv2.IMWRITE_PNG_COMPRESSION), 1]
            else:
                imencode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 95]
        ok, buffer = cv2.imencode(ext, frame, imencode_params)
        if not ok:
            raise RuntimeError(f'cv2.imencode failed on the current frame, ext={ext}')
        return base64.b64encode(buffer).decode('utf-8')

    def _bac_keep_ratio_resize_no_pad(self, roi, target_w, target_h):
        """
        Keep aspect ratio and resize only. Do NOT pad to 320x320.

        With the default target_w=target_h=320, this means:
        - 80x160  -> 160x320
        - 160x80  -> 320x160
        - 140x84  -> 320x192

        The actual image sent to the model API can therefore be non-square.
        """
        if roi is None or roi.size == 0:
            raise RuntimeError('empty roi passed to _bac_keep_ratio_resize_no_pad')

        roi_h, roi_w = roi.shape[:2]
        target_w = max(1, int(target_w))
        target_h = max(1, int(target_h))
        scale = min(float(target_w) / float(max(1, roi_w)), float(target_h) / float(max(1, roi_h)))
        resized_w = max(1, int(round(float(roi_w) * scale)))
        resized_h = max(1, int(round(float(roi_h) * scale)))

        if resized_w != roi_w or resized_h != roi_h:
            resized = cv2.resize(roi, (resized_w, resized_h), interpolation=cv2.INTER_LINEAR)
        else:
            resized = roi.copy()

        meta = {
            'mode': 'keep_ratio_no_pad',
            'scale': float(scale),
            'original_wh': (int(roi_w), int(roi_h)),
            'resized_wh': (int(resized_w), int(resized_h)),
            'engine_wh': (int(resized_w), int(resized_h)),
            'pad_ltrb': (0, 0, 0, 0),
        }
        return resized, meta
    
    def _bac_keep_ratio_resize_center_pad(self, roi, target_w, target_h):
        """
        Match SL_crop_tool Step 2 preprocessing:

        1. Preserve the original aspect ratio.
        2. Resize the image to fit inside target W:H.
        3. Center-pad the missing area using cv2.BORDER_REPLICATE.
        4. Return an image whose final size is exactly target W:H.

        Smaller ROIs are enlarged and larger ROIs are reduced. No part of the
        original ROI is cropped, and the image is not stretched.
        """
        if roi is None or roi.size == 0:
            raise RuntimeError(
                'empty roi passed to _bac_keep_ratio_resize_center_pad'
            )

        roi_h, roi_w = roi.shape[:2]
        target_w = max(1, int(target_w))
        target_h = max(1, int(target_h))

        scale = min(
            float(target_w) / float(max(1, roi_w)),
            float(target_h) / float(max(1, roi_h)),
        )

        resized_w = max(
            1,
            min(target_w, int(round(float(roi_w) * scale))),
        )
        resized_h = max(
            1,
            min(target_h, int(round(float(roi_h) * scale))),
        )

        interpolation = cv2.INTER_CUBIC if scale >= 1.0 else cv2.INTER_AREA
        resized = cv2.resize(
            roi,
            (resized_w, resized_h),
            interpolation=interpolation,
        )

        total_pad_x = target_w - resized_w
        total_pad_y = target_h - resized_h

        pad_left = total_pad_x // 2
        pad_right = total_pad_x - pad_left
        pad_top = total_pad_y // 2
        pad_bottom = total_pad_y - pad_top

        padded = cv2.copyMakeBorder(
            resized,
            pad_top,
            pad_bottom,
            pad_left,
            pad_right,
            borderType=cv2.BORDER_REPLICATE,
        )

        engine_h, engine_w = padded.shape[:2]
        if engine_w != target_w or engine_h != target_h:
            raise RuntimeError(
                f'unexpected BAC padded image W:H={engine_w}:{engine_h}; '
                f'expected W:H={target_w}:{target_h}'
            )

        meta = {
            'mode': 'keep_ratio_center_pad',
            'scale': float(scale),
            'original_wh': (int(roi_w), int(roi_h)),
            'resized_wh': (int(resized_w), int(resized_h)),
            'engine_wh': (int(engine_w), int(engine_h)),
            'pad_ltrb': (
                int(pad_left),
                int(pad_top),
                int(pad_right),
                int(pad_bottom),
            ),
        }
        return padded, meta

    def _post_engine(self, payload):
        """POST to inference engine with retry + session re-create.

        IMPORTANT:
        - Never let network exceptions kill the inference thread.
        - Always log full traceback into .log for post-mortem debugging.
        """
        url = self.engine_api_url

        # Keep retries small to avoid blocking the realtime loop forever.
        max_tries = 3
        backoff_s = 0.4
        last_exc = None

        for attempt in range(1, max_tries + 1):
            try:
                resp = self._http_session.post(url, data=payload, timeout=15)
                resp.raise_for_status()

                try:
                    return resp.json()
                except Exception:
                    txt = resp.text.strip()
                    try:
                        return json.loads(txt)
                    except Exception:
                        return ast.literal_eval(txt)

            except Exception as e:
                last_exc = e
                # Full traceback to file
                logger.exception(
                    f"_post_engine failed (attempt {attempt}/{max_tries}), url={url}, err={e}"
                )

                # Re-create session to recover from broken pool/socket.
                try:
                    self._http_session.close()
                except Exception:
                    pass
                self._http_session = requests.Session()

                # Simple backoff before next try.
                time.sleep(backoff_s)
                backoff_s = min(backoff_s * 2, 2.0)

        # Give a stable return shape so caller logic doesn't crash.
        logger.error(f"_post_engine giving up after {max_tries} attempts, last_err={last_exc}")
        return {}

    # ---------------- BJ21 path (original) ----------------
    def _process_frame_bj21(self, frame, gmcode, gmcode_show, frame_id):
        frame_base64 = self._encode_frame_base64(frame)
        payload = {
            'msg': 'Frame from client',
            'imgbase64': frame_base64,
            'img_base64N': len(frame_base64),
            'img_w': frame.shape[1],
            'img_h': frame.shape[0],
            'img_N': frame.size
        }

        start_time = time.time()
        logger.info(f"process_frame[{self.gametype}] before posting, timestamp = {start_time}, url = {self.engine_api_url}")
        rj = self._post_engine(payload)
        end_time = time.time()
        logger.info(f"process_frame[{self.gametype}] posted, timestamp = {end_time}, time_passed = {end_time - start_time}")

        new_card_boxes = []
        group_boxes_dict = {}
        is_card_detected = False
        self.resultlist = []

        group_index_str = rj.get('group_index', '')
        group_text_raw = rj.get('group_text', '')
        if not group_index_str.strip() or not group_text_raw.strip():
            return None, None, False

        try:
            group_indices = [int(x) for x in group_index_str.split(',')]
        except Exception as e:
            logger.info(f"{self.gametype} parse group_index failed: {e}")
            return None, None, False

        group_texts_raw = group_text_raw.split(';')
        group_texts = []
        for gtxt in group_texts_raw:
            cards = gtxt.strip('[]').replace("'", "").split(',')
            group_texts.append([c.strip() for c in cards])

        class_str = rj.get('nClass', '')
        score_str = rj.get('nScore', '')
        onebox_str = rj.get('onebox', '')
        if not class_str.strip() or not score_str.strip() or not onebox_str.strip():
            return None, None, False

        class_list = [int(x) for x in class_str.split(',')]
        score_list = [float(x) for x in score_str.split(',')]
        box_str_list = onebox_str.split(';')
        if not (len(class_list) == len(score_list) == len(box_str_list)):
            logger.info(f"{self.gametype} mismatch lengths nClass/nScore/onebox")
            return None, None, False

        box_list = []
        for bstr in box_str_list:
            vals = list(map(int, bstr.strip("[]").split(',')))
            if len(vals) != 4:
                return None, None, False
            xmin, xmax, ymin, ymax = vals  # engine format
            box_list.append([xmin, ymin, xmax, ymax])

        predicted_cards = []
        for i in range(len(class_list)):
            predicted_cards.append({'classid': class_list[i], 'score': score_list[i], 'box': box_list[i], 'used': False})

        card_groups = {}
        for group_idx, group_cards in zip(group_indices, group_texts):
            group_min_x = group_min_y = group_max_x = group_max_y = None
            group_key = f"group_{group_idx}"
            if group_key not in card_groups:
                card_groups[group_key] = []

            for card_str_val in group_cards:
                try:
                    card_val = int(card_str_val)
                except:
                    continue
                match = None
                for pc in predicted_cards:
                    if not pc['used'] and pc['classid'] == card_val:
                        match = pc
                        break
                if match is None:
                    continue
                match['used'] = True
                x1, y1, x2, y2 = match['box']
                score = match['score']
                card_groups[group_key].append((card_val, score))
                new_card_boxes.append([x1, y1, x2, y2])
                group_min_x = x1 if group_min_x is None else min(group_min_x, x1)
                group_min_y = y1 if group_min_y is None else min(group_min_y, y1)
                group_max_x = x2 if group_max_x is None else max(group_max_x, x2)
                group_max_y = y2 if group_max_y is None else max(group_max_y, y2)

            if group_min_x is not None:
                group_boxes_dict[group_idx] = [group_min_x, group_min_y, group_max_x, group_max_y]

        self.last_detected_group_boxes = group_boxes_dict
        if card_groups:
            self.resultlist.append(card_groups)
            is_card_detected = True

        # Save the full frame we posted to the engine (by gametype)
        try:
            self._save_predict_patch(
                gmcode_show,
                frame_id,         # use frame_id so files don't overwrite
                frame,            # full BGR frame
                predict_classid=0,  # no single class for full-frame; use 0
                score=0.0
            )
        except Exception as e:
            logger.error(f"_save_predict_patch {self.gametype} full-frame failed: {e}")

        return new_card_boxes, group_boxes_dict, is_card_detected

    # ---------------- BAC path (per-index via HTTP) ----------------

    # ---------------- BALL3 path (whole-frame) ----------------
    def _process_frame_ball3(self, frame, gmcode, gmcode_show, frame_id):
        global LAST_BALL3_FRAME, LAST_BALL3_FRAME_META, LAST_BALL3_POST_FRAME, LAST_BALL3_POST_INFO
        # BALL3 frame preprocess (speed focus):
        # Keep PNG (model accuracy). Speed up by using low compression.
        ok, buffer = cv2.imencode(
            '.png',
            frame,
            [int(cv2.IMWRITE_PNG_COMPRESSION), int(self._ball3_png_compression)]
        )
        if not ok:
            raise RuntimeError("cv2.imencode(.png) failed on the current frame")
        frame_base64 = base64.b64encode(buffer).decode('utf-8')
        payload = {
            'msg': 'Frame from client',
            'imgbase64': frame_base64,
            'img_base64N': len(frame_base64),
            'img_w': frame.shape[1],
            'img_h': frame.shape[0],
            'img_N': frame.size
        }

        start_time = time.time()
        logger.info(f"process_frame[BALL3] before posting, timestamp = {start_time}")

        # Cache last frame for STOP images:
        # - LAST_BALL3_FRAME: for big stop image (round_end_imgs)
        # - LAST_BALL3_POST_FRAME/INFO: for ONE predict_images saved at STOP
        try:
            LAST_BALL3_FRAME = frame.copy()
            LAST_BALL3_FRAME_META = {"gmcode": gmcode_show, "seq": int(frame_id), "ts": start_time}
            # POST frame (engine input) will be stamped with class/score after we parse api
            LAST_BALL3_POST_FRAME = frame.copy()
            LAST_BALL3_POST_INFO = {"gmcode": gmcode_show}
        except Exception as e:
            logger.error(f"BALL3 cache last frame failed: {e}")
        api = self._post_engine(payload)
        end_time = time.time()
        logger.info(f"process_frame[BALL3] after posting, time cost = {(end_time - start_time):.3f}s, resp keys={list(api.keys()) if isinstance(api, dict) else type(api)}")

        # Update per-request prediction log for CSV
        try:
            ScanRMgrInstance().update_ball3_predlog(gmcode, api if isinstance(api, dict) else {})
        except Exception as e:
            logger.error(f'BALL3 update_ball3_predlog failed: {e}')

        # Parse nClass / nScore / onebox / group_index
        nclass_raw = api.get('nClass', '') if isinstance(api, dict) else ''
        nscore_raw = api.get('nScore', '') if isinstance(api, dict) else ''
        onebox_raw = api.get('onebox', '') if isinstance(api, dict) else ''
        group_raw  = api.get('group_index', '') if isinstance(api, dict) else ''

        # classes
        if isinstance(nclass_raw, list):
            classes = [str(x).strip() for x in nclass_raw if str(x).strip() != '']
        else:
            classes = [s.strip() for s in str(nclass_raw).split(',') if s.strip()]

        # scores
        if isinstance(nscore_raw, list):
            scores = []
            for x in nscore_raw:
                try:
                    scores.append(float(x))
                except Exception:
                    scores.append(0.0)
        else:
            scores = []
            for s in [t.strip() for t in str(nscore_raw).split(',') if t.strip()]:
                try:
                    scores.append(float(s))
                except Exception:
                    scores.append(0.0)

        # Stamp latest engine-output info for predict_images filename (saved ONLY at STOP)
        try:
            _cid = None
            if classes:
                try:
                    _cid = int(str(classes[0]).strip())
                except Exception:
                    _cid = None
            _sc = float(scores[0]) if scores else 0.0
            _cname = None
            try:
                gt = api.get('group_text') if isinstance(api, dict) else None
                if isinstance(gt, str):
                    gt2 = gt.strip()
                    if gt2:
                        # take first token before comma/space
                        _cname = re.split(r"[\s,;]+", gt2)[0].strip()
            except Exception:
                _cname = None
            if not _cname:
                if _cid == 0:
                    _cname = 'BACK'
                elif _cid == 2:
                    _cname = 'EMPTY'
                elif _cid is None:
                    _cname = 'UNK'
                else:
                    _cname = f'CLS{_cid}'
            LAST_BALL3_POST_INFO.update({'class_id': _cid if _cid is not None else -1, 'score': _sc, 'class_name': _cname})
        except Exception as e:
            logger.error(f'BALL3 stamp LAST_BALL3_POST_INFO failed: {e}')

        # group ids
        if isinstance(group_raw, list):
            group_ids = []
            for x in group_raw:
                try:
                    group_ids.append(int(x))
                except Exception:
                    group_ids.append(0)
        else:
            group_ids = []
            for s in [t.strip() for t in str(group_raw).split(',') if t.strip()]:
                try:
                    group_ids.append(int(s))
                except Exception:
                    group_ids.append(0)

        # onebox: engine seems to output "xmin,xmax,ymin,ymax" per box; separated by ';'
        boxes = []
        if isinstance(onebox_raw, list):
            for b in onebox_raw:
                if isinstance(b, (list, tuple)) and len(b) >= 4:
                    x1, y1, x2, y2 = int(b[0]), int(b[1]), int(b[2]), int(b[3])
                    boxes.append([x1, y1, x2, y2])
        else:
            parts = [p.strip() for p in str(onebox_raw).split(';') if p.strip()]
            for p in parts:
                p2 = p.strip().lstrip('[').rstrip(']')
                nums = [x.strip() for x in p2.split(',') if x.strip()]
                if len(nums) < 4:
                    continue
                try:
                    xmin = int(float(nums[0]))
                    xmax = int(float(nums[1]))
                    ymin = int(float(nums[2]))
                    ymax = int(float(nums[3]))
                except Exception:
                    continue
                x1, y1, x2, y2 = xmin, ymin, xmax, ymax
                if x2 < x1:
                    x1, x2 = x2, x1
                if y2 < y1:
                    y1, y2 = y2, y1
                boxes.append([x1, y1, x2, y2])

        n = min(len(classes), len(boxes)) if boxes else len(classes)
        if len(scores) < n:
            scores += [0.0] * (n - len(scores))
        if len(group_ids) < n:
            # fallback: each detection is its own group if group_index missing/mismatch
            group_ids = list(range(n))

        # Build UI boxes + grouped results for dealer (BJ21-like dict)
        new_card_boxes = []
        group_dict = {}

        for i in range(n):
            cls_str = classes[i]
            try:
                cls_int = int(float(cls_str))
            except Exception:
                # keep as string if not numeric
                cls_int = cls_str

            sc = float(scores[i]) if i < len(scores) else 0.0
            gid = int(group_ids[i]) if i < len(group_ids) else i

            if boxes:
                x1, y1, x2, y2 = boxes[i]
            else:
                x1 = y1 = x2 = y2 = 0

            label = f"{cls_str} ({sc:.2f}) G{gid}"
            new_card_boxes.append({
                'box': (x1, y1, x2, y2),
                'label': label,
                'class': cls_int,
                'score': sc,
                'group': gid,
            })

            group_key = f"group_{gid}"
            group_dict.setdefault(group_key, []).append((cls_int, sc))

            # ------------------------------------------------------------
            # NEW: Extract stable BALL3 result (3 cards) for filename usage
            # ------------------------------------------------------------
            try:
                cards = []
                scores = []

                for gkey in sorted(group_dict.keys()):
                    items = group_dict[gkey]

                    if not items:
                        continue

                    # choose highest score in this group
                    best_cls, best_score = max(items, key=lambda x: x[1])

                    rank = _rank_from_any(best_cls)

                    if rank is None:
                        cards.append("UNK")
                    else:
                        cards.append(str(rank))

                    scores.append(float(best_score))

                # only store when we actually have 3 cards
                if len(cards) == 3:
                    LAST_BALL3_POST_INFO.update({
                        "cards": cards,
                        "scores": scores
                    })

                    logger.info(f"[BALL3 RESULT] cards={cards} scores={scores}")
                    global LAST_BALL3_RESULT_FRAME, LAST_BALL3_RESULT_INFO

                    LAST_BALL3_RESULT_FRAME = frame.copy()

                    LAST_BALL3_RESULT_INFO = {
                        "gmcode": gmcode,
                        "cards": cards.copy(),
                        "scores": scores.copy()
                    }

                    logger.info(f"[BALL3 CACHE] result cached cards={cards}")

                    # Continuously overwrite candidate image (STOP can arrive late)
                    try:
                        save_ball3_candidate_image(gmcode_show, frame, cards, scores)
                    except Exception as e:
                        logger.error(f"[BALL3 CANDIDATE] save failed: {e}")

                    
            except Exception as e:
                logger.error(f"BALL3 extract 3-card result failed: {e}")

        # For BALL3 we stream predictions like BJ21 (immediate forwarding)
        self.resultlist.append(group_dict)

        # group boxes are optional; keep empty dict to avoid breaking drawing
        new_group_boxes = {}
        is_detected = (n > 0)
        return new_card_boxes, new_group_boxes, is_detected


    def _parse_bac_engine_result(self, api, pos, frame_shape, engine_roi_shape=None):
        if not isinstance(api, dict) or not api:
            return None
    
        def _first_scalar(v):
            if v is None:
                return None
            if isinstance(v, (list, tuple)):
                if len(v) == 0:
                    return None
                if isinstance(v[0], (list, tuple)):
                    return v[0][0] if len(v[0]) > 0 else None
                return v[0]
            s = str(v).strip()
            if not s:
                return None
            if ';' in s and not s.startswith('['):
                s = s.split(';')[0].strip()
            if ',' in s and not s.startswith('['):
                s = s.split(',')[0].strip()
            return s
    
        def _parse_score(v):
            x = _first_scalar(v)
            if x is None:
                return None
            try:
                return float(x)
            except Exception:
                return None
    
        def _parse_int(v):
            x = _first_scalar(v)
            if x is None:
                return None
            try:
                return int(float(x))
            except Exception:
                return None
    
        def _parse_label_text(v):
            if v is None:
                return None
            if isinstance(v, (list, tuple)):
                if len(v) == 0:
                    return None
                if isinstance(v[0], (list, tuple)):
                    return str(v[0][0]).strip() if len(v[0]) > 0 else None
                return str(v[0]).strip()
            s = str(v).strip()
            if not s:
                return None
            try:
                parsed = ast.literal_eval(s)
                if isinstance(parsed, (list, tuple)):
                    if len(parsed) == 0:
                        return None
                    if isinstance(parsed[0], (list, tuple)):
                        return str(parsed[0][0]).strip() if len(parsed[0]) > 0 else None
                    return str(parsed[0]).strip()
            except Exception:
                pass
            s = s.strip('[]').replace("'", '').replace('"', '').strip()
            if ',' in s:
                s = s.split(',')[0].strip()
            return s or None
    
        def _parse_onebox(v):
            vals = None
            if v is None:
                return None
            if isinstance(v, (list, tuple)):
                if len(v) >= 4 and not isinstance(v[0], (list, tuple, dict)):
                    vals = list(v[:4])
                elif len(v) > 0 and isinstance(v[0], (list, tuple)) and len(v[0]) >= 4:
                    vals = list(v[0][:4])
            else:
                s = str(v).strip()
                if not s:
                    return None
                if ';' in s:
                    s = s.split(';')[0].strip()
                try:
                    parsed = ast.literal_eval(s)
                    if isinstance(parsed, (list, tuple)) and len(parsed) >= 4:
                        vals = list(parsed[:4])
                except Exception:
                    nums = [x.strip() for x in s.strip('[]').split(',') if x.strip()]
                    if len(nums) >= 4:
                        vals = nums[:4]
            if vals is None:
                return None
            try:
                xmin = int(float(vals[0]))
                xmax = int(float(vals[1]))
                ymin = int(float(vals[2]))
                ymax = int(float(vals[3]))
            except Exception:
                return None
            if xmax < xmin:
                xmin, xmax = xmax, xmin
            if ymax < ymin:
                ymin, ymax = ymax, ymin
            frame_h, frame_w = frame_shape[:2]
            roi_w = max(1, int(pos.xmax - pos.xmin))
            roi_h = max(1, int(pos.ymax - pos.ymin))

            # BAC ROI may be preprocessed before posting to the engine.
            # Supported cases:
            # 1) legacy direct resize: engine_roi_shape is a normal image shape tuple
            # 2) keep-ratio resize: engine_roi_shape is a dict with scale info
            if engine_roi_shape is not None:
                try:
                    if isinstance(engine_roi_shape, dict):
                        mode = str(engine_roi_shape.get('mode', '') or '').strip()
                        engine_w, engine_h = engine_roi_shape.get('engine_wh', (roi_w, roi_h))
                        engine_w = max(1, int(engine_w))
                        engine_h = max(1, int(engine_h))

                        if mode in (
                            'keep_ratio_no_pad',
                            'keep_ratio_center_pad',
                            'letterbox_keep_ratio_blackpad',
                        ):
                            scale = float(engine_roi_shape.get('scale', 1.0) or 1.0)
                            pad_left, pad_top, pad_right, pad_bottom = engine_roi_shape.get('pad_ltrb', (0, 0, 0, 0))
                            pad_left = int(pad_left)
                            pad_top = int(pad_top)
                            if scale > 0:
                                xmin = int(round((xmin - pad_left) / scale))
                                xmax = int(round((xmax - pad_left) / scale))
                                ymin = int(round((ymin - pad_top) / scale))
                                ymax = int(round((ymax - pad_top) / scale))
                        elif engine_w != roi_w or engine_h != roi_h:
                            scale_x = float(roi_w) / float(engine_w)
                            scale_y = float(roi_h) / float(engine_h)
                            xmin = int(round(xmin * scale_x))
                            xmax = int(round(xmax * scale_x))
                            ymin = int(round(ymin * scale_y))
                            ymax = int(round(ymax * scale_y))
                    else:
                        engine_h, engine_w = engine_roi_shape[:2]
                        engine_w = max(1, int(engine_w))
                        engine_h = max(1, int(engine_h))
                        if engine_w != roi_w or engine_h != roi_h:
                            scale_x = float(roi_w) / float(engine_w)
                            scale_y = float(roi_h) / float(engine_h)
                            xmin = int(round(xmin * scale_x))
                            xmax = int(round(xmax * scale_x))
                            ymin = int(round(ymin * scale_y))
                            ymax = int(round(ymax * scale_y))
                except Exception as e:
                    logger.debug(f"BAC onebox coordinate scaling skipped: engine_roi_shape={engine_roi_shape}, err={e}")

            xmin = max(0, min(xmin, roi_w - 1))
            xmax = max(0, min(xmax, roi_w - 1))
            ymin = max(0, min(ymin, roi_h - 1))
            ymax = max(0, min(ymax, roi_h - 1))
            full_xmin = max(0, min(pos.xmin + xmin, frame_w - 1))
            full_xmax = max(0, min(pos.xmin + xmax, frame_w - 1))
            full_ymin = max(0, min(pos.ymin + ymin, frame_h - 1))
            full_ymax = max(0, min(pos.ymin + ymax, frame_h - 1))
            return {'roi_xyxy': [xmin, ymin, xmax, ymax], 'full_xyxy': [full_xmin, full_ymin, full_xmax, full_ymax]}
    
        api_class = _parse_int(api.get('nClass'))
        score = _parse_score(api.get('nScore'))
        box_info = _parse_onebox(api.get('onebox'))
        label_text = _parse_label_text(api.get('group_text'))
        logger.debug(f"BAC parse api_class={api_class}, score={score}, label_text={label_text}, box_info={box_info}, raw_api={api}")
        if api_class is None or score is None:
            return None
        conf_threshold = float(getattr(cfg, 'saveimagescore', 0.85) or 0.85)
        if score < conf_threshold:
            logger.debug(f"BAC parse ignored low confidence: api_class={api_class}, score={score:.4f}, threshold={conf_threshold:.4f}")
            return None
        if api_class in (API_NO_CARD, API_ZERO_CARD):
            return None
        rank_1_to_13 = _api_rank_1_to_13(api_class)
        phbac_id = _api_to_phbac_class(api_class)
        if rank_1_to_13 is None or phbac_id is None:
            logger.debug(f"BAC parse ignored unmappable result: api_class={api_class}, rank_1_to_13={rank_1_to_13}, phbac_id={phbac_id}")
            return None
        if not label_text:
            label_text = str(rank_1_to_13)
        return {
            'api_class': api_class,
            'score': score,
            'rank_1_to_13': rank_1_to_13,
            'phbac_id': phbac_id,
            'label_text': label_text,
            'box_info': box_info,
        }
    
        
    def _process_frame_bac(self, frame, poslist, gmcode, gmcode_show, frame_id):
        """
        BAC path:
        - crop each active ROI from full frame
        - send ROI only to HTTP engine
        - parse single-card result
        - convert to PH_BAC CardInfo
        - feed DataManager
        """
        new_card_boxes = []
        is_card_detected = False
    
        for pos in poslist:
            try:
                if DataMgrInstance().getIsDispatch(gmcode, pos.index):
                    continue
                if not DataMgrInstance().isincurCardList(gmcode, pos.index):
                    continue
    
                roi = frame[pos.ymin:pos.ymax, pos.xmin:pos.xmax]
                if roi is None or roi.size == 0:
                    logger.warning(f"process_frame[BAC] idx={pos.index} empty ROI, skip")
                    continue
    
                roi_for_engine = roi
                roi_h, roi_w = roi.shape[:2]
                resize_applied = False
                preprocess_meta = {
                    'mode': 'identity',
                    'scale': 1.0,
                    'original_wh': (int(roi_w), int(roi_h)),
                    'resized_wh': (int(roi_w), int(roi_h)),
                    'engine_wh': (int(roi_w), int(roi_h)),
                    'pad_ltrb': (0, 0, 0, 0),
                }
                if self.bac_preprocess_resize_enable:
                    if self.bac_preprocess_resize_mode == 'keep_ratio_center_pad':
                        # Crop Tool-compatible mode always preprocesses every BAC ROI.
                        # The final model input is exact resize_target W:H.
                        resize_applied = True
                        roi_for_engine, preprocess_meta = (
                            self._bac_keep_ratio_resize_center_pad(
                                roi,
                                self.bac_preprocess_resize_target_w,
                                self.bac_preprocess_resize_target_h,
                            )
                        )
                    elif self.bac_preprocess_resize_mode == 'keep_ratio_no_pad':
                        # Preserve the old min-size trigger for legacy configs.
                        if (
                            roi_w < self.bac_preprocess_resize_min_w
                            or roi_h < self.bac_preprocess_resize_min_h
                        ):
                            resize_applied = True
                            roi_for_engine, preprocess_meta = (
                                self._bac_keep_ratio_resize_no_pad(
                                    roi,
                                    self.bac_preprocess_resize_target_w,
                                    self.bac_preprocess_resize_target_h,
                                )
                            )
                    else:
                        raise RuntimeError(
                            'unsupported BAC resize_mode: '
                            f'{self.bac_preprocess_resize_mode!r}'
                        )

                engine_h, engine_w = roi_for_engine.shape[:2]
                resized_w, resized_h = preprocess_meta.get('resized_wh', (engine_w, engine_h))
                pad_left, pad_top, pad_right, pad_bottom = preprocess_meta.get('pad_ltrb', (0, 0, 0, 0))
                resize_scale = float(preprocess_meta.get('scale', 1.0) or 1.0)
                resize_mode = str(preprocess_meta.get('mode', 'identity'))
                size_log_key = (
                    gmcode_show,
                    pos.index,
                    roi_w,
                    roi_h,
                    engine_w,
                    engine_h,
                    resize_applied,
                    resize_mode,
                    resized_w,
                    resized_h,
                    pad_left,
                    pad_top,
                    pad_right,
                    pad_bottom,
                    round(resize_scale, 6),
                    self.bac_preprocess_resize_enable,
                    self.bac_preprocess_resize_min_w,
                    self.bac_preprocess_resize_min_h,
                    self.bac_preprocess_resize_target_w,
                    self.bac_preprocess_resize_target_h,
                )
                if size_log_key not in self._bac_preprocess_size_log_cache:
                    self._bac_preprocess_size_log_cache.add(size_log_key)
                    logger.info(
                        f"[BAC_PREPROCESS_SIZE][BEFORE_RESIZE] gmcode={gmcode_show}, frame_id={frame_id}, idx={pos.index}, "
                        f"roi_wh=({roi_w},{roi_h}), roi_shape_hwc={roi.shape}"
                    )
                    logger.info(
                        f"[BAC_PREPROCESS_SIZE][AFTER_RESIZE] gmcode={gmcode_show}, frame_id={frame_id}, idx={pos.index}, "
                        f"resize_enable={self.bac_preprocess_resize_enable}, resize_applied={resize_applied}, "
                        f"resize_mode={resize_mode}, scale={resize_scale:.6f}, "
                        f"resize_min_wh=({self.bac_preprocess_resize_min_w},{self.bac_preprocess_resize_min_h}), "
                        f"resize_target_wh=({self.bac_preprocess_resize_target_w},{self.bac_preprocess_resize_target_h}), "
                        f"resized_wh=({resized_w},{resized_h}), pad_ltrb=({pad_left},{pad_top},{pad_right},{pad_bottom}), "
                        f"engine_wh=({engine_w},{engine_h}), engine_shape_hwc={roi_for_engine.shape}"
                    )

                roi_b64 = self._encode_frame_base64(
                    roi_for_engine,
                    ext='.png',
                    imencode_params=[int(cv2.IMWRITE_PNG_COMPRESSION), 1]
                )
                payload = {
                    'msg': 'Frame from client',
                    'imgbase64': roi_b64,
                    'img_base64N': len(roi_b64),
                    'img_w': roi_for_engine.shape[1],
                    'img_h': roi_for_engine.shape[0],
                    'img_N': roi_for_engine.size,
                }
                if size_log_key not in self._bac_preprocess_payload_log_cache:
                    self._bac_preprocess_payload_log_cache.add(size_log_key)
                    logger.info(
                        f"[BAC_PREPROCESS_SIZE][PAYLOAD] gmcode={gmcode_show}, frame_id={frame_id}, idx={pos.index}, "
                        f"img_w={payload['img_w']}, img_h={payload['img_h']}, img_N={payload['img_N']}, img_base64N={payload['img_base64N']}"
                    )
                t0 = time.time()
                logger.debug(
                    f"process_frame[BAC] before post idx={pos.index}, roi_wh=({roi_w},{roi_h}), engine_wh=({roi_for_engine.shape[1]},{roi_for_engine.shape[0]}), gmcode={gmcode_show}, frame_id={frame_id}, url={self.engine_api_url}"
                )
                api = self._post_engine(payload)
                t1 = time.time()
                logger.debug(f"process_frame[BAC] after post idx={pos.index}, cost={(t1 - t0):.3f}s, api={api}")
    
                parsed = self._parse_bac_engine_result(api, pos, frame.shape, preprocess_meta)
                if parsed is None:
                    continue
                api_class = parsed['api_class']
                score = parsed['score']
                rank_1_to_13 = parsed['rank_1_to_13']
                phbac_id = parsed['phbac_id']
                label_text = parsed['label_text']
                box_info = parsed['box_info']
    
                result = CardInfo(pos.index, phbac_id, api_class, rank_1_to_13, float(score))
                if box_info is not None:
                    rx1, ry1, rx2, ry2 = box_info['roi_xyxy']
                    fx1, fy1, fx2, fy2 = box_info['full_xyxy']
                    result.setAnchor(pos, rx1, ry1, max(1, rx2 - rx1), max(1, ry2 - ry1), f'{label_text}({score:.4f})')
                    new_card_boxes.append([fx1, fy1, fx2, fy2])
    
                self.resultlist.append(result)
                is_card_detected = True
                logger.info(f"process_frame[BAC] accepted idx={pos.index}, gmcode={gmcode_show}, dealer_classid={result.dealer_classid}, predict_classid={result.predict_classid}, card_point={result.card_point}, score={result.score:.4f}")
    
                engine_saved_path = None
                original_saved_path = None
                try:
                    engine_saved_path = self._save_predict_patch(
                        gmcode_show,
                        pos.index,
                        roi_for_engine,
                        predict_classid=api_class,
                        score=score
                    )
                except Exception as e:
                    logger.exception(f'_save_predict_patch BAC engine-input idx={pos.index} failed: {e}')

                if self.save_original_crop:
                    try:
                        original_saved_path = self._save_predict_patch(
                            gmcode_show,
                            pos.index,
                            roi,
                            predict_classid=api_class,
                            score=score,
                            subfolder='original_crop'
                        )
                    except Exception as e:
                        logger.exception(
                            f'_save_predict_patch BAC original-crop '
                            f'idx={pos.index} failed: {e}'
                        )

                logger.info(
                    f"[BAC_PREDICT_IMAGE_SAVE_RESULT] idx={pos.index}, "
                    f"engine_saved_path={engine_saved_path}, "
                    f"save_original_crop={self.save_original_crop}, "
                    f"original_saved_path={original_saved_path}"
                )
            except Exception as e:
                logger.exception(f"process_frame[BAC] idx={getattr(pos, 'index', 'UNK')} failed: {e}")
    
        return new_card_boxes, is_card_detected
    
    
    # ---------------- drawing ----------------
    def display_frame(self, frame, winname, gmcode, gmcode_show, frame_id):
        frame_resized = cv2.resize(frame, (self.resize_width, self.resize_height))
        current_time = time.time()

        # Show gmcode/frame_id
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(frame_resized, f'{gmcode_show}_{frame_id}',
                    (10, 30), font, 1, (255, 255, 255), 2, cv2.LINE_AA)


        # Scale factors
        scale_x = self.resize_width / frame.shape[1]
        scale_y = self.resize_height / frame.shape[0]

        # --- BAC position rectangles (from PH_BAC) ---
        for pos in self.config_poslist:
            xmin = int(pos.xmin * self.resize_width / self.stream_videowidth)
            ymin = int(pos.ymin * self.resize_height / self.stream_videoheight)
            xmax = int(pos.xmax * self.resize_width / self.stream_videowidth)
            ymax = int(pos.ymax * self.resize_height / self.stream_videoheight)

            if DataMgrInstance().getIsDispatch(gmcode, pos.index):
                color = (0, 255, 0)  # green for dispatched
            elif DataMgrInstance().isincurCardList(gmcode, pos.index):
                flicker = int((current_time * 10) % 2)
                color = (0, 255, 255) if flicker else (255, 255, 255)  # yellow/white flicker
            else:
                color = (255, 255, 255)  # white

            cv2.rectangle(frame_resized, (xmin, ymin), (xmax, ymax), color, 2)

        # --- Detection boxes (green) ---
        for item in (self.last_detected_boxes or []):
            xmin = ymin = xmax = ymax = None

            # case A: dict format (BALL3 often uses this)
            if isinstance(item, dict):
                coords = item.get('box') or item.get('onebox')
                if isinstance(coords, (list, tuple)) and len(coords) >= 4:
                    xmin, ymin, xmax, ymax = coords[:4]

            # case B: tuple/list with >= 4 values (e.g. (x1,y1,x2,y2,cls,score))
            elif isinstance(item, (list, tuple)) and len(item) >= 4:
                xmin, ymin, xmax, ymax = item[:4]

            if xmin is None:
                continue

            rxmin = int(xmin * scale_x)
            rymin = int(ymin * scale_y)
            rxmax = int(xmax * scale_x)
            rymax = int(ymax * scale_y)
            cv2.rectangle(frame_resized, (rxmin, rymin), (rxmax, rymax), (0, 255, 0), 2)

        # --- BJ21 group overlays (if any) ---
        overlay = frame_resized.copy()
        alpha = 0.2
        margin = 10
        GROUP_COLORS = [(0, 0, 255), (0, 255, 255), (255, 0, 0), (0, 255, 0), (255, 0, 255)]
        for group_idx in sorted(self.last_detected_group_boxes.keys()):
            (gxmin, gymin, gxmax, gymax) = self.last_detected_group_boxes[group_idx]
            color = GROUP_COLORS[group_idx % len(GROUP_COLORS)]
            rgxmin = max(int(gxmin * scale_x) - margin, 0)
            rgymin = max(int(gymin * scale_y) - margin, 0)
            rgxmax = min(int(gxmax * scale_x) + margin, self.resize_width)
            rgymax = min(int(gymax * scale_y) + margin, self.resize_height)
            cv2.rectangle(overlay, (rgxmin, rgymin), (rgxmax, rgymax), color, -1)
            cv2.rectangle(frame_resized, (rgxmin, rgymin), (rgxmax, rgymax), color, 4)
            label_text = "Dealer" if group_idx == 0 else f"Player {group_idx}"
            cv2.putText(frame_resized, label_text,
                        (rgxmin, max(rgymin - 5, 0)),
                        font, 0.9, color, 2, cv2.LINE_AA)
        cv2.addWeighted(overlay, alpha, frame_resized, 1 - alpha, 0, frame_resized)

        cv2.imshow(winname, frame_resized)

    def rotate_frame(self, frame, angle):
        (h, w) = frame.shape[:2]
        center = (w // 2, h // 2)
        rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(frame, rotation_matrix, (w, h))

    def save_full_img(self, gmcode, frame, gmcode_show):
        strgmcode = gmcode_show
        fmt_str = '%s' % strgmcode

        if not os.path.exists(self.auditDir):
            os.makedirs(self.auditDir, exist_ok=True)

        filename = fmt_str + '.jpg'
        filepath = os.path.join(self.auditDir, filename)
        logger.info(f'write full image, image file path ={filepath}')

        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(frame, f'{gmcode_show}', (10, 30), font, 1, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.imwrite(filepath, frame)
        return filename, filepath
