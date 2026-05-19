from openai import OpenAI
import os
import glob
import shutil
import base64
import json
import re
import cv2
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

client = OpenAI()

# =========================
# 設定
# =========================

PYTHON_EXE = r"C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe"

ANKO_SCRIPT = r"C:\Users\user\foolder\杏子\杏子_cli.py"

BLUR_LIMIT = 120


# =========================
# ブレ判定
# =========================

def blur_score(image_path):

    img = cv2.imread(image_path)

    if img is None:
        return 0

    gray = cv2.cvtColor(
        img,
        cv2.COLOR_BGR2GRAY
    )

    return cv2.Laplacian(
        gray,
        cv2.CV_64F
    ).var()


# =========================
# GPT写真分類
# =========================

def gpt_photo_check(image_path):

    with open(image_path, "rb") as f:

        base64_image = base64.b64encode(
            f.read()
        ).decode("utf-8")

    response = client.responses.create(

        model="gpt-4.1-mini",

        temperature=0,

        input=[
            {
                "role": "user",

                "content": [

                    {
                        "type": "input_text",

                        "text": """
あなたは工事写真分類AIです。

必ずJSONのみ返してください。
説明文は禁止です。

分類候補:
- 出来形測定写真
- 作業風景
- 黒板写真
- 要確認
- 除外

重要:
測定表
手書き数字
田番
測点番号
平均値
Xmax
Xmin

これらがあれば必ず
「出来形測定写真」

JSON形式:
{
  "category": "出来形測定写真",
  "reason": "測定表と数字があるため",
  "has_board": true,
  "has_numbers": true,
  "has_measurement_table": true,
  "has_worker": false,
  "has_machine": false,
  "useful": true
}
"""
                    },

                    {
                        "type": "input_image",

                        "image_url":
                        f"data:image/jpeg;base64,{base64_image}"
                    }
                ]
            }
        ]
    )

    text = response.output_text.strip()

    print()
    print("GPT生返答")
    print(text)

    text = text.replace("```json", "")
    text = text.replace("```", "")

    match = re.search(
        r"\{.*\}",
        text,
        re.DOTALL
    )

    if not match:

        return {
            "category": "要確認",
            "reason": "JSON取得失敗",
            "raw": text
        }

    try:

        result = json.loads(
            match.group()
        )

        return result

    except Exception as e:

        return {
            "category": "要確認",
            "reason": f"JSON変換失敗: {e}",
            "raw": text
        }


# =========================
# 安全コピー
# =========================

def safe_copy(src, dst_folder):

    os.makedirs(
        dst_folder,
        exist_ok=True
    )

    name = os.path.basename(src)

    dst = os.path.join(
        dst_folder,
        name
    )

    if os.path.exists(dst):

        base, ext = os.path.splitext(name)

        count = 1

        while True:

            new_name = f"{base}_{count}{ext}"

            dst = os.path.join(
                dst_folder,
                new_name
            )

            if not os.path.exists(dst):
                break

            count += 1

    shutil.copy2(src, dst)


# =========================
# GUI
# =========================

class PhotoCleanerGUI:

    def __init__(self, root):

        self.root = root

        self.root.title(
            "AI写真整理 OCR自動接続"
        )

        self.root.geometry("1000x760")

        self.input_folder = tk.StringVar(
            value=r"C:\Users\user\foolder\634\images_all"
        )

        self.output_folder = tk.StringVar(
            value=r"C:\Users\user\foolder\634\photo_sorted"
        )

        self.auto_ocr = tk.BooleanVar(value=True)

        self.blur_check = tk.BooleanVar(value=True)

        self.ocr_check = tk.BooleanVar(value=True)

        self.create_widgets()

    # =========================

    def create_widgets(self):

        tk.Label(
            self.root,
            text="入力フォルダ"
        ).pack(anchor="w", padx=10, pady=(10, 0))

        frame1 = tk.Frame(self.root)

        frame1.pack(fill="x", padx=10)

        tk.Entry(
            frame1,
            textvariable=self.input_folder
        ).pack(side="left", fill="x", expand=True)

        tk.Button(
            frame1,
            text="選択",
            command=self.select_input
        ).pack(side="left", padx=5)

        tk.Label(
            self.root,
            text="出力フォルダ"
        ).pack(anchor="w", padx=10, pady=(10, 0))

        frame2 = tk.Frame(self.root)

        frame2.pack(fill="x", padx=10)

        tk.Entry(
            frame2,
            textvariable=self.output_folder
        ).pack(side="left", fill="x", expand=True)

        tk.Button(
            frame2,
            text="選択",
            command=self.select_output
        ).pack(side="left", padx=5)

        option_frame = tk.Frame(self.root)

        option_frame.pack(anchor="w", padx=10, pady=10)

        tk.Checkbutton(
            option_frame,
            text="ピンボケ除外",
            variable=self.blur_check
        ).pack(side="left", padx=5)

        tk.Checkbutton(
            option_frame,
            text="OCR自動実行",
            variable=self.auto_ocr
        ).pack(side="left", padx=5)

        tk.Checkbutton(
            option_frame,
            text="OCR信頼度チェック",
            variable=self.ocr_check
        ).pack(side="left", padx=5)

        tk.Button(
            self.root,
            text="AI写真整理開始",
            command=self.start_thread,
            height=2,
            bg="#d9ead3"
        ).pack(fill="x", padx=10, pady=10)

        self.log = tk.Text(
            self.root,
            height=35
        )

        self.log.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=10
        )

    # =========================

    def select_input(self):

        folder = filedialog.askdirectory()

        if folder:
            self.input_folder.set(folder)

    # =========================

    def select_output(self):

        folder = filedialog.askdirectory()

        if folder:
            self.output_folder.set(folder)

    # =========================

    def write_log(self, text=""):

        self.log.insert(
            tk.END,
            text + "\n"
        )

        self.log.see(tk.END)

        self.root.update_idletasks()

    # =========================

    def start_thread(self):

        thread = threading.Thread(
            target=self.run_process
        )

        thread.daemon = True

        thread.start()

    # =========================

    def run_process(self):

        try:

            self.process_photos()

            messagebox.showinfo(
                "完了",
                "AI写真整理が完了しました"
            )

        except Exception as e:

            self.write_log(f"エラー: {e}")

            messagebox.showerror(
                "エラー",
                str(e)
            )

    # =========================

    def process_photos(self):

        input_folder = self.input_folder.get()

        output_folder = self.output_folder.get()

        measurement_folder = os.path.join(
            output_folder,
            "出来形測定写真"
        )

        work_folder = os.path.join(
            output_folder,
            "作業風景"
        )

        board_folder = os.path.join(
            output_folder,
            "黒板写真"
        )

        check_folder = os.path.join(
            output_folder,
            "要確認"
        )

        ng_folder = os.path.join(
            output_folder,
            "除外"
        )

        folders = [
            measurement_folder,
            work_folder,
            board_folder,
            check_folder,
            ng_folder
        ]

        for folder in folders:

            os.makedirs(
                folder,
                exist_ok=True
            )

            files = glob.glob(
                os.path.join(folder, "*")
            )

            for file in files:
                os.remove(file)

        self.write_log("AI写真整理開始")

        image_files = [

            f for f in os.listdir(input_folder)

            if f.lower().endswith(
                (
                    ".jpg",
                    ".jpeg",
                    ".png"
                )
            )
        ]

        self.write_log(
            f"対象枚数: {len(image_files)}"
        )

        for image_name in image_files:

            image_path = os.path.join(
                input_folder,
                image_name
            )

            self.write_log("")
            self.write_log(f"処理中: {image_name}")

            if self.blur_check.get():

                score = blur_score(image_path)

                self.write_log(
                    f"ブレスコア: {score:.2f}"
                )

                if score < BLUR_LIMIT:

                    self.write_log(
                        "保存先: 除外（ピンボケ）"
                    )

                    safe_copy(
                        image_path,
                        ng_folder
                    )

                    continue

            result = gpt_photo_check(image_path)

            category = result.get(
                "category",
                "要確認"
            )

            reason = result.get(
                "reason",
                ""
            )

            self.write_log(f"分類: {category}")
            self.write_log(f"理由: {reason}")
            self.write_log(f"GPT結果: {result}")

            if category == "出来形測定写真":

                self.write_log(
                    "保存先: 出来形測定写真"
                )

                safe_copy(
                    image_path,
                    measurement_folder
                )

            elif category == "作業風景":

                self.write_log(
                    "保存先: 作業風景"
                )

                safe_copy(
                    image_path,
                    work_folder
                )

            elif category == "黒板写真":

                self.write_log(
                    "保存先: 黒板写真"
                )

                safe_copy(
                    image_path,
                    board_folder
                )

            elif category == "除外":

                self.write_log(
                    "保存先: 除外"
                )

                safe_copy(
                    image_path,
                    ng_folder
                )

            else:

                self.write_log(
                    "保存先: 要確認"
                )

                safe_copy(
                    image_path,
                    check_folder
                )

        self.write_log("")
        self.write_log("AI写真整理完了")

        self.write_log(
            f"出力先: {output_folder}"
        )

        if self.auto_ocr.get():

            if self.ocr_check.get():

                self.write_log("")
                self.write_log("OCR信頼度チェック: ON")

            else:

                self.write_log("")
                self.write_log("OCR信頼度チェック: OFF")

            self.write_log("")
            self.write_log("OCR自動接続開始")

            process = subprocess.Popen(
                [
                    PYTHON_EXE,
                    ANKO_SCRIPT
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="cp932",
                errors="ignore"
            )

            for line in process.stdout:

                line = line.rstrip()

                self.write_log(line)

            process.wait()

            self.write_log("OCR自動接続完了")


# =========================
# 起動
# =========================

if __name__ == "__main__":

    root = tk.Tk()

    

    app = PhotoCleanerGUI(root)

    root.mainloop()