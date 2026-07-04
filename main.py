# encoding=utf-8
import os
import sys
import threading
import traceback
import xml.etree.ElementTree as ET

from twisted.internet import reactor

import pylogger as logger
from ball3_http_service import start_ball3_http_service, register_ball3_callbacks
from config import cfg
from dealerclient import DealerClient
from videomanager import VideoManager

VERSION = '1.0.6-BAC'


def _runtime_root():
    try:
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        return os.getcwd()
    except Exception:
        return os.getcwd()


if __name__ == '__main__':
    def _sys_excepthook(exctype, value, tb):
        try:
            logger.error(
                "Uncaught exception (sys.excepthook)\n" + ''.join(traceback.format_exception(exctype, value, tb))
            )
        except Exception:
            pass

    sys.excepthook = _sys_excepthook

    if hasattr(threading, 'excepthook'):
        def _thread_excepthook(args):
            try:
                logger.error(
                    "Uncaught exception (threading.excepthook)\n"
                    + ''.join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
                )
            except Exception:
                pass
        threading.excepthook = _thread_excepthook

    try:
        ver_path = os.path.join(_runtime_root(), 'version.txt')
        if os.path.exists(ver_path):
            with open(ver_path, 'r', encoding='utf-8') as vf:
                logger.info(f'[VERSION] {vf.read().strip()}')
    except Exception as e:
        logger.warning(f'[VERSION] failed to read version.txt: {e}')

    logger.info('detect v%s starting...' % VERSION)
    logger.info(
        f'[RUNTIME CONFIG] vid={cfg.vid}, gametype={cfg.gametype}, stream={cfg.stream}, '
        f'position_file={cfg.position_filename}, engine_api_url={getattr(cfg, "engine_api_url", "")}'
    )
    reactor.suggestThreadPoolSize(8)

    dealer = DealerClient(cfg.dealer_host, cfg.dealer_port, cfg.dealer_id)
    try:
        register_ball3_callbacks(
            dealer.onStartPredict,
            dealer.onStopPredict,
            dealer.onDispatchCard,
            dealer.onSaveFinalResult,
        )
        logger.info('BALL3 HTTP callbacks registered.')
    except Exception as e:
        logger.error(f'Failed to register BALL3 HTTP callbacks: {e}')

    imageSaver = None

    def _read_save_predict_image_cfg(xml_path='config.xml'):
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            node = root.find('./savePredictImage') or root.find('.//savePredictImage')
            folder = './predict_images'
            enabled = False
            if node is not None:
                folder = node.get('folder', folder)
                enabled = node.get('enable', '0').strip() in ('1', 'true', 'True')
            logger.info(f'read_save_predict_image_cfg, enable={enabled}, folder={folder}')
            if enabled:
                os.makedirs(folder, exist_ok=True)
            return enabled, folder
        except Exception as e:
            logger.error(f'read savePredictImage from {xml_path} failed: {e}')
            return False, './predict_images'

    save_predictions, save_predict_folder = _read_save_predict_image_cfg()
    save_full_image = int(cfg.save_auto_upload)

    videoMgr = VideoManager(
        cfg.gametype,
        cfg.stream,
        cfg.videowidth,
        cfg.videoheight,
        cfg.pos_list,
        dealer,
        imageSaver,
        cfg.onelabel,
        cfg.freq,
        cfg.tilt_angle,
        save_predictions,
        save_full_image,
        cfg.save_folder,
        save_predict_folder,
        cfg.skip_freq,
    )
    videoMgr.start()

    try:
        http_thread = threading.Thread(
            target=start_ball3_http_service,
            kwargs={'http_port': cfg.http_port, 'https_port': cfg.https_port},
            name='ball3_http_service',
            daemon=True,
        )
        http_thread.start()
        logger.info('BALL3 HTTP service started (threaded).')
    except Exception as e:
        logger.error(f'Failed to start BALL3 HTTP service: {e}')

    reactor.run()
    sys.exit(0)
