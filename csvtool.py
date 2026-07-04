# encoding=utf-8

import os
import datetime as d
import pandas as pd

LEGACY_HEADER = ["game", "idx", "class_dealer", "class_model", "score", "card_number", "endid"]


class csvtool(object):
    def __init__(self, dir):
        self.dir = dir
        self.curDir = None
        self.session_ts = d.datetime.now().strftime('%Y%m%d_%H%M%S')
        os.makedirs(dir, exist_ok=True)

    def curDate(self):
        return d.datetime.now().strftime('%Y-%m-%d')

    def curFileName(self):
        return d.datetime.now().strftime('%Y%m%d_%H%M%S.csv')

    def _ensure_dir(self):
        newDir = os.path.join(self.dir, self.curDate())
        os.makedirs(newDir, exist_ok=True)
        self.curDir = newDir
        return newDir

    def _append_rows(self, filename, rows):
        file_exists = os.path.exists(filename)
        file_has_content = file_exists and os.path.getsize(filename) > 0
        rows_to_write = list(rows)
        if not file_has_content:
            rows_to_write = [LEGACY_HEADER] + rows_to_write
        data_df = pd.DataFrame(rows_to_write)
        data_df.to_csv(filename, header=False, index=False, mode='a')

    def write(self, messagelist, isFinalResult):
        cur_dir = self._ensure_dir()
        if isFinalResult:
            newfile = os.path.join(cur_dir, 'finalresult_' + d.datetime.now().strftime('%Y%m%d') + '.csv')
        else:
            newfile = os.path.join(cur_dir, self.curFileName())
        self._append_rows(newfile, messagelist)


_csvtooler = None


def _get_csvtooler():
    global _csvtooler
    if _csvtooler is None:
        _csvtooler = csvtool('./csv')
    return _csvtooler


def tocsv(message, isFinalResult):
    _get_csvtooler().write(message, isFinalResult)
