# encoding=utf-8
from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime

import pylogger as logger
from csvtool import tocsv, LEGACY_HEADER

BALL3_HEADER = [
    "round_id",
    "end_time",
    "region_A",
    "region_J",
    "region_Q",
    "region_K",
    "region_9",
    "region_10",
    "model_prediction_log",
]


_BALL3_ROUND_RE = re.compile(r"^(Ball3_\d{8}(?:[_-]\d+)?)(?:[_-]\d+)*$")


def _decode_gmcode(gmcode) -> str:
    if isinstance(gmcode, (tuple, list)):
        if not gmcode:
            return ""
        gmcode = gmcode[0]
    if isinstance(gmcode, (bytes, bytearray)):
        return gmcode.decode("utf-8", errors="ignore").strip("\x00")
    return str(gmcode).strip("\x00")


def _ball3_round_id(gm: str) -> str:
    gm = (gm or "").replace("\x00", "").strip()
    m = _BALL3_ROUND_RE.match(gm)
    if m:
        s = m.group(1)
        return "Ball3_" + s[6:]
    return gm


def _ball3_to_region_label(v):
    if isinstance(v, str):
        s = v.strip().upper()
        if s in ("A", "J", "Q", "K", "9", "10"):
            return s
        if s.isdigit():
            try:
                return _ball3_to_region_label(int(s))
            except Exception:
                return None
        return None
    if isinstance(v, (int, float)):
        n = int(v)
        return {1: "A", 9: "9", 10: "10", 11: "J", 12: "Q", 13: "K"}.get(n)
    return None


def _extract_ball3_regions_from_groups(groups_dict: dict):
    if not isinstance(groups_dict, dict):
        return None
    regions = []
    for gname in sorted(groups_dict.keys()):
        items = groups_dict.get(gname) or []
        if not items:
            return None
        first = items[0]
        if not isinstance(first, (tuple, list)) or len(first) < 1:
            return None
        r = _ball3_to_region_label(first[0])
        if r is None:
            return None
        regions.append(r)
    return regions if len(regions) == 3 else None


def _regions_to_counts(regions):
    counts = {"A": 0, "J": 0, "Q": 0, "K": 0, "9": 0, "10": 0}
    for r in regions:
        if r in counts:
            counts[r] += 1
    return counts


class ScanResultManager:
    def __init__(self):
        self.session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.csv_root = os.path.join(os.getcwd(), "csv")
        self.date_folder = datetime.now().strftime("%Y-%m-%d")
        self.csv_dir = os.path.join(self.csv_root, self.date_folder)
        os.makedirs(self.csv_dir, exist_ok=True)

        self.ball3_csv_path = None
        self.legacy_session_csv_path = None

        self.ball3_latest_regions_by_gmcode = {}
        self.ball3_predlog_by_gmcode = {}

        self._legacy_scan_rows_by_gmcode = {}
        self._legacy_final_rows_by_gmcode = {}
        self._legacy_final_saved_gmcodes = set()

    def _ensure_ball3_csv_ready(self):
        if not self.ball3_csv_path:
            self.ball3_csv_path = os.path.join(self.csv_dir, f"{self.session_ts}.csv")
        if not os.path.exists(self.ball3_csv_path) or os.path.getsize(self.ball3_csv_path) == 0:
            with open(self.ball3_csv_path, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow(BALL3_HEADER)

    def _ensure_legacy_session_csv_ready(self):
        if not self.legacy_session_csv_path:
            self.legacy_session_csv_path = os.path.join(self.csv_dir, f"{self.session_ts}.csv")
        if not os.path.exists(self.legacy_session_csv_path) or os.path.getsize(self.legacy_session_csv_path) == 0:
            with open(self.legacy_session_csv_path, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow(LEGACY_HEADER)

    def _append_legacy_session_rows(self, rows):
        if not rows:
            return
        self._ensure_legacy_session_csv_ready()
        with open(self.legacy_session_csv_path, 'a', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerows(rows)
            f.flush()

    def update_ball3_predlog(self, gmcode, api: dict):
        try:
            gm = _ball3_round_id(_decode_gmcode(gmcode))
            lst = self.ball3_predlog_by_gmcode.setdefault(gm, [])
            item = {
                'ts': datetime.now().strftime('%H:%M:%S.%f')[:-3],
                'Cost_time': api.get('Cost_time'),
                'Counts': api.get('Counts'),
                'group_text': api.get('group_text'),
                'nClass': api.get('nClass'),
                'nScore': api.get('nScore'),
            }
            lst.append(item)
            if len(lst) > 300:
                del lst[:50]
        except Exception as e:
            logger.error(f'update_ball3_predlog failed: {e}')

    def saveScanResult(self, gmcode, index: int, cardVal: int):
        gm = _decode_gmcode(gmcode)
        row = [gm, index, 0, 0, 1.0, cardVal, 0]
        self._legacy_scan_rows_by_gmcode.setdefault(gm, []).append(row)

    def saveFinaDeclareResult(self, gmcode, resultlist):
        gm = _decode_gmcode(gmcode)
        row_map = self._legacy_final_rows_by_gmcode.setdefault(gm, {})
        for res in resultlist:
            row_map[int(res.index)] = [
                gm,
                int(res.index),
                int(res.dealer_classid),
                int(res.predict_classid),
                float(res.score),
                int(res.card_point),
                0,
            ]
        if row_map:
            self._legacy_final_saved_gmcodes.discard(gm)
            logger.info(f'saveFinaDeclareResult: cached {len(row_map)} BAC final rows for gmcode={gm}')

    def saveFinaDeclareResultNoLock(self, gmcode, resultlist):
        self.saveFinaDeclareResult(gmcode, resultlist)

    def HasPendingFinalResult(self, gmcode):
        gm = _decode_gmcode(gmcode)
        if gm in self._legacy_final_saved_gmcodes:
            return False
        return bool(self._legacy_final_rows_by_gmcode.get(gm))

    def SaveFinalResult(self, gmcode):
        gm = _decode_gmcode(gmcode)
        rows_map = self._legacy_final_rows_by_gmcode.get(gm, {})
        rows = [rows_map[k] for k in sorted(rows_map.keys())] if rows_map else []
        if not rows:
            logger.warning(f'SaveFinalResult: no cached BAC final rows for gmcode={gm}, fallback to scan rows')
            rows = self._legacy_scan_rows_by_gmcode.get(gm, [])
        if not rows:
            logger.warning(f'SaveFinalResult: nothing to write for gmcode={gm}')
            return
        tocsv(rows, isFinalResult=True)
        self._append_legacy_session_rows(rows)
        self._legacy_final_saved_gmcodes.add(gm)
        logger.info(f'SaveFinalResult: wrote {len(rows)} final rows for gmcode={gm}')
        self.clearCardMap(gmcode)

    def clearCardMap(self, gmcode):
        gm = _decode_gmcode(gmcode)
        self._legacy_scan_rows_by_gmcode.pop(gm, None)
        self._legacy_final_rows_by_gmcode.pop(gm, None)
        self.ball3_latest_regions_by_gmcode.pop(gm, None)
        self.ball3_predlog_by_gmcode.pop(gm, None)
        logger.info(f'clearCardMap: cleared caches for gmcode={gm}')

    def update_ball3_latest_from_groups(self, gmcode, groups_dict: dict) -> None:
        gm = _ball3_round_id(_decode_gmcode(gmcode))
        regions = _extract_ball3_regions_from_groups(groups_dict)
        if regions is not None:
            self.ball3_latest_regions_by_gmcode[gm] = regions

    def save_ball3_final_csv(self, gmcode) -> bool:
        self._ensure_ball3_csv_ready()
        gm_raw = _decode_gmcode(gmcode)
        gm = _ball3_round_id(gm_raw)
        regions = self.ball3_latest_regions_by_gmcode.get(gm)
        if not regions:
            logger.warning(f'save_ball3_final_csv: no latest regions for gmcode={gm} (raw={gm_raw})')
            return False
        counts = _regions_to_counts(regions)
        end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        predlog = self.ball3_predlog_by_gmcode.get(gm, [])
        last_pred = predlog[-1] if predlog else None
        predlog_json = json.dumps(last_pred, ensure_ascii=False) if last_pred is not None else ''
        row = [gm, end_time, counts['A'], counts['J'], counts['Q'], counts['K'], counts['9'], counts['10'], predlog_json]
        with open(self.ball3_csv_path, 'a', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(row)
            f.flush()
        self.ball3_latest_regions_by_gmcode.pop(gm, None)
        self.ball3_predlog_by_gmcode.pop(gm, None)
        logger.info(f'[BALL3] appended CSV row -> {self.ball3_csv_path} gmcode={gm} regions={regions}')
        return True


_mgr = None


def ScanRMgrInstance() -> ScanResultManager:
    global _mgr
    if _mgr is None:
        _mgr = ScanResultManager()
    return _mgr
