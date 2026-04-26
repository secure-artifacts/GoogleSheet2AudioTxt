import warnings

warnings.filterwarnings("ignore")  # 忽略所有控制台警告

import sys
import os
import re
import json
import tempfile
import requests
import subprocess
import shutil  # 用于文件移动和文件夹清理
import time
from google.oauth2 import service_account
from googleapiclient.discovery import build
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QTextEdit, QMessageBox,
                               QCheckBox, QSpinBox, QGroupBox, QProgressBar)
from PySide6.QtCore import Qt, QThread, Signal


# =========================
# 工具函数：文本处理、路径与列转换
# =========================

def sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符"""
    name = name.strip()
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.strip(".")
    return name or "untitled"


def clean_blank_lines(text: str) -> str:
    """彻底清理所有多余的空行"""
    lines = text.splitlines()
    valid_lines = [line for line in lines if line.strip() != ""]
    return "\n".join(valid_lines)


def wrap_text(text: str, width: int) -> str:
    """按指定字符宽度进行自动断行"""
    paragraphs = re.split(r"\n\s*\n", text.strip())
    wrapped_result = []

    for para in paragraphs:
        words = para.split()
        if not words:
            continue

        line = ""
        for word in words:
            if not line:
                line = word
            elif len(line) + 1 + len(word) <= width:
                line += " " + word
            else:
                wrapped_result.append(line)
                line = word

            if line and line[-1] in [":", ".", "?", "!", "：", "。", "？", "！"]:
                wrapped_result.append(line)
                line = ""

        if line:
            wrapped_result.append(line)
        wrapped_result.append("")

    while wrapped_result and wrapped_result[-1] == "":
        wrapped_result.pop()

    return clean_blank_lines("\n".join(wrapped_result))


def col2num(col_str: str) -> int:
    """将Excel/Google Sheets的列字母(如A, B, Z, AA)转换为从0开始的索引"""
    num = 0
    for c in col_str.upper():
        if 'A' <= c <= 'Z':
            num = num * 26 + (ord(c) - ord('A') + 1)
    return num - 1 if num > 0 else 0


def extract_drive_id(url: str) -> str:
    """从 Google Drive 链接或纯 File ID 中提取 File ID"""
    if not url:
        return None

    url = str(url).strip()
    if not url:
        return None

    # 如果本身就是 file id，则直接返回
    if re.fullmatch(r"[a-zA-Z0-9_-]{10,}", url):
        return url

    match = re.search(r'/d/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)

    match = re.search(r'id=([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)

    return None


# =========================
# UI 组件
# =========================

class DragDropLineEdit(QLineEdit):
    """自定义带拖拽功能的单行输入框"""
    def __init__(self, is_folder=False, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.is_folder = is_folder

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            url = event.mimeData().urls()[0]
            path = url.toLocalFile()

            if self.is_folder and os.path.isdir(path):
                self.setText(path)
            elif not self.is_folder and os.path.isfile(path):
                self.setText(path)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


# =========================
# 后台工作线程
# =========================

class UnifiedGeneratorThread(QThread):
    log_signal = Signal(str)
    progress_signal = Signal(int, int)  # done, total
    finished_signal = Signal()

    def __init__(self, config_data):
        super().__init__()
        self.cfg = config_data
        self.SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

    def parse_rows(self, row_str):
        rows = set()
        for part in row_str.split(','):
            part = part.strip()
            if not part:
                continue
            if '-' in part:
                try:
                    start, end = part.split('-')
                    rows.update(range(int(start), int(end) + 1))
                except ValueError:
                    continue
            else:
                try:
                    rows.add(int(part))
                except ValueError:
                    continue
        return sorted(list(rows))

    def run(self):
        try:
            idx_text = col2num(self.cfg["col_text"])
            idx_name = col2num(self.cfg["col_name"])
            idx_voice = col2num(self.cfg["col_voice"])
            idx_img = col2num(self.cfg["col_img"])

            self.log_signal.emit("🔄 正在验证 Google 凭证并连接表格...")
            creds = service_account.Credentials.from_service_account_file(
                self.cfg["cred_path"], scopes=self.SCOPES)
            service = build('sheets', 'v4', credentials=creds)

            range_name = f"{self.cfg['sheet_name']}!A:ZZ"
            sheet = service.spreadsheets()
            result = sheet.values().get(spreadsheetId=self.cfg["sheet_id"], range=range_name).execute()
            values = result.get('values', [])

            if not values:
                self.log_signal.emit("❌ 表格中没有找到数据。")
                return

            target_rows = self.parse_rows(self.cfg["rows_str"])
            if not target_rows:
                self.log_signal.emit("❌ 未检测到有效的行号配置。")
                return

            self.log_signal.emit(f"📋 准备处理的行号: {target_rows}")
            total_tasks = len(target_rows)

            for i, row_num in enumerate(target_rows):
                idx = row_num - 1

                if idx < 0 or idx >= len(values):
                    self.log_signal.emit(f"⚠️ 行 {row_num}：超出表格实际数据范围，跳过。")
                    self.progress_signal.emit(i + 1, total_tasks)
                    continue

                row_data = values[idx]

                text = str(row_data[idx_text]).strip() if len(row_data) > idx_text else ""
                file_name_raw = str(row_data[idx_name]).strip() if len(row_data) > idx_name else ""
                voice_id = str(row_data[idx_voice]).strip() if len(row_data) > idx_voice else ""
                img_link = str(row_data[idx_img]).strip() if len(row_data) > idx_img else ""

                if not text and not img_link:
                    self.log_signal.emit(f"⏭️ 行 {row_num}：文案和 Drive 文件链接均为空，跳过。")
                    self.progress_signal.emit(i + 1, total_tasks)
                    continue

                if not file_name_raw:
                    file_name_raw = f"Row_{row_num}_Unnamed"

                file_name = sanitize_filename(file_name_raw)

                # --- A. 文本处理 ---
                processed_text = text
                if self.cfg["task_wrap"] and processed_text:
                    processed_text = wrap_text(processed_text, self.cfg["wrap_width"])

                # --- B. 导出 TXT ---
                if self.cfg["task_txt"] and processed_text:
                    txt_path = os.path.join(self.cfg["output_dir"], f"{file_name}.txt")
                    try:
                        with open(txt_path, 'w', encoding='utf-8') as f:
                            f.write(processed_text)
                        self.log_signal.emit(f"✅ 行 {row_num} [TXT]: 保存成功 -> {file_name}.txt")
                    except Exception as e:
                        self.log_signal.emit(f"❌ 行 {row_num} [TXT]: 写入失败 -> {e}")

                # --- C. 导出 Audio ---
                if self.cfg["task_audio"] and processed_text:
                    if not voice_id:
                        self.log_signal.emit(f"⚠️ 行 {row_num} [MP3]: 声音ID为空，跳过。")
                    else:
                        self.log_signal.emit(f"⏳ 行 {row_num} [MP3]: 正在调用 ElevenLabs (Voice ID: {voice_id})...")
                        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
                        headers = {
                            "Accept": "audio/mpeg",
                            "Content-Type": "application/json",
                            "xi-api-key": self.cfg["api_key"]
                        }
                        data = {
                            "text": processed_text,
                            "model_id": "eleven_v3",
                            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
                        }

                        try:
                            response = requests.post(url, json=data, headers=headers)
                            if response.status_code == 200:
                                mp3_path = os.path.join(self.cfg["output_dir"], f"{file_name}.mp3")
                                with open(mp3_path, 'wb') as f:
                                    f.write(response.content)
                                self.log_signal.emit(f"✅ 行 {row_num} [MP3]: 生成成功 -> {file_name}.mp3")
                            else:
                                self.log_signal.emit(f"❌ 行 {row_num} [MP3]: 失败 HTTP {response.status_code}")
                        except Exception as e:
                            self.log_signal.emit(f"❌ 行 {row_num} [MP3]: 网络请求异常 -> {e}")

                # --- D. 导出 Google Drive 文件 (使用 rclone) ---
                if self.cfg["task_img"]:
                    if not img_link:
                        self.log_signal.emit(f"⚠️ 行 {row_num} [Drive]: 文件链接为空，跳过下载。")
                    else:
                        file_id = extract_drive_id(img_link)
                        if file_id:
                            self.log_signal.emit(f"⏳ 行 {row_num} [Drive]: 正在调用 rclone 下载文件 (ID: {file_id})...")
                            try:
                                with tempfile.TemporaryDirectory() as tmpdir:
                                    # Windows 下避免 copyid 把目标路径误判成单文件路径
                                    download_dir = os.path.join(tmpdir, "downloaded")
                                    os.makedirs(download_dir, exist_ok=True)

                                    # 末尾补分隔符，明确告诉 rclone 这是目录
                                    rclone_target = download_dir + os.sep

                                    startupinfo = None
                                    if os.name == 'nt':
                                        startupinfo = subprocess.STARTUPINFO()
                                        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                                    max_attempts = 4
                                    retry_wait_seconds = 20
                                    result = None
                                    err_msg = ""

                                    for attempt in range(1, max_attempts + 1):
                                        if attempt == 1:
                                            self.log_signal.emit(
                                                f"⏳ 行 {row_num} [Drive]: 开始下载文件 (ID: {file_id})..."
                                            )
                                        else:
                                            self.log_signal.emit(
                                                f"🔁 行 {row_num} [Drive]: 第 {attempt} 次重新下载失败文件 (ID: {file_id})..."
                                            )

                                        cmd = [
                                            "rclone",
                                            "--contimeout", "15s",
                                            "--timeout", "60s",
                                            "--retries", "1",
                                            "--low-level-retries", "1",
                                            "backend", "copyid",
                                            "gdrive_rs:", file_id, rclone_target
                                        ]

                                        result = subprocess.run(
                                            cmd,
                                            capture_output=True,
                                            text=True,
                                            startupinfo=startupinfo,
                                            shell=False
                                        )

                                        if result.returncode == 0:
                                            break

                                        err_msg = result.stderr.strip() if result.stderr else (
                                            result.stdout.strip() if result.stdout else "未知错误（无报错输出）"
                                        )

                                        if attempt < max_attempts:
                                            self.log_signal.emit(
                                                f"⚠️ 行 {row_num} [Drive]: 下载失败，20 秒后重试。错误详情: {err_msg}"
                                            )
                                            time.sleep(retry_wait_seconds)
                                        else:
                                            self.log_signal.emit(
                                                f"❌ 行 {row_num} [Drive]: 连续 {max_attempts} 次下载失败，跳过。错误详情: {err_msg}"
                                            )

                                    if result is None or result.returncode != 0:
                                        self.log_signal.emit(
                                            f"❌ 行 {row_num} [Drive]: 未能下载文件。请检查 ID、权限或网络。详情: {err_msg}"
                                        )
                                    else:
                                        files = [
                                            os.path.join(download_dir, f)
                                            for f in os.listdir(download_dir)
                                            if os.path.isfile(os.path.join(download_dir, f))
                                        ]

                                        if not files:
                                            self.log_signal.emit(f"❌ 行 {row_num} [Drive]: 下载成功后未找到实际文件。")
                                        else:
                                            src_file = files[0]
                                            _, ext = os.path.splitext(src_file)
                                            final_path = os.path.join(self.cfg["output_dir"], f"{file_name}{ext}")

                                            if os.path.exists(final_path):
                                                os.remove(final_path)

                                            shutil.move(src_file, final_path)
                                            self.log_signal.emit(
                                                f"✅ 行 {row_num} [Drive]: 下载成功 -> {os.path.basename(final_path)}"
                                            )

                            except Exception as e:
                                self.log_signal.emit(f"❌ 行 {row_num} [Drive]: 执行过程代码异常 -> {str(e)}")
                        else:
                            self.log_signal.emit(f"⚠️ 行 {row_num} [Drive]: 无法从链接中提取 File ID，跳过 -> {img_link}")

                # 更新进度
                self.progress_signal.emit(i + 1, total_tasks)

        except Exception as e:
            self.log_signal.emit(f"❌ 发生致命错误: {str(e)}")
        finally:
            self.log_signal.emit("\n🎉 === 队列任务全部结束 ===")
            self.finished_signal.emit()


# =========================
# 主界面
# =========================

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("全自动工作流：Google Sheets提取 + 文本格式化 + 语音生成 + rclone网盘文件下载")
        self.resize(800, 850)

        self.config_file = "config/App_config.json"

        self.init_ui()
        self.load_config()

    def init_ui(self):
        main_layout = QVBoxLayout()

        group_api = QGroupBox("1. API 与 授权")
        layout_api = QVBoxLayout()
        layout_api.addWidget(QLabel("ElevenLabs API Key:"))
        self.api_input = QLineEdit()
        self.api_input.setEchoMode(QLineEdit.Password)
        layout_api.addWidget(self.api_input)
        layout_api.addWidget(QLabel("Google 凭证 JSON (拖拽文件):"))
        self.cred_input = DragDropLineEdit(is_folder=False)
        layout_api.addWidget(self.cred_input)
        group_api.setLayout(layout_api)
        main_layout.addWidget(group_api)

        group_sheet = QGroupBox("2. Google 表格配置")
        layout_sheet = QVBoxLayout()
        layout_sheet.addWidget(QLabel("表格 ID (/d/ 和 /edit 之间的内容):"))
        self.sheet_id_input = QLineEdit()
        layout_sheet.addWidget(self.sheet_id_input)

        h_layout = QHBoxLayout()
        v_layout1 = QVBoxLayout()
        v_layout1.addWidget(QLabel("工作表名称 (如: Sheet1):"))
        self.sheet_name_input = QLineEdit()
        v_layout1.addWidget(self.sheet_name_input)
        h_layout.addLayout(v_layout1)

        v_layout2 = QVBoxLayout()
        v_layout2.addWidget(QLabel("目标行号 (如: 10, 12-15):"))
        self.rows_input = QLineEdit()
        v_layout2.addWidget(self.rows_input)
        h_layout.addLayout(v_layout2)

        layout_sheet.addLayout(h_layout)

        col_layout = QHBoxLayout()
        v_col_text = QVBoxLayout()
        v_col_text.addWidget(QLabel("文案所在列 (如 G):"))
        self.col_text_input = QLineEdit()
        self.col_text_input.setPlaceholderText("G")
        v_col_text.addWidget(self.col_text_input)
        col_layout.addLayout(v_col_text)

        v_col_name = QVBoxLayout()
        v_col_name.addWidget(QLabel("命名所在列 (如 O):"))
        self.col_name_input = QLineEdit()
        self.col_name_input.setPlaceholderText("O")
        v_col_name.addWidget(self.col_name_input)
        col_layout.addLayout(v_col_name)

        v_col_voice = QVBoxLayout()
        v_col_voice.addWidget(QLabel("声音ID列 (如 S):"))
        self.col_voice_input = QLineEdit()
        self.col_voice_input.setPlaceholderText("S")
        v_col_voice.addWidget(self.col_voice_input)
        col_layout.addLayout(v_col_voice)

        v_col_img = QVBoxLayout()
        v_col_img.addWidget(QLabel("Google Drive 文件列 (如 U):"))
        self.col_img_input = QLineEdit()
        self.col_img_input.setPlaceholderText("U")
        v_col_img.addWidget(self.col_img_input)
        col_layout.addLayout(v_col_img)

        layout_sheet.addLayout(col_layout)
        group_sheet.setLayout(layout_sheet)
        main_layout.addWidget(group_sheet)

        group_task = QGroupBox("3. 任务与输出设置")
        layout_task = QVBoxLayout()
        layout_task.addWidget(QLabel("输出文件夹 (拖拽目录):"))
        self.dir_input = DragDropLineEdit(is_folder=True)
        layout_task.addWidget(self.dir_input)

        task_h_layout = QHBoxLayout()
        self.cb_txt = QCheckBox("导出 TXT 文本")
        self.cb_txt.setChecked(True)

        self.cb_wrap = QCheckBox("对文案执行自动断行")
        self.cb_wrap.setChecked(True)

        wrap_layout = QHBoxLayout()
        wrap_layout.addWidget(QLabel("断行最大字符:"))
        self.spin_width = QSpinBox()
        self.spin_width.setRange(5, 200)
        self.spin_width.setValue(18)
        wrap_layout.addWidget(self.spin_width)
        wrap_layout.addStretch()

        task_h_layout.addWidget(self.cb_txt)
        task_h_layout.addWidget(self.cb_wrap)
        task_h_layout.addLayout(wrap_layout)
        layout_task.addLayout(task_h_layout)

        task_media_layout = QHBoxLayout()
        self.cb_audio = QCheckBox("调用 ElevenLabs 生成 MP3")
        self.cb_audio.setChecked(True)
        self.cb_img = QCheckBox("使用 rclone 下载 Google Drive 文件")
        self.cb_img.setChecked(True)
        task_media_layout.addWidget(self.cb_audio)
        task_media_layout.addWidget(self.cb_img)

        layout_task.addLayout(task_media_layout)
        group_task.setLayout(layout_task)
        main_layout.addWidget(group_task)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        self.btn_run = QPushButton("🚀 开始执行全自动流水线")
        self.btn_run.setStyleSheet(
            "padding: 12px; font-weight: bold; font-size: 14px; background-color: #2e8b57; color: white;")
        self.btn_run.clicked.connect(self.start_generation)
        main_layout.addWidget(self.btn_run)

        main_layout.addWidget(QLabel("运行日志:"))
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        main_layout.addWidget(self.log_output, 1)

        self.setLayout(main_layout)

    def load_config(self):
        config_dir = os.path.dirname(self.config_file)
        if config_dir and not os.path.exists(config_dir):
            try:
                os.makedirs(config_dir, exist_ok=True)
            except Exception as e:
                self.log(f"⚠️ 创建配置文件夹失败: {e}")
                return

        if not os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump({}, f, ensure_ascii=False, indent=4)
            except Exception as e:
                self.log(f"⚠️ 创建初始配置文件失败: {e}")
                return

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self.api_input.setText(config.get("api_key", ""))
                self.cred_input.setText(config.get("cred_path", ""))
                self.sheet_id_input.setText(config.get("sheet_id", ""))
                self.sheet_name_input.setText(config.get("sheet_name", "Sheet1"))
                self.dir_input.setText(config.get("output_dir", ""))
                self.rows_input.setText(config.get("rows_str", ""))

                self.col_text_input.setText(config.get("col_text", "G"))
                self.col_name_input.setText(config.get("col_name", "O"))
                self.col_voice_input.setText(config.get("col_voice", "S"))
                self.col_img_input.setText(config.get("col_img", "U"))

                self.cb_txt.setChecked(config.get("task_txt", True))
                self.cb_wrap.setChecked(config.get("task_wrap", True))
                self.spin_width.setValue(config.get("wrap_width", 18))
                self.cb_audio.setChecked(config.get("task_audio", True))
                self.cb_img.setChecked(config.get("task_img", True))

        except Exception as e:
            self.log(f"⚠️ 读取配置文件失败: {e}")

    def save_config(self):
        config = {
            "api_key": self.api_input.text().strip(),
            "cred_path": self.cred_input.text().strip(),
            "sheet_id": self.sheet_id_input.text().strip(),
            "sheet_name": self.sheet_name_input.text().strip(),
            "output_dir": self.dir_input.text().strip(),
            "rows_str": self.rows_input.text().strip(),
            "col_text": self.col_text_input.text().strip().upper() or "G",
            "col_name": self.col_name_input.text().strip().upper() or "O",
            "col_voice": self.col_voice_input.text().strip().upper() or "S",
            "col_img": self.col_img_input.text().strip().upper() or "U",
            "task_txt": self.cb_txt.isChecked(),
            "task_wrap": self.cb_wrap.isChecked(),
            "wrap_width": self.spin_width.value(),
            "task_audio": self.cb_audio.isChecked(),
            "task_img": self.cb_img.isChecked()
        }
        try:
            config_dir = os.path.dirname(self.config_file)
            if config_dir and not os.path.exists(config_dir):
                os.makedirs(config_dir, exist_ok=True)

            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            self.log(f"⚠️ 保存配置文件失败: {e}")

    def closeEvent(self, event):
        self.save_config()
        event.accept()

    def log(self, message):
        self.log_output.append(message)
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def update_progress(self, done, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(done)

    def start_generation(self):
        self.save_config()

        config_data = {
            "api_key": self.api_input.text().strip(),
            "cred_path": self.cred_input.text().strip(),
            "sheet_id": self.sheet_id_input.text().strip(),
            "sheet_name": self.sheet_name_input.text().strip(),
            "output_dir": self.dir_input.text().strip(),
            "rows_str": self.rows_input.text().strip(),
            "col_text": self.col_text_input.text().strip().upper() or "G",
            "col_name": self.col_name_input.text().strip().upper() or "O",
            "col_voice": self.col_voice_input.text().strip().upper() or "S",
            "col_img": self.col_img_input.text().strip().upper() or "U",
            "task_txt": self.cb_txt.isChecked(),
            "task_wrap": self.cb_wrap.isChecked(),
            "wrap_width": self.spin_width.value(),
            "task_audio": self.cb_audio.isChecked(),
            "task_img": self.cb_img.isChecked()
        }

        if not all([config_data["cred_path"], config_data["sheet_id"], config_data["sheet_name"],
                    config_data["output_dir"], config_data["rows_str"]]):
            QMessageBox.warning(self, "信息缺失", "请填写完整基础信息 (凭证、表格ID、工作表、行号、输出路径)！")
            return

        if config_data["task_audio"] and not config_data["api_key"]:
            QMessageBox.warning(self, "信息缺失", "若要生成音频，ElevenLabs API Key 必填！")
            return

        if not os.path.exists(config_data["cred_path"]):
            QMessageBox.warning(self, "错误", "Google 凭证文件不存在！")
            return

        if not os.path.exists(config_data["output_dir"]):
            QMessageBox.warning(self, "错误", "输出文件夹路径不存在！")
            return

        if not (config_data["task_txt"] or config_data["task_audio"] or config_data["task_img"]):
            QMessageBox.information(self, "提示", "您至少需要勾选一项输出任务 (TXT、MP3 或 Google Drive 文件)。")
            return

        self.btn_run.setEnabled(False)
        self.log_output.clear()
        self.progress_bar.setValue(0)

        self.thread = UnifiedGeneratorThread(config_data)
        self.thread.log_signal.connect(self.log)
        self.thread.progress_signal.connect(self.update_progress)
        self.thread.finished_signal.connect(self.thread_finished)
        self.thread.start()

    def thread_finished(self):
        self.btn_run.setEnabled(True)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
