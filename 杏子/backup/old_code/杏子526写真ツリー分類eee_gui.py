import os
import sys
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from pathlib import Path


BASE_DIR = r"C:\Users\user\foolder\杏子"

CORE_SCRIPT = os.path.join(BASE_DIR, "杏子526ees.py")
CONFIG_PATH = os.path.join(BASE_DIR, "config.yml")


def write_config(base_folder, input_folder, model, max_workers, hash_threshold):
    text = f'''# 工事写真整理システム 設定

base_folder: "{base_folder.replace("\\", "\\\\")}"
input_folder: "{input_folder.replace("\\", "\\\\")}"

openai_model: "{model}"

max_workers: {max_workers}
hash_threshold: {hash_threshold}
'''
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(text)


class PhotoOrganizerGUI(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("杏子 写真分類GUI")
        self.geometry("980x720")

        self.base_folder_var = tk.StringVar(value=BASE_DIR)
        self.input_folder_var = tk.StringVar(value=r"C:\Users\user\OneDrive\hhh")
        self.model_var = tk.StringVar(value="gpt-4.1-mini")
        self.workers_var = tk.StringVar(value="5")
        self.hash_var = tk.StringVar(value="8")

        self.process = None

        self.build_ui()

    def build_ui(self):
        pad = {"padx": 10, "pady": 5}

        frame = tk.LabelFrame(self, text="設定")
        frame.pack(fill="x", **pad)

        self.add_folder_row(frame, "作業フォルダ", self.base_folder_var, self.select_base_folder)
        self.add_folder_row(frame, "写真フォルダ", self.input_folder_var, self.select_input_folder)

        row = tk.Frame(frame)
        row.pack(fill="x", pady=4)

        tk.Label(row, text="AIモデル", width=12, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=self.model_var, width=25).pack(side="left", padx=4)

        tk.Label(row, text="並列数", width=8, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=self.workers_var, width=8).pack(side="left", padx=4)

        tk.Label(row, text="重複判定", width=8, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=self.hash_var, width=8).pack(side="left", padx=4)

        btn_frame = tk.Frame(self)
        btn_frame.pack(fill="x", **pad)

        self.run_btn = tk.Button(
            btn_frame,
            text="写真分類 実行",
            command=self.start_run,
            bg="#2e7d32",
            fg="white",
            height=2,
            width=20,
            font=("", 11, "bold"),
        )
        self.run_btn.pack(side="left", padx=5)

        tk.Button(
            btn_frame,
            text="出力フォルダを開く",
            command=self.open_output_folder,
            height=2,
            width=18,
        ).pack(side="left", padx=5)

        tk.Button(
            btn_frame,
            text="config.ymlを保存",
            command=self.save_config_only,
            height=2,
            width=18,
        ).pack(side="left", padx=5)

        self.status_var = tk.StringVar(value="待機中")
        tk.Label(self, textvariable=self.status_var, anchor="w").pack(fill="x", padx=10)

        self.log_text = scrolledtext.ScrolledText(self, width=120, height=32)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=8)

    def add_folder_row(self, parent, label, var, command):
        row = tk.Frame(parent)
        row.pack(fill="x", pady=4)

        tk.Label(row, text=label, width=12, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=var, width=90).pack(side="left", padx=4)
        tk.Button(row, text="選択", command=command).pack(side="left")

    def select_base_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.base_folder_var.set(folder)

    def select_input_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.input_folder_var.set(folder)

    def log(self, text):
        self.log_text.insert(tk.END, str(text) + "\n")
        self.log_text.see(tk.END)

    def save_config_only(self):
        try:
            self.write_current_config()
            messagebox.showinfo("保存完了", f"config.yml を保存しました。\n{CONFIG_PATH}")
        except Exception as e:
            messagebox.showerror("エラー", str(e))

    def write_current_config(self):
        base_folder = self.base_folder_var.get().strip()
        input_folder = self.input_folder_var.get().strip()
        model = self.model_var.get().strip()

        max_workers = int(self.workers_var.get().strip())
        hash_threshold = int(self.hash_var.get().strip())

        if not os.path.isdir(base_folder):
            raise ValueError("作業フォルダが存在しません")

        if not os.path.isdir(input_folder):
            raise ValueError("写真フォルダが存在しません")

        write_config(
            base_folder,
            input_folder,
            model,
            max_workers,
            hash_threshold,
        )

    def start_run(self):
        if not os.path.exists(CORE_SCRIPT):
            messagebox.showerror(
                "エラー",
                f"分類本体が見つかりません。\n{CORE_SCRIPT}\n\nCORE_SCRIPT の名前を確認してください。",
            )
            return

        try:
            self.write_current_config()
        except Exception as e:
            messagebox.showerror("設定エラー", str(e))
            return

        self.run_btn.config(state="disabled")
        self.status_var.set("実行中...")
        self.log_text.delete("1.0", tk.END)

        thread = threading.Thread(target=self.run_core_script, daemon=True)
        thread.start()

    def run_core_script(self):
        try:
            self.log("写真分類を開始します")
            self.log(f"分類本体: {CORE_SCRIPT}")
            self.log(f"設定: {CONFIG_PATH}")
            self.log("")

            cmd = [sys.executable, CORE_SCRIPT]

            self.process = subprocess.Popen(
                cmd,
                cwd=BASE_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            for line in self.process.stdout:
                self.after(0, self.log, line.rstrip())

            code = self.process.wait()

            if code == 0:
                self.after(0, self.status_var.set, "完了")
                self.after(0, messagebox.showinfo, "完了", "写真分類が完了しました")
            else:
                self.after(0, self.status_var.set, "エラー")
                self.after(0, messagebox.showerror, "エラー", f"終了コード: {code}")

        except Exception as e:
            self.after(0, self.status_var.set, "エラー")
            self.after(0, messagebox.showerror, "エラー", str(e))

        finally:
            self.after(0, self.run_btn.config, {"state": "normal"})

    def open_output_folder(self):
        folder = os.path.join(self.base_folder_var.get().strip(), "selected_photos", "PHOTO")

        if os.path.exists(folder):
            os.startfile(folder)
        else:
            messagebox.showwarning("未作成", f"出力フォルダがまだありません。\n{folder}")


if __name__ == "__main__":

    print("GUI開始")

    try:

        app = PhotoOrganizerGUI()

        print("GUI生成OK")

        app.mainloop()

    except Exception as e:

        print("GUIエラー")
        print(e)

        input("Enterで終了")