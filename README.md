# AutoSheetMediaBuilder

一个基于 Google Sheets 的自动化媒体生成工具。

它可以从指定的 Google Sheets 行中读取文案、文件名、ElevenLabs 声音 ID 和 Google Drive 文件链接，然后批量完成以下任务：

- 导出 TXT 文本文档
- 调用 ElevenLabs 生成 MP3 音频
- 使用 rclone 下载 Google Drive 素材文件
- 根据表格中的命名字段自动整理输出文件

本项目适合用于短视频制作、配音生成、字幕文本导出、素材下载、内容生产流水线等场景。

---

## 功能特点

- 图形化界面，使用简单
- 支持读取 Google Sheets 指定行
- 支持自定义文案列、命名列、声音 ID 列、Google Drive 文件列
- 支持批量导出 TXT
- 支持自动清理多余空行
- 支持按指定字符宽度自动断行
- 支持调用 ElevenLabs API 生成 MP3 音频
- 支持通过 rclone 下载 Google Drive 文件
- 支持拖拽选择 Google 凭证 JSON 文件
- 支持拖拽选择输出文件夹
- 支持自动保存本地配置，方便下次继续使用

---

## 环境要求

使用本工具前，请确保你的电脑已准备好以下环境：

- Python 3.9 或更高版本
- Google Sheets API 凭证 JSON 文件
- ElevenLabs API Key
- rclone
- 可访问 Google Sheets 和 Google Drive 的网络环境

推荐在 Windows 系统下使用。

---

## 安装 Python 依赖

先克隆项目：

```bash
git clone https://github.com/你的用户名/AutoSheetMediaBuilder.git
cd AutoSheetMediaBuilder
```

安装依赖：

```bash
pip install -r requirements.txt
```

`requirements.txt` 建议内容如下：

```txt
PySide6
requests
google-auth
google-api-python-client
```

---

## rclone 安装与配置

本工具使用 rclone 下载 Google Drive 文件。

程序中默认调用的 rclone remote 名称是：

```txt
gdrive_rs
```

也就是说，你需要提前配置一个名为 `gdrive_rs` 的 Google Drive remote。

---

### 1. 下载 rclone

打开 rclone 下载页面：

```txt
https://rclone.org/downloads/
```

下载 Windows 版本，例如：

```txt
rclone-current-windows-amd64.zip
```

解压后可以看到：

```txt
rclone.exe
```

建议放到固定目录，例如：

```txt
C:\rclone\rclone.exe
```

---

### 2. 将 rclone 加入系统环境变量

为了让程序能直接调用 `rclone` 命令，需要把 rclone 所在目录加入系统 Path。

例如你把 `rclone.exe` 放在：

```txt
C:\rclone\rclone.exe
```

那么需要把下面这个目录加入系统环境变量 Path：

```txt
C:\rclone
```

加入后重新打开 CMD 或 PowerShell，执行：

```bash
rclone version
```

如果能看到版本信息，说明安装成功。

如果提示：

```txt
'rclone' 不是内部或外部命令
```

说明 rclone 没有正确加入环境变量，或者终端没有重新打开。

---

### 3. 配置 Google Drive remote

打开 CMD 或 PowerShell，执行：

```bash
rclone config
```

然后按提示操作。

新建 remote：

```txt
n
```

输入 remote 名称：

```txt
gdrive_rs
```

注意：名称必须是 `gdrive_rs`，因为程序默认使用这个名称。

选择存储类型时，选择：

```txt
Google Drive
```

不同版本的 rclone 中，Google Drive 对应的编号可能不同，请根据终端显示的列表选择。

---

### 4. rclone 常见配置参考

配置过程中可能会出现以下选项。

如果出现：

```txt
client_id>
```

可以直接回车。

如果出现：

```txt
client_secret>
```

可以直接回车。

如果出现：

```txt
scope>
```

建议选择完整 Drive 权限，通常是：

```txt
drive
```

或者选择 rclone 提示中的对应编号。

如果出现：

```txt
root_folder_id>
```

可以直接回车。

如果出现：

```txt
service_account_file>
```

一般可以直接回车。

如果出现：

```txt
Edit advanced config?
```

输入：

```txt
n
```

如果出现：

```txt
Use auto config?
```

如果是在自己的电脑上配置，输入：

```txt
y
```

随后浏览器会打开 Google 授权页面。

登录 Google 账号并授权 rclone 访问 Google Drive。

如果出现：

```txt
Configure this as a Shared Drive?
```

如果不是共享云端硬盘，输入：

```txt
n
```

最后确认保存：

```txt
y
```

---

### 5. 检查 rclone 配置是否成功

执行：

```bash
rclone listremotes
```

正常情况下应该能看到：

```txt
gdrive_rs:
```

也可以测试列出 Google Drive 目录：

```bash
rclone lsd gdrive_rs:
```

如果能看到目录列表，说明 rclone 配置成功。

---

### 6. 测试通过文件 ID 下载 Google Drive 文件

Google Drive 文件链接通常长这样：

```txt
https://drive.google.com/file/d/文件ID/view
```

其中 `/d/` 和 `/view` 中间的内容就是文件 ID。

例如：

```txt
https://drive.google.com/file/d/1AbCdEfGhIjK123456789/view
```

文件 ID 是：

```txt
1AbCdEfGhIjK123456789
```

可以手动测试下载：

```bash
rclone backend copyid gdrive_rs: 1AbCdEfGhIjK123456789 ./test_download/
```

如果文件能下载到 `test_download` 文件夹中，说明配置正常。

---

### 7. 为什么 remote 名称必须是 gdrive_rs

程序中默认使用以下 remote：

```txt
gdrive_rs:
```

也就是会调用类似下面的命令：

```bash
rclone backend copyid gdrive_rs: 文件ID 输出目录
```

如果你的 rclone remote 不是 `gdrive_rs`，程序会下载失败。

如果你想使用其他名称，需要修改代码里的：

```python
"gdrive_rs:"
```

例如改成：

```python
"mydrive:"
```

然后你的 rclone remote 名称也要叫：

```txt
mydrive
```

---

## Google Sheets 凭证配置

本工具通过 Google Service Account 读取 Google Sheets 内容。

你需要准备一个 Google 服务账号 JSON 凭证文件。

基本步骤如下：

1. 打开 Google Cloud Console
2. 创建一个项目
3. 启用 Google Sheets API
4. 创建 Service Account
5. 下载 Service Account 的 JSON 凭证文件
6. 将 Google Sheets 表格共享给 Service Account 邮箱

Service Account 邮箱通常类似：

```txt
xxxx@xxxx.iam.gserviceaccount.com
```

你需要把 Google Sheets 表格共享给这个邮箱，并至少给予读取权限。

---

## ElevenLabs 配置

如果需要生成 MP3 音频，需要准备 ElevenLabs API Key。

程序会根据表格中的 Voice ID 调用 ElevenLabs 文本转语音接口生成音频文件。

如果你只想导出 TXT 或下载 Google Drive 文件，可以不勾选音频生成任务。

---

## Google Sheets 表格字段说明

建议你的 Google Sheets 中包含以下字段：

| 字段 | 说明 | 示例 |
| --- | --- | --- |
| 文案列 | 要导出的文本，或者用于生成语音的文案 | G |
| 命名列 | 输出文件名 | O |
| 声音 ID 列 | ElevenLabs Voice ID | S |
| Google Drive 文件列 | Google Drive 文件链接或 File ID | U |

程序支持自定义列名，例如：

```txt
文案所在列：G
命名所在列：O
声音ID列：S
Google Drive 文件列：U
```

---

## 使用方法

运行程序：

```bash
python XL-GoogleSheet2Audio_Txt.py
```

打开软件界面后，按顺序填写信息。

---

### 1. API 与授权

填写：

- ElevenLabs API Key
- Google 凭证 JSON 文件路径

Google 凭证 JSON 文件可以直接拖拽到输入框中。

---

### 2. Google 表格配置

填写：

- Google Sheets 表格 ID
- 工作表名称
- 目标行号
- 文案所在列
- 命名所在列
- 声音 ID 列
- Google Drive 文件列

Google Sheets 表格 ID 是链接中 `/d/` 和 `/edit` 之间的内容。

例如：

```txt
https://docs.google.com/spreadsheets/d/这里是表格ID/edit
```

---

### 3. 任务与输出设置

选择输出文件夹，然后勾选需要执行的任务：

- 导出 TXT 文本
- 对文案执行自动断行
- 调用 ElevenLabs 生成 MP3
- 使用 rclone 下载 Google Drive 文件

目标行号支持以下格式：

```txt
10
10,12,15
10-20
10,12-15,20
```

填写完成后，点击：

```txt
开始执行全自动流水线
```

程序会自动处理指定行，并在运行日志中显示进度。

---

## 输出结果

程序会根据表格中的命名列生成文件名。

可能输出的文件包括：

```txt
文件名.txt
文件名.mp3
文件名.jpg
文件名.png
文件名.mp4
```

Google Drive 文件会保留原始扩展名。

如果命名列为空，程序会自动使用类似下面的名称：

```txt
Row_10_Unnamed
```

---

## 配置文件

程序会自动创建并保存配置文件：

```txt
config/App_config.json
```

该文件会保存：

- ElevenLabs API Key
- Google 凭证路径
- Google Sheets 表格 ID
- 工作表名称
- 输出目录
- 目标行号
- 列配置
- 任务勾选状态

下次打开程序时会自动读取配置。

---

## 安全注意事项

请不要把敏感信息提交到 GitHub。

尤其不要提交：

- ElevenLabs API Key
- Google Service Account JSON 凭证
- rclone 配置文件
- config/App_config.json
- 任何 token、密钥、账号信息

建议 `.gitignore` 中加入：

```gitignore
config/App_config.json
*.json
rclone.conf
__pycache__/
*.pyc
dist/
build/
*.spec
```

如果项目需要提供配置示例，可以创建：

```txt
App_config.example.json
```

不要上传真实密钥。

---

## 常见问题

### 1. 提示 Google 凭证文件不存在

请检查：

- JSON 凭证路径是否正确
- 文件是否真的存在
- 是否拖拽了正确的 JSON 文件

---

### 2. 无法读取 Google Sheets

请检查：

- Google Sheets API 是否已启用
- Service Account JSON 是否正确
- 表格是否已共享给 Service Account 邮箱
- 表格 ID 是否填写正确
- 工作表名称是否填写正确

---

### 3. MP3 生成失败

请检查：

- ElevenLabs API Key 是否正确
- Voice ID 是否正确
- ElevenLabs 账号额度是否充足
- 网络是否可以访问 ElevenLabs API

---

### 4. Google Drive 文件下载失败

请检查：

- 是否已安装 rclone
- 是否已配置 `gdrive_rs`
- Google Drive 文件链接是否有效
- 当前 rclone 登录账号是否有访问权限
- 文件是否被删除
- 文件 ID 是否能正确提取

可以先用命令测试：

```bash
rclone listremotes
rclone lsd gdrive_rs:
```

---

### 5. rclone 提示不是内部或外部命令

说明系统找不到 rclone。

请检查：

- `rclone.exe` 是否已经下载
- rclone 所在目录是否加入 Path
- CMD 或 PowerShell 是否重新打开

---

### 6. 文件名异常

程序会自动清理文件名中的非法字符，例如：

```txt
\ / : * ? " < > |
```

如果命名列为空，会自动使用默认文件名。

---

## 打包为 EXE

可以使用 PyInstaller 打包：

```bash
pip install pyinstaller
pyinstaller --onefile --windowed XL-GoogleSheet2Audio_Txt.py
```

打包完成后，文件通常位于：

```txt
dist/
```

如果你的程序依赖外部文件或配置，请确保这些文件也放在正确位置。

---

## 项目结构示例

```txt
AutoSheetMediaBuilder/
├── XL-GoogleSheet2Audio_Txt.py
├── requirements.txt
├── README.md
├── .gitignore
└── config/
    └── App_config.json
```

注意：`config/App_config.json` 不建议提交到 GitHub。

---

## 免责声明

本工具仅用于自动化处理你有权限访问的 Google Sheets 和 Google Drive 文件。

使用 ElevenLabs、Google API、rclone 等第三方服务时，请遵守对应平台的服务条款和使用限制。

如果因错误配置、密钥泄露、权限设置不当或第三方服务限制导致问题，使用者需自行承担相关风险。
