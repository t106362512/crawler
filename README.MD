# crawler - ptt 爬蟲
  
## 基礎內容 

- 已容器化,只需給對應的環境變數即可使用
- k8s相關參數已經大致設定好了,照著 k8s/example.sh 使用即可建立elasticsearch, plughin 及kibana以搜集數據及處理或視覺化數據等等
- k8s/2-2.runCustomContainer_multi.yml 會去執行多線程執行緒爬蟲並導入至elasticsearch,而 k8s/2-1.runCustomContainer.yml 則是一筆一筆資料爬並一筆筆資料放入elasticsearch
- 已在 Azure kubernetes Service 上測試了,確定可用

### 說明
 - 將 .env-sample 改為 .env 並填入對應的參數即可簡單的build image並測試
 - 已先build好一份image至docker hub了,` t106362512/crawler:latest`
 - 開發人數不多,就不弄ci/cd了
 - 日後更新再搞airflow吧
 
## 感謝名單
 - [Openbox7681](https://github.com/Openbox7681/CrawlerTurtorial) - 提供 source code
 - [t106362501-簡浩庭](https://github.com/HowardCHT)
