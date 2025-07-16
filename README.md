# 20250703 update : pydeaerLight 
優化修正推論端設定成遠端推論引擎URL 修改組態設定方式 ,完全捨棄本地模型檔推論  
config.xml url to videolist.xml, and remove self-predicting codes  

--生成exe步驟  
conda create -n pydealerlight_test python=3.10.12 -y  
conda activate pydealerlight_test  
python -m pip install -U pip  
pip install -r requirements.txt  

pyinstaller --clean --noconfirm pydealerLight_httpapi.spec  
本次.spec包含將config.xml與models/videolist.xml放進去的動作，但標註檔.xml還是需手動放入，因每個流有不同的設定檔  

# 20250625 update : add PH_BAC exec build  

conda create -n BJ21pydealer_test python=3.10.12 -y  
conda activate BJ21pydealer_test  
python -m pip install -U pip  
pip install -r requirements.txt  

smoke test : python main.py  

pyinstaller --clean --onedir --console --name pydealer_httpapi --hidden-import=tkinter --runtime-hook=hook_force_stdlib_distutils.py --add-data "config.xml;." --add-data "models;models" main.py    
<!-- pyinstaller --clean --noconfirm ImageDetector_PH.spec   -->
如dist裡面的pydealer_httpapi資料夾內還是沒有config.xml或models資料夾，請將外面專案資料夾的這兩份檔案複製進去  => 目前都是手動放置  


# PyDealerClient

image recognition which sample live video and send result data to Dealer by net socket.

# release note
2022/11/2 v1.5.6
1. fix��ͼ�ϴ��ͺ�16s.
2. log add gmSaveFinalResult and gmCount.
3. support samba folder to save snapshot images.
2022/10/22 v1.5.1
1. ���������ͼƬ.
# if len(save_descjudge) > 0:
#     self.imageSaver.save(gmcode, int(pos.index), save_descjudge, save_scorejudge, predict_image_save, False)
imageSaver = ImageSaver(cfg.save_folder)  //������ͼƬ����Ŀ¼
2. �����ļ��޸�
	<save folder="./predict_images" autoUpload="0"/>

2022/10/5 v1.5.0
    only produce one full image and upload to FTP Server.

2022/8/16 v1.4.2
    init as baseline.

