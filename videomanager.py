# encoding=utf-8

import cv2
import numpy as np
from cardinfo import CardInfo, GetCardVal
from datamanager import DataMgrInstance
from scanresultsave import ScanRMgrInstance
import pylogger as logger
from twisted.internet import reactor
import time
from skimage.metrics import structural_similarity as compare_ssim # tf2.1
from config import cfg
import subprocess

# 20241025 add a button for manual predict process
import tkinter as tk
from tkinter import Button
# Add this line to start the Tkinter UI inside Twisted's event loop
from twisted.internet import tksupport
# 20241029 put imageSaver code in here
import datetime as d
import os
import sys
# 20250103 implement http_post_api
import base64
import requests
import json

class VideoManager(object):
    def __init__(self, gametype, stream, videowidth, videoheight, poslist, dealer,
                 imageSaver, onelabel, freq, tilt_angle, save_predictions, save_full_image,
                 savedir, window_resize_width=640, window_resize_height=480):
        """
        This VideoManager merges the old stable version with the new grouped detection logic.
        We preserve older logs and comments from the original code.
        """
        self.gametype = gametype
        self.stream = stream
        self.config_videowidth = videowidth
        self.config_videoheight = videoheight
        self.config_poslist = poslist
        self.dealer = dealer
        self.imageSaver = imageSaver
        self.onelabel = onelabel
        self.config_freq = freq
        self.skip_freq = 120
        self.resultlist = []
        self.stopRun = False
        self.isExit = False
        self.resize_width = window_resize_width
        self.resize_height = window_resize_height
        # 20240926 tilt_angle
        self.tilt_angle = tilt_angle
        # pause mechanic
        self.paused = False  # Track pause/play state
        self.last_click_time = 0  # Track time of last click to detect double-click
        # 20241025 add a button for manual predict process
        self.use_manual_flag = False  # Track if manual predictFlag is being used
        self.predictFlag_manual = False  # Custom flag to control prediction
        self.root = None
        # 20241025 toggle save predictions(I/O save to local disk)
        self.save_predictions = save_predictions
        self.save_full_image = save_full_image
        # 20241029 imageSaver
        self.auditDir = savedir
        # 20250703 add url for pydealerLight
        self.engine_api_url = cfg.engine_api_url

        # DataMgr registers
        DataMgrInstance().setgametype(gametype)
        DataMgrInstance().register_ImageSaver(imageSaver)
        # 20240926 / 20241122: we use dealer's callback for sending results
        DataMgrInstance().register_senddata(dealer.sendPredictResult)

        # 202412xx: Keep bounding boxes across frames
        # last_detected_boxes = list of per-card bounding boxes [x1,y1,x2,y2]
        # last_detected_group_boxes = list of bigger group bounding boxes [gx1,gy1,gx2,gy2]
        self.last_detected_boxes = []
        self.last_detected_group_boxes = {}

    def setup_ui(self):
        """
        20241025: Set up Tkinter UI with a button to toggle the prediction process.
        (Optional - can be commented if no GUI needed.)
        """
        self.root = tk.Tk()
        self.root.title("Prediction Control")
        # Initial button to ask if user wants to use manual predictFlag
        self.initial_manual_button = Button(self.root, text="Use manual predictFlag?",
                                            command=self.set_manual_flag)
        self.initial_manual_button.pack()

    def set_manual_flag(self):
        """
        20241025: set the manual prediction flag, remove the initial button,
        and create a toggle button for manual prediction.
        """
        self.use_manual_flag = True
        logger.info('User chose to use manual predictFlag.')
        # Remove initial button and create a toggle button
        self.initial_manual_button.destroy()
        self.toggle_button = Button(self.root, text="Start Prediction", command=self.toggle_prediction)
        self.toggle_button.pack()

    def toggle_prediction(self):
        """
        20241025: Toggle the prediction flag when the button is clicked.
        """
        self.predictFlag_manual = not self.predictFlag_manual
        if self.predictFlag_manual:
            self.toggle_button.config(text="Stop Prediction")
            logger.info('Prediction started manually.')
        else:
            self.toggle_button.config(text="Start Prediction")
            logger.info('Prediction stopped manually.')

    def mouse_callback(self, event, x, y, flags, param):
        """
        20241025: Detect double-click to pause/resume.
        """
        if event == cv2.EVENT_LBUTTONDBLCLK:
            self.toggle_pause_resume()

    def toggle_pause_resume(self):
        """
        Toggle between pausing and resuming the video processing.
        """
        if self.paused:
            self.paused = False
            logger.info('Resuming video and processes...')
        else:
            self.paused = True
            logger.info('Pausing video and processes...')

    def start(self):
        """
        Start the video processing in a separate thread, integrated with Twisted (if root UI used).
        """
        if self.root:
            tksupport.install(self.root)
        reactor.callInThread(self.run)

    def run(self):
        """
        This loop ensures continuous video processing until stopRun is True.
        """
        playVideoCount = 0
        while not self.stopRun:
            ifopenVideo = self.playVideo(self.stream, self.config_poslist)
            if self.isExit or not ifopenVideo:
                self.cleanup(playVideoCount)
                break

    def cleanup(self, playVideoCount):
        """
        Cleanup resources and stop the reactor when the video processing is done or fails.
        """
        if playVideoCount > 20:
            logger.info(f'openVideo failed, exit after {playVideoCount} attempts')
        self.stopRun = True
        cv2.destroyAllWindows()
        self.imageSaver.stop()
        reactor.callFromThread(reactor.stop)
        if self.root:
            self.root.quit()

    def camera_check(self, cap):
        """
        20241025: Check if the camera is operational by comparing a test frame with an error template.
        """
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
        """
        20241025: Adjust settings for camera capture if the input is a live video feed (e.g., from a camera).
        """
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
            logger.info(f"cv2.CAP_PROP_FRAME_WIDTH set to : {stream_width}, "
                        f"cv2.CAP_PROP_FRAME_HEIGHT set to : {stream_height}")

            if self.camera_check(cap):
                break
            counter += 1

    def playVideo(self, videoname, poslist):
        """
        Opens the video stream, reads frames, and processes them.  
        Incorporates pausing/resuming & new grouping detection logic.

        20250103: We also do the skip_freq logic. If a frame is processed with detection, we store the bounding boxes.
        Otherwise, we keep old bounding boxes so they remain on screen (no flashing).
        """
        logger.info(f'Starting video stream: {videoname}')
        cap = cv2.VideoCapture(videoname)

        self.stream_videowidth = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        self.stream_videoheight = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)

        # 20241024 / 20241122: check resolution matches config
        if self.config_videowidth != self.stream_videowidth:
            logger.info(f"WARNING : config videowidth is {self.config_videowidth}, but the stream videowidth is {self.stream_videowidth}, exit program")
            reactor.callFromThread(reactor.stop)
            self.isExit = True
            raise ValueError('config videowidth and stream videowidth mismatch')
                          
            # # 20241024 config裡的解析度是當初crop_tool抓取的影片的解析度，因此pos_list解析度也應做同樣的調整
            # logger.info(f"WARNING : config videowidth is {self.config_videowidth}, but the stream videowidth is {self.stream_videowidth}, use stream videowidth instead")
            # # Calculate the rectangle coordinates based on the real frame
            # for pos in poslist:
            #     pos.xmin = int(pos.xmin * self.stream_videowidth / self.config_videowidth)
            #     pos.xmax = int(pos.xmax * self.stream_videowidth / self.config_videowidth)

        if self.config_videoheight != self.stream_videoheight:
            logger.info(f"WARNING : config videoheight is {self.config_videoheight}, but the stream videoheight is {self.stream_videoheight}, exit program")
            reactor.callFromThread(reactor.stop)
            self.isExit = True
            raise ValueError('config videoheight and stream videoheight mismatch')

            # # 20241024 config裡的解析度是當初crop_tool抓取的影片的解析度，因此pos_list解析度也應做同樣的調整
            # logger.info(f"WARNING : config videoheight is {self.config_videoheight}, but the stream videoheight is {self.stream_videoheight}, use stream videoheight instead")
            # # Calculate the rectangle coordinates based on the real frame
            # for pos in poslist:
            #     pos.ymin = int(pos.ymin * self.stream_videoheight / self.config_videoheight)
            #     pos.ymax = int(pos.ymax * self.stream_videoheight / self.config_videoheight)
        if isinstance(videoname, int):
            self.adjust_capture_settings(cap)

        if not cap.isOpened():
            logger.info('cap.isOpened() failed')
            return False

        nframe = 0
        frame_id = 0
        skip_freq = self.skip_freq
        winname = 'pydealerclientLight_v20250703'
        cv2.namedWindow(winname)
        cv2.setMouseCallback(winname, self.mouse_callback)

        while True:
            if not self.paused:
                ret, frame = cap.read()
                frame_id += 1
                if not ret or frame is None:
                    logger.info('Failed to read frame from video')
                    continue

                # Rotate the frame based on self.tilt_angle
                if self.tilt_angle != 0:
                    frame = self.rotate_frame(frame, self.tilt_angle)

                # Process and display frame
                predictFlag = DataMgrInstance().getPredictFlag()
                gmcode = DataMgrInstance().getGamecode()
                gmcode_show = gmcode
                if isinstance(gmcode, bytes):
                    gmcode_show = gmcode.decode('utf-8').rstrip('\x00')

                nframe += 1
                isDetect = (nframe >= skip_freq)

                # Decide if we want to run detection this frame
                if isDetect:
                    nframe = 0  # reset the skip counter

                # 20241025: if using manual mode, override predictFlag
                if self.use_manual_flag:
                    predictFlag = self.predictFlag_manual
                else:
                    predictFlag = DataMgrInstance().getPredictFlag()

                # We'll store newly-detected boxes so we can keep them on screen
                new_card_boxes = None
                new_group_boxes = None
                is_card_detected = False

                if predictFlag and gmcode and isDetect:
                    # Clear self.resultlist for new detection
                    self.resultlist = []
                    # We run the new grouping detection
                    new_card_boxes, new_group_boxes, is_card_detected = self.process_frame(
                        frame, poslist, gmcode, gmcode_show, frame_id
                    )
                    # If detection produced new boxes, store them
                    if new_card_boxes is not None:
                        self.last_detected_boxes = new_card_boxes
                    if new_group_boxes is not None:
                        self.last_detected_group_boxes = new_group_boxes

                    if len(self.resultlist) > 0:
                        DataMgrInstance().addResultlist(gmcode, self.resultlist)

                    # Adjust skip frequency if a card was detected
                    if is_card_detected:
                        skip_freq = self.config_freq
                        # Possibly save full image
                        if self.save_full_image:
                            last_frame = frame.copy()
                            self.save_full_img(gmcode, last_frame, gmcode_show)
                    else:
                        skip_freq = self.skip_freq

                # 20241114: display frame + bounding boxes
                self.display_frame(frame, winname, gmcode, gmcode_show, frame_id)


            key = cv2.waitKey(1)
            if key & 0xFF == ord('q') or cv2.getWindowProperty(winname, cv2.WND_PROP_AUTOSIZE) < 1:
                self.stopRun = True
                logger.error('Exiting...')
                cv2.destroyAllWindows()
                reactor.callFromThread(reactor.stop)
                self.isExit = True
                break

        if cap.isOpened():
            cap.release()
        return True

    def process_frame(self, frame, poslist, gmcode, gmcode_show, frame_id):
        """
        Runs the new grouping-based detection approach, searching for repeated classes
        in the order the engine returned them, and handles no detections gracefully
        (returning None, None, False if group_index or group_text is empty).

        Returns:
        (new_card_boxes, new_group_boxes, is_card_detected)
            - new_card_boxes: [ [xmin,ymin,xmax,ymax], ... ] for each card
            - new_group_boxes: [ [gxmin,gymin,gxmax,gymax], ... ] for each group
            - is_card_detected: bool
        """
        # 1) Encode frame as base64 for HTTP request
        _, buffer = cv2.imencode('.jpg', frame)
        frame_base64 = base64.b64encode(buffer).decode('utf-8')
        img_base64N = len(frame_base64)

        payload = {
            'msg': 'Frame from client',
            'imgbase64': frame_base64,
            'img_base64N': img_base64N,
            'img_w': frame.shape[1],
            'img_h': frame.shape[0],
            'img_N': frame.size
        }

        start_time = time.time()
        logger.info(f"process_frame before posting, timestamp = {start_time}, url = {self.engine_api_url}")

        # engine_predict_URL = f"{cfg.engine_url}{cfg.engine_endpoint}"
        engine_predict_URL = self.engine_api_url
        response = requests.post(engine_predict_URL, data=payload)

        end_time = time.time()
        logger.info(f"process_frame posted, timestamp = {end_time}, time_passed = {end_time - start_time}")

        # Prepare outputs
        new_card_boxes = []
        group_boxes_dict = {}
        is_card_detected = False

        # Always clear self.resultlist before filling with new results
        self.resultlist = []

        if response.status_code != 200:
            logger.info(f"Failed to send frame. Status code: {response.status_code}")
            return None, None, False

        # Convert response to JSON
        resp_json = response.json()
        logger.info(f"Response from engine: {resp_json}")

        # 2) Check for no detection
        group_index_str = resp_json.get('group_index', '')
        if not group_index_str.strip():
            logger.info("Empty group_index => no detection => skip frame")
            return None, None, False

        group_text_raw = resp_json.get('group_text', '')
        if not group_text_raw.strip():
            logger.info("Empty group_text => no detection => skip frame")
            return None, None, False

        # 3) Parse group_index, group_text safely
        try:
            group_indices = [int(x) for x in group_index_str.split(',')]
        except ValueError as e:
            logger.info(f"Error parsing group_index: {e}")
            return None, None, False

        group_texts_raw = group_text_raw.split(';')
        group_texts = []
        for gtxt in group_texts_raw:
            # Remove brackets/quotes => split by comma => strip each
            cards = gtxt.strip('[]').replace("'", "").split(',')
            group_texts.append([c.strip() for c in cards])

        # 4) Parse nClass, nScore, onebox
        class_str = resp_json.get('nClass', '')
        score_str = resp_json.get('nScore', '')
        onebox_str = resp_json.get('onebox', '')
        is_card_detected = True

        # If they're empty, we skip
        if not class_str.strip() or not score_str.strip() or not onebox_str.strip():
            logger.info("Empty nClass/nScore/onebox => no detection => skip frame")
            return None, None, False

        class_list = [int(x) for x in class_str.split(',')]
        score_list = [float(x) for x in score_str.split(',')]
        box_str_list = onebox_str.split(';')

        # Ensure all lists are same length
        if not (len(class_list) == len(score_list) == len(box_str_list)):
            logger.warning("Mismatch in lengths of nClass, nScore, and onebox => partial detection => skip frame")
            return None, None, False

        # Convert each onebox string into [xmin,ymin,xmax,ymax]
        box_list = []
        for bstr in box_str_list:
            vals = list(map(int, bstr.strip("[]").split(',')))
            if len(vals) != 4:
                logger.warning(f"One of the boxes doesn't have exactly 4 coords => skip: {vals}")
                return None, None, False
            # Engine returns [xmin, xmax, ymin, ymax], reorder them into (xmin,ymin,xmax,ymax)
            xmin = vals[0]
            xmax = vals[1]
            ymin = vals[2]
            ymax = vals[3]
            box_list.append([xmin, ymin, xmax, ymax])

        # 5) Make a list of predicted_cards in the exact engine order, so we can handle duplicates
        predicted_cards = []
        for i in range(len(class_list)):
            predicted_cards.append({
                'classid': class_list[i],
                'score': score_list[i],
                'box': box_list[i],
                'used': False
            })

        # Initialize card_groups if not already done (at start of process_frame)
        card_groups = {}

        # 6) For each group, find the needed cards in predicted_cards (in order)
        for group_idx, group_cards in zip(group_indices, group_texts):
            group_min_x = None
            group_min_y = None
            group_max_x = None
            group_max_y = None

            # Initialize this group's list if not already present
            group_key = f"group_{group_idx}"
            if group_key not in card_groups:
                card_groups[group_key] = []

            for card_str_val in group_cards:
                # parse e.g. '8' -> int(8)
                card_val = int(card_str_val)

                # find first unused predicted card with classid == card_val
                match = None
                for pc in predicted_cards:
                    if not pc['used'] and pc['classid'] == card_val:
                        match = pc
                        break

                if match is None:
                    logger.warning(f"No predicted card found for val={card_val}. Possibly engine mismatch.")
                    continue

                # Mark used
                match['used'] = True

                # Extract bounding box and score
                x1, y1, x2, y2 = match['box']
                score = match['score']
                classid = match['classid']

                # Add this card's value and score to its group's list, preserving order
                card_groups[group_key].append((card_val, score))

                # Store for bounding box draw
                new_card_boxes.append([x1, y1, x2, y2])

                # Expand group bounding box
                if group_min_x is None or x1 < group_min_x:
                    group_min_x = x1
                if group_min_y is None or y1 < group_min_y:
                    group_min_y = y1
                if group_max_x is None or x2 > group_max_x:
                    group_max_x = x2
                if group_max_y is None or y2 > group_max_y:
                    group_max_y = y2

            # Done assigning cards in this group; store group box if valid
            if group_min_x is not None:
                group_boxes_dict[group_idx] = [group_min_x, group_min_y, group_max_x, group_max_y]

        # Finally:
        self.last_detected_group_boxes = group_boxes_dict

        # After all groups are processed, add card_groups to resultlist
        if card_groups:
            self.resultlist.append(card_groups)
            logger.info(f"Added card groups to resultlist: {card_groups}")


        return new_card_boxes, group_boxes_dict, is_card_detected

    def display_frame(self, frame, winname, gmcode, gmcode_show, frame_id):
        frame_resized = cv2.resize(frame, (self.resize_width, self.resize_height))
        
        # Show gmcode/frame_id
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(frame_resized, f'{gmcode_show}_{frame_id}',
                    (10, 30), font, 1, (255, 255, 255), 2, cv2.LINE_AA)
        
        # Scale factors
        scale_x = self.resize_width / frame.shape[1]
        scale_y = self.resize_height / frame.shape[0]

        # 1) Draw each card bounding box in green
        for (xmin, ymin, xmax, ymax) in self.last_detected_boxes:
            rxmin = int(xmin * scale_x)
            rymin = int(ymin * scale_y)
            rxmax = int(xmax * scale_x)
            rymax = int(ymax * scale_y)
            cv2.rectangle(frame_resized, (rxmin, rymin), (rxmax, rymax), (0, 255, 0), 2)

        # 2) Prepare overlay for group boxes
        overlay = frame_resized.copy()
        alpha = 0.2
        margin = 10

        # We can define a color array. We'll pick color by group_idx % len(colors).
        GROUP_COLORS = [
            (0, 0, 255),    # Red
            (0, 255, 255),  # Yellow
            (255, 0, 0),    # Blue
            (0, 255, 0),    # Green
            (255, 0, 255)   # Magenta
        ]

        # 3) Now iterate group boxes in sorted order of group_idx
        for group_idx in sorted(self.last_detected_group_boxes.keys()):
            (gxmin, gymin, gxmax, gymax) = self.last_detected_group_boxes[group_idx]

            # Pick a color
            color = GROUP_COLORS[group_idx % len(GROUP_COLORS)]

            # Scale + margin
            rgxmin = int(gxmin * scale_x) - margin
            rgymin = int(gymin * scale_y) - margin
            rgxmax = int(gxmax * scale_x) + margin
            rgymax = int(gymax * scale_y) + margin

            # Clamp
            if rgxmin < 0: rgxmin = 0
            if rgymin < 0: rgymin = 0
            if rgxmax > self.resize_width: rgxmax = self.resize_width
            if rgymax > self.resize_height: rgymax = self.resize_height

            # Fill
            cv2.rectangle(overlay, (rgxmin, rgymin), (rgxmax, rgymax), color, -1)

            # Outline
            cv2.rectangle(frame_resized, (rgxmin, rgymin), (rgxmax, rgymax), color, 4)

            # Label
            if group_idx == 0:
                label_text = "Dealer"
            else:
                label_text = f"Player {group_idx}"

            cv2.putText(frame_resized, label_text,
                        (rgxmin, max(rgymin - 5, 0)),
                        font, 0.9, color, 2, cv2.LINE_AA)

        # 4) Blend overlay
        cv2.addWeighted(overlay, alpha, frame_resized, 1 - alpha, 0, frame_resized)

        cv2.imshow(winname, frame_resized)

    def rotate_frame(self, frame, angle):
        """
        20240926: Rotate the given frame by the specified angle (from config).
        """
        (h, w) = frame.shape[:2]
        center = (w // 2, h // 2)
        rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(frame, rotation_matrix, (w, h))

    def save_full_img(self, gmcode, frame, gmcode_show):
        """
        20241029: Draw the best result on the frame and save to local img (big picture).
        20250103: Overwrite each time with the same gmcode name or do timestamp if needed.
        """
        strgmcode = gmcode_show
        fmt_str = '%s' % strgmcode

        if not os.path.exists(self.auditDir):
            os.makedirs(self.auditDir)

        # Generate filename based on gmcode
        filename = fmt_str + '.jpg'
        filepath = os.path.join(self.auditDir, filename)
        logger.info('write full image, image file path =%s' % (filepath))

        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 1
        font_color = (255, 255, 255)
        thickness = 2
        position = (10, 30)
        cv2.putText(frame, f'{gmcode_show}', position, font, font_scale, font_color, thickness, cv2.LINE_AA)
        cv2.imwrite(filepath, frame)

        return filename, filepath