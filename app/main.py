import os
import sys
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk


BASE_DIR = r"C:\Users\user\foolder\杏子"

PHOTO_CORE_SCRIPT = os.path.join(BASE_DIR, "杏子526ees.py")
SSK_GUI_SCRIPT = os.path.join(BASE_DIR, "杏子子_gui.py")
CONFIG_PATH = os.path.join(BASE_DIR, "config.yml")


def write_photo_config(base_folder, input_folder, model, max_workers, hash_threshold):
    text = f'''# 工事写真整理システム 設定

base_folder: "{base_folder.replace("\\", "\\\\")}"
input_folder: "{input_folder.replace("\\", "\\\\")}"

openai_model: "{model}"

max_workers: {max_workers}
hash_threshold: {hash_threshold}
'''
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(text)


class IntegratedGUI(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("杏子 統合GUI")
        self.geometry("1100x780")
        self.resizable(True, True)

        self.photo_process = None
        self.ssk_process = None

        self.build_ui()

    def build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        self.photo_tab = tk.Frame(notebook)
        self.ssk_tab = tk.Frame(notebook)

        notebook.add(self.photo_tab, text="写真分類・PHOTO.XML")
        notebook.add(self.ssk_tab, text="出来形OCR・デキスパートCSV")

        self.build_photo_tab()
        self.build_ssk_tab()

    def build_photo_tab(self):
        pad = {"padx": 10, "pady": 5}

        frame = tk.LabelFrame(self.photo_tab, text="写真分類設定")
        frame.pack(fill="x", **pad)

        self.base_folder_var = tk.StringVar(value=BASE_DIR)
        self.input_folder_var = tk.StringVar(value=r"C:\Users\user\OneDrive\hhh")
        self.model_var = tk.StringVar(value="gpt-4.1-mini")
        self.workers_var = tk.StringVar(value="5")
        self.hash_var = tk.StringVar(value="8")

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

        btn_frame = tk.Frame(self.photo_tab)
        btn_frame.pack(fill="x", **pad)

        self.photo_run_btn = tk.Button(
            btn_frame,
            text="写真分類 実行",
            command=self.start_photo_run,
            bg="#2e7d32",
            fg="white",
            height=2,
            width=20,
            font=("", 11, "bold"),
        )
        self.photo_run_btn.pack(side="left", padx=5)

        tk.Button(
            btn_frame,
            text="出力フォルダを開く",
            command=self.open_photo_output,
            height=2,
            width=18,
        ).pack(side="left", padx=5)

        tk.Button(
            btn_frame,
            text="config.yml保存",
            command=self.save_photo_config_only,
            height=2,
            width=18,
        ).pack(side="left", padx=5)

        tk.Button(
            btn_frame,
            text="出来形OCR・CSV作成",
            command=self.start_ssk_gui,
            bg="#1565c0",
            fg="white",
            height=2,
            width=22,
            font=("", 10, "bold"),
        ).pack(side="left", padx=5)

        self.photo_status_var = tk.StringVar(value="待機中")
        tk.Label(self.photo_tab, textvariable=self.photo_status_var, anchor="w").pack(fill="x", padx=10)

        self.photo_log_text = scrolledtext.ScrolledText(self.photo_tab, width=130, height=34)
        self.photo_log_text.pack(fill="both", expand=True, padx=10, pady=8)

    def add_folder_row(self, parent, label, var, command):
        row = tk.Frame(parent)
        row.pack(fill="x", pady=4)

        tk.Label(row, text=label, width=12, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=var, width=95).pack(side="left", padx=4)
        tk.Button(row, text="選択", command=command).pack(side="left")

    def select_base_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.base_folder_var.set(folder)

    def select_input_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.input_folder_var.set(folder)

    def photo_log(self, text):
        self.photo_log_text.insert(tk.END, str(text) + "\n")
        self.photo_log_text.see(tk.END)

    def write_current_photo_config(self):
        base_folder = self.base_folder_var.get().strip()
        input_folder = self.input_folder_var.get().strip()
        model = self.model_var.get().strip()

        max_workers = int(self.workers_var.get().strip())
        hash_threshold = int(self.hash_var.get().strip())

        if not os.path.isdir(base_folder):
            raise ValueError("作業フォルダが存在しません")

        if not os.path.isdir(input_folder):
            raise ValueError("写真フォルダが存在しません")

        write_photo_config(
            base_folder,
            input_folder,
            model,
            max_workers,
            hash_threshold,
        )

    def save_photo_config_only(self):
        try:
            self.write_current_photo_config()
            messagebox.showinfo("保存完了", f"config.yml を保存しました。\n{CONFIG_PATH}")
        except Exception as e:
            messagebox.showerror("エラー", str(e))

    def start_photo_run(self):
        if not os.path.exists(PHOTO_CORE_SCRIPT):
            messagebox.showerror(
                "エラー",
                f"写真分類本体が見つかりません。\n{PHOTO_CORE_SCRIPT}",
            )
            return

        try:
            self.write_current_photo_config()
        except Exception as e:
            messagebox.showerror("設定エラー", str(e))
            return

        self.photo_run_btn.config(state="disabled")
        self.photo_status_var.set("写真分類 実行中...")
        self.photo_log_text.delete("1.0", tk.END)

        thread = threading.Thread(target=self.run_photo_core_script, daemon=True)
        thread.start()

    def run_photo_core_script(self):
        try:
            self.after(0, self.photo_log, "写真分類を開始します")
            self.after(0, self.photo_log, f"分類本体: {PHOTO_CORE_SCRIPT}")
            self.after(0, self.photo_log, f"設定: {CONFIG_PATH}")
            self.after(0, self.photo_log, "")

            self.photo_process = subprocess.Popen(
                [sys.executable, PHOTO_CORE_SCRIPT],
                cwd=BASE_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            for line in self.photo_process.stdout:
                self.after(0, self.photo_log, line.rstrip())

            code = self.photo_process.wait()

            if code == 0:
                self.after(0, self.photo_status_var.set, "写真分類 完了")
                self.after(0, messagebox.showinfo, "完了", "写真分類が完了しました")
            else:
                self.after(0, self.photo_status_var.set, "写真分類 エラー")
                self.after(0, messagebox.showerror, "エラー", f"終了コード: {code}")

        except Exception as e:
            self.after(0, self.photo_status_var.set, "写真分類 エラー")
            self.after(0, messagebox.showerror, "エラー", str(e))

        finally:
            self.after(0, self.photo_run_btn.config, {"state": "normal"})

    def open_photo_output(self):
        folder = os.path.join(self.base_folder_var.get().strip(), "selected_photos", "PHOTO")

        if os.path.exists(folder):
            os.startfile(folder)
        else:
            messagebox.showwarning("未作成", f"出力フォルダがまだありません。\n{folder}")

    def build_ssk_tab(self):
        pad = {"padx": 10, "pady": 8}

        info = tk.Label(
            self.ssk_tab,
            text=(
                "出来形OCR・デキスパートCSV作成を起動します。\n"
                "実測値シート写真から田番別CSVを作成します。"
            ),
            anchor="w",
            justify="left",
        )
        info.pack(fill="x", **pad)

        btn_frame = tk.Frame(self.ssk_tab)
        btn_frame.pack(fill="x", **pad)

        self.ssk_run_btn = tk.Button(
            btn_frame,
            text="出来形OCR・CSV作成",
            command=self.start_ssk_gui,
            bg="#1565c0",
            fg="white",
            height=2,
            width=24,
            font=("", 11, "bold"),
        )
        self.ssk_run_btn.pack(side="left", padx=5)

        tk.Button(
            btn_frame,
            text="杏子フォルダを開く",
            command=lambda: os.startfile(BASE_DIR),
            height=2,
            width=18,
        ).pack(side="left", padx=5)

        self.ssk_status_var = tk.StringVar(value="待機中")
        tk.Label(self.ssk_tab, textvariable=self.ssk_status_var, anchor="w").pack(fill="x", padx=10)

        self.ssk_log_text = scrolledtext.ScrolledText(self.ssk_tab, width=130, height=34)
        self.ssk_log_text.pack(fill="both", expand=True, padx=10, pady=8)

        self.ssk_log("SSK OCR GUIファイル:")
        self.ssk_log(SSK_GUI_SCRIPT)

    def ssk_log(self, text):
        self.ssk_log_text.insert(tk.END, str(text) + "\n")
        self.ssk_log_text.see(tk.END)

    def start_ssk_gui(self):
        if not os.path.exists(SSK_GUI_SCRIPT):
            messagebox.showerror(
                "エラー",
                f"SSK OCR GUI が見つかりません。\n{SSK_GUI_SCRIPT}\n\nファイル名を確認してください。",
            )
            return

        try:
            self.ssk_status_var.set("SSK OCR GUI 起動中...")
            self.ssk_log("")
            self.ssk_log("SSK OCR GUIを起動します")
            self.ssk_log(SSK_GUI_SCRIPT)

            self.ssk_process = subprocess.Popen(
                [sys.executable, SSK_GUI_SCRIPT],
                cwd=BASE_DIR,
            )

            self.ssk_status_var.set("SSK OCR GUI 起動済み")

        except Exception as e:
            self.ssk_status_var.set("SSK OCR GUI 起動エラー")
            messagebox.showerror("エラー", str(e))


if __name__ == "__main__":
    app = IntegratedGUI()
    app.mainloop()






