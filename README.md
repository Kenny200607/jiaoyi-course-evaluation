# 交醫課程評價工具

透過 WebVPN 登入上海交通大學醫學院教務系統，逐項開啟課程評價。
預設只填寫供使用者檢查；正式提交須啟用設定，並在每次執行輸入 `SUBMIT` 確認。

這是個人工具，與學校官方沒有隸屬關係。倉庫及下載包只提供程式和空白設定，
不包含帳密、登入會話、課程文件或真實評價紀錄。請用自己的帳號，遵守校方規定。

## 推薦：下載 Windows ZIP

1. 從本倉庫 **Releases** 下載 `JiaoyiCourseEvaluation-v0.1.1-windows-x64.zip`。
2. 完整解壓到可寫資料夾，保留 `_internal` 和附帶文件。
3. 用記事本編輯 `config.ini`，填自己的設定。
4. 雙擊 `RunCourseEvaluation.exe`。

Windows x64，使用已安裝的 **Chrome 或 Edge**；包內附 Python、Selenium 和 OCR 資源，
不需另裝 Python。首次使用、快取清除或瀏覽器更新後，可能需連網下載匹配驅動。
程式仍需連接學校系統，並非離線工具。

## 設定

| 區段／欄位 | 用途 |
| --- | --- |
| `user-account.username` | 自己的 WebVPN 帳號 |
| `user-account.password` | 自己的密碼；與帳號同時留空可手動登入 |
| `browser-option.driver` | `Chrome` 或 `Edge` |
| `browser-option.exe_path` | 瀏覽器 exe 完整路徑；留空自動尋找 |
| `browser-option.driver_path` | 進階驅動路徑；一般留空 |
| `evaluation-option.submit` | `false` 預覽；`true` 正式提交，仍須當次確認 |
| `evaluation-option.max_courses` | 正式處理上限；`0` 為全部有效未完成記錄 |
| `evaluation-option.dry_run_limit` | 預覽表單數，預設 `1` |
| `script-option.headless` | 是否隱藏瀏覽器；手動登入須為 `false` |
| `script-option.close_browser_on_finish` | 成功後是否關閉本次瀏覽器 |

路徑可寫 `C:\Program Files\Google\Chrome\Application\chrome.exe`，不用引號或雙反斜線。
設定採 UTF-8，附中文註解。密碼中的 `%`、`#`、`;` 視為文字。
**設定是本機明文檔案；請勿把填好的 config.ini、日誌或登入狀態貼到 Issues。**

原始碼首次啟動會建立空白 `config.ini` 並結束，編輯後重新啟動。
明確指定 `--config` 時只讀該檔；存在 INI 時，空帳密不從舊 `.env` 補入。
未建立 INI 的舊原始碼環境仍相容原有 JSON／`.env`，但不自動遷移秘密到發布設定。

## 評價行為

- 每列選擇最後一個單選項；不同表單次序可能不同，請先預覽。
- 預覽會停留在填好的表單，檢查後按 Enter 返回；無互動輸入時保留該頁並結束。
- 留言預設空白。進階既有評價設定可用相容 JSON。
- 逐項處理有效未完成記錄，跨頁繼續；null 課程欄位跳過。
- 等待實際伺服器回應；拒絕或逾時停止，不自動重複提交該表單。
- 若達到上限而仍有未完成記錄，會提示。
- 不保存工作流程截圖；日誌在 `logs/evaluation.log`，新執行會覆寫。
- 成功可保留瀏覽器；失敗時清理本次啟動的瀏覽器與驅動。

## 命令列與診斷

```powershell
.\RunCourseEvaluation.exe --check
.\RunCourseEvaluation.exe --diagnose
.\RunCourseEvaluation.exe --check-browser
.\RunCourseEvaluation.exe --dry-run --dry-run-limit 1
.\RunCourseEvaluation.exe --submit --max-courses 1
.\RunCourseEvaluation.exe --mode schedule
```

`--check` 只驗證設定，`--diagnose` 檢查套件及 OCR，`--check-browser` 只開本地測試頁。
診斷均不提交學校評價。`--dry-run` 強制覆蓋設定中的提交開關。

## 原始碼使用

安裝 Python 3.12（已驗證版本）及 Chrome／Edge，下載原始碼並解壓，雙擊 `start_evaluation.cmd`。
首次會在專案 `.venv` 安裝鎖定依賴，需要連網，不依賴開發者專屬路徑。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -X utf8 app.py --check
.\.venv\Scripts\python.exe -X utf8 app.py
```

## 常見問題

- **找不到瀏覽器**：安裝 Chrome／Edge，或填 `exe_path`。
- **驅動下載失敗**：檢查網路／代理，或用 `driver_path` 指定匹配驅動。Edge 前三段版本需匹配。
- **驗證碼或額外驗證**：在本次瀏覽器完成；OCR 失敗時保留手動流程。
- **首次只建立設定就結束**：屬正常行為，編輯設定後重新啟動。
- **不能寫設定或日誌**：解壓到可寫資料夾，不要直接在 ZIP 內啟動。
- **Windows 信任提示**：目前未簽章；核對下載來源及 SHA-256。雜湊不等於簽章，不能保證無提示。
- **學校頁面改版**：目前僅針對指定 WebVPN／教務系統，未來頁面變更可能需更新。

## 開發、測試與建置

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests -v
$env:RUN_BROWSER_TESTS = '1'
$env:TEST_BROWSER = 'Chrome' # 或 Edge
.\.venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests -p test_browser_integration.py -v
.\.venv\Scripts\python.exe -X utf8 tools/build_release.py
```

瀏覽器測試用本地模擬表單，不需真實帳密，不提交學校評價。
測試頁下載 jQuery／Bootstrap Table，需連網。在 Windows x64 的乾淨虛擬環境建置。
成品在 `releases/`，含原始碼 ZIP、Windows ZIP 及 `SHA256SUMS.txt`。
建置只收集公開允許清單，排除私人設定、日誌及瀏覽器資料。

## 授權與來源

應用程式原始碼採 MIT，見 `LICENSE`。套件保留各自授權；Windows ZIP 的
`third_party_licenses/` 收錄授權、聲明及版本清單。
登入流程沿用本地 AutoCourseDownload 的 Selenium 實作，不含其下載、PowerPoint 或微信功能。
設定方式參考 Autovisor，發布與文件組織參考
[交醫課件下載器](https://github.com/fishchipssss/jiaoyi-courseware-downloader)。
學校系統、課件及使用者資料不屬於本倉庫的授權內容。
