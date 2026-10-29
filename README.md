# 交医课程评价工具

透过 WebVPN 登录上海交通大学医学院教务系统，逐项开启课程评价。
默认只填写供使用者检查；正式提交须启用设置，并在每次执行输入 `SUBMIT` 确认。

这是个人工具，与学校官方没有隶属关系。仓库及下载包只提供程序和空白设置，
不包含账号密码、登录会话、课程文件或真实评价记录。请用自己的账号，遵守校方规定。

## 推荐：下载 Windows ZIP

1. 从本仓库 **Releases** 下载 `JiaoyiCourseEvaluation-v0.1.4-windows-x64.zip`。
2. 完整解压到可写文件夹，保留 `_internal` 和附带文件。
3. 用记事本编辑 `config.ini`，填自己的设置。
4. 双击 `RunCourseEvaluation.exe`。

Windows x64，使用已安装的 **Chrome 或 Edge**；包内附 Python、Selenium 和 OCR 资源，
不需另装 Python。首次使用、缓存清除或浏览器更新后，可能需连网下载匹配驱动。
程序仍需连接学校系统，并非离线工具。

## 设置

| 区段／字段 | 用途 |
| --- | --- |
| `user-account.username` | 自己的 WebVPN 账号 |
| `user-account.password` | 自己的密码；与账号同时留空可手动登录 |
| `browser-option.driver` | `Chrome` 或 `Edge` |
| `browser-option.exe_path` | 浏览器 exe 完整路径；留空自动寻找 |
| `browser-option.driver_path` | 进阶驱动路径；一般留空 |
| `evaluation-option.submit` | `false` 预览；`true` 正式提交，仍须当次确认 |
| `evaluation-option.rating_level` | `highest`（默认最高级）或指定 `1`、`2`、`3` 等等级 |
| `evaluation-option.max_courses` | 正式处理上限；`0` 为全部有效未完成记录 |
| `evaluation-option.dry_run_limit` | 预览表单数，默认 `1` |
| `script-option.headless` | 是否隐藏浏览器；手动登录须为 `false` |
| `script-option.close_browser_on_finish` | 成功后是否关闭本次浏览器 |

路径可写 `C:\Program Files\Google\Chrome\Application\chrome.exe`，不用引号或双反斜线。
设置采 UTF-8，附中文注解。密码中的 `%`、`#`、`;` 视为文字。
**设置是本机明文文件；请勿把填好的 config.ini、日志或登录状态贴到 Issues。**

源代码首次启动会建立空白 `config.ini` 并结束，编辑后重新启动。
明确指定 `--config` 时只读该档；存在 INI 时，空账号密码不从旧 `.env` 补入。
未建立 INI 的旧源代码环境仍兼容原有 JSON／`.env`，但不自动迁移秘密到发布设置。

## 选择评分等级

在 `config.ini` 的 `[evaluation-option]` 中设置：

```ini
[evaluation-option]
rating_level = highest
```

`highest` 自动选择每题的最后一项：五级表单选第 5 级，三级表单选第 3 级。
需要统一评第 3 级时改为 `rating_level = 3`；填 `1` 则选择每题第一项。
数字按每题从左到右的选项顺序计算，适用于选项从低到高排列的表单；请先预览确认。
若任何题目没有指定等级，或该项不可选，程序会停止并提示，不会改用其他等级提交。
旧配置未填写此项时继续默认最高级。

命令行可临时覆盖配置，例如 `RunCourseEvaluation.exe --rating-level 4 --dry-run`。
兼容 JSON 的对应字段为 `evaluation.ratingLevel`，可填 `"highest"` 或正整数。

## 评价行为

- 按配置选择每题等级，默认最高级（最后一项）；不同表单次序可能不同，请先预览。
- 预览会停留在填好的表单，检查后按 Enter 返回；无互动输入时保留该页并结束。
- 留言默认空白。进阶既有评价设置可用兼容 JSON。
- 逐项处理有效未完成记录，跨页继续；null 课程字段跳过。
- 等待实际服务器回应；拒绝或超时停止，不自动重复提交该表单。
- 若达到上限而仍有未完成记录，会提示。
- 不保存工作流程截图；日志在 `logs/evaluation.log`，新执行会覆写。
- 成功可保留浏览器；失败时清理本次启动的浏览器与驱动。

## 命令列与诊断

```powershell
.\RunCourseEvaluation.exe --check
.\RunCourseEvaluation.exe --diagnose
.\RunCourseEvaluation.exe --check-browser
.\RunCourseEvaluation.exe --dry-run --dry-run-limit 1
.\RunCourseEvaluation.exe --rating-level 3 --dry-run
.\RunCourseEvaluation.exe --submit --max-courses 1
.\RunCourseEvaluation.exe --mode schedule
```

`--check` 只验证设置，`--diagnose` 检查依赖包及 OCR，`--check-browser` 只开本地测试页。
诊断均不提交学校评价。`--dry-run` 强制覆盖设置中的提交开关。

## 源代码使用

安装 Python 3.12（已验证版本）及 Chrome／Edge，下载源代码并解压，双击 `start_evaluation.cmd`。
首次会在专案 `.venv` 安装锁定依赖，需要连网，不依赖开发者专属路径。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -X utf8 app.py --check
.\.venv\Scripts\python.exe -X utf8 app.py
```

## 常见问题

- **找不到浏览器**：安装 Chrome／Edge，或填 `exe_path`。
- **驱动下载失败**：检查网路／代理，或用 `driver_path` 指定匹配驱动。Edge 前三段版本需匹配。
- **验证码或额外验证**：在本次浏览器完成；OCR 失败时保留手动流程。
- **首次只建立设置就结束**：属正常行为，编辑设置后重新启动。
- **不能写设置或日志**：解压到可写文件夹，不要直接在 ZIP 内启动。
- **Windows 信任提示**：目前未签章；核对下载来源及 SHA-256。杂凑不等于签章，不能保证无提示。
- **学校页面改版**：目前仅针对指定 WebVPN／教务系统，未来页面变更可能需更新。

## 开发、测试与构建

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests -v
$env:RUN_BROWSER_TESTS = '1'
$env:TEST_BROWSER = 'Chrome' # 或 Edge
.\.venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests -p test_browser_integration.py -v
.\.venv\Scripts\python.exe -X utf8 tools/build_release.py
```

浏览器测试用本地模拟表单，不需真实账号密码，不提交学校评价。
测试页下载 jQuery／Bootstrap Table，需连网。在 Windows x64 的干净虚拟环境构建。
成品在 `releases/`，含源代码 ZIP、Windows ZIP 及 `SHA256SUMS.txt`。
构建只收集公开允许清单，排除私人设置、日志及浏览器资料。

## 授权与来源

应用程序源代码采 MIT，见 `LICENSE`。依赖包保留各自授权；Windows ZIP 的
`third_party_licenses/` 收录授权、声明及版本清单。
登录流程沿用本地 AutoCourseDownload 的 Selenium 实作，不含其下载、PowerPoint 或微信功能。
学校系统、课件及使用者资料不属于本仓库的授权内容。
