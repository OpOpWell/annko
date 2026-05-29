"""
SSK出来形測定 OCR GUI v2.0
改善版

改善内容:
- APIキー .env対応
- 起動クラッシュ防止
- chat.completions 統一
- GUI安全化
- ログ保存
- プログレスバー
- OCR結果マージ
"""

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from openai import OpenAI
from dotenv import load_dotenv

import base64
import os
import csv
import re
import json
import threading
import traceback
import logging

from datetime import datetime
from pathlib import Path


# ==================================================
# .env 読込
# ==================================================

load_dotenv()

# ==================================================
# OpenAI Client
# ==================================================

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# ==================================================
# ログ設定
# ==================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            "ssk_ocr.log",
            encoding="utf-8"
        )
    ],
)

log = logging.getLogger(__name__)

# ==================================================
# GUI
# ==================================================


class OCRGUI(tk.Tk):

    def __init__(self):

        super().__init__()

        self.title("SSK出来形OCR GUI")
        self.geometry("1100x760")

        self.image_folder_var = tk.StringVar()
        self.output_folder_var = tk.StringVar()

        self.build_ui()

    # ------------------------------------------------

    def build_ui(self):

        frame = tk.LabelFrame(
            self,
            text="設定"
        )

        frame.pack(
            fill="x",
            padx=10,
            pady=10
        )

        # ------------------------------

        row1 = tk.Frame(frame)
        row1.pack(fill="x", pady=5)

        tk.Label(
            row1,
            text="画像フォルダ",
            width=14,
            anchor="w"
        ).pack(side="left")

        tk.Entry(
            row1,
            textvariable=self.image_folder_var,
            width=90
        ).pack(side="left", padx=5)

        tk.Button(
            row1,
            text="選択",
            command=self.select_image_folder
        ).pack(side="left")

        # ------------------------------

        row2 = tk.Frame(frame)
        row2.pack(fill="x", pady=5)

        tk.Label(
            row2,
            text="出力フォルダ",
            width=14,
            anchor="w"
        ).pack(side="left")

        tk.Entry(
            row2,
            textvariable=self.output_folder_var,
            width=90
        ).pack(side="left", padx=5)

        tk.Button(
            row2,
            text="選択",
            command=self.select_output_folder
        ).pack(side="left")

        # ------------------------------

        btn_frame = tk.Frame(self)
        btn_frame.pack(fill="x", padx=10)

        self.run_btn = tk.Button(
            btn_frame,
            text="OCR開始",
            command=self.start_ocr,
            bg="#1565c0",
            fg="white",
            width=20,
            height=2,
            font=("", 11, "bold")
        )

        self.run_btn.pack(side="left", padx=5)

        tk.Button(
            btn_frame,
            text="出力フォルダを開く",
            command=self.open_output_folder,
            width=20,
            height=2
        ).pack(side="left", padx=5)

        # ------------------------------

        self.progress = ttk.Progressbar(
            self,
            orient="horizontal",
            mode="determinate"
        )

        self.progress.pack(
            fill="x",
            padx=10,
            pady=10
        )

        # ------------------------------

        self.log_text = scrolledtext.ScrolledText(
            self,
            width=130,
            height=35
        )

        self.log_text.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=10
        )

    # ------------------------------------------------

    def log(self, text):

        self.log_text.insert(
            tk.END,
            str(text) + "\n"
        )

        self.log_text.see(tk.END)

        log.info(text)

    # ------------------------------------------------

    def select_image_folder(self):

        folder = filedialog.askdirectory()

        if folder:
            self.image_folder_var.set(folder)

    # ------------------------------------------------

    def select_output_folder(self):

        folder = filedialog.askdirectory()

        if folder:
            self.output_folder_var.set(folder)

    # ------------------------------------------------

    def start_ocr(self):

        image_folder = self.image_folder_var.get().strip()
        output_folder = self.output_folder_var.get().strip()

        if not os.path.isdir(image_folder):

            messagebox.showerror(
                "エラー",
                "画像フォルダが存在しません"
            )

            return

        if not output_folder:

            messagebox.showerror(
                "エラー",
                "出力フォルダを指定してください"
            )

            return

        self.run_btn.config(state="disabled")

        self.log_text.delete("1.0", tk.END)

        thread = threading.Thread(
            target=self.run_ocr,
            daemon=True
        )

        thread.start()

    # ------------------------------------------------

    def run_ocr(self):

        try:

            image_folder = self.image_folder_var.get().strip()
            output_folder = self.output_folder_var.get().strip()

            ok_dir = os.path.join(output_folder, "ok")
            warning_dir = os.path.join(output_folder, "warning")
            error_dir = os.path.join(output_folder, "error")

            os.makedirs(ok_dir, exist_ok=True)
            os.makedirs(warning_dir, exist_ok=True)
            os.makedirs(error_dir, exist_ok=True)

            image_files = []

            for ext in ["*.jpg", "*.jpeg", "*.png", "*.JPG"]:

                image_files.extend(
                    Path(image_folder).glob(ext)
                )

            total = len(image_files)

            self.progress["maximum"] = total

            self.log("================================")
            self.log("SSK OCR 開始")
            self.log(f"対象枚数: {total}")
            self.log("================================")

            for idx, image_path in enumerate(image_files):

                self.progress["value"] = idx + 1

                self.log("")
                self.log(f"[{idx+1}/{total}] {image_path.name}")

                try:

                    result = self.gpt_ocr(image_path)

                    self.log(json.dumps(
                        result,
                        ensure_ascii=False,
                        indent=2
                    ))

                    csv_path = os.path.join(
                        ok_dir,
                        image_path.stem + ".csv"
                    )

                    self.save_csv(
                        csv_path,
                        result
                    )

                    self.log(f"保存: {csv_path}")

                except Exception as e:

                    self.log("OCR失敗")
                    self.log(str(e))

                    traceback.print_exc()

            self.after(
                0,
                lambda: messagebox.showinfo(
                    "完了",
                    "OCR処理完了"
                )
            )

        except Exception as e:

            self.after(
                0,
                lambda: messagebox.showerror(
                    "エラー",
                    str(e)
                )
            )

        finally:

            self.after(
                0,
                lambda: self.run_btn.config(
                    state="normal"
                )
            )

    # ------------------------------------------------

    def gpt_ocr(self, image_path):

        with open(image_path, "rb") as f:

            base64_image = base64.b64encode(
                f.read()
            ).decode("utf-8")

        response = client.chat.completions.create(

            model="gpt-4.1-mini",

            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """
この出来形管理写真から
測点番号と実測値をJSONで返してください。

形式:
[
  {
    "no": 1,
    "value": 1.402
  }
]
"""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],

            response_format={
                "type": "json_object"
            }
        )

        text = response.choices[0].message.content

        return json.loads(text)

    # ------------------------------------------------

    def save_csv(self, path, result):

        with open(
            path,
            "w",
            newline="",
            encoding="utf-8-sig"
        ) as f:

            writer = csv.writer(f)

            writer.writerow([
                "No",
                "実測値"
            ])

            if isinstance(result, dict):

                result = result.get(
                    "values",
                    []
                )

            for row in result:

                writer.writerow([
                    row.get("no"),
                    row.get("value")
                ])

    # ------------------------------------------------

    def open_output_folder(self):

        folder = self.output_folder_var.get().strip()

        if os.path.exists(folder):

            os.startfile(folder)

        else:

            messagebox.showwarning(
                "警告",
                "出力フォルダが存在しません"
            )


# ==================================================
# Main
# ==================================================

if __name__ == "__main__":

    app = OCRGUI()

    app.mainloop()





















































