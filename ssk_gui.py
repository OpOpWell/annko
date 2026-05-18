from openai import OpenAI
import base64
import os
import csv
import re
import json
import threading
import queue
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk

client = OpenAI()

expected_counts = {
    "19": 30,
    "18": 16,
    "17": 14,
    "16": 12,
    "15": 12,
    "14": 11,
    "13": 22,
    "12": 23,

    "11": 26,
    "10": 11,
    "9": 10,
    "8": 10,
    "7": 10,
    "6": 10,
    "5": 9,
    "4": 0,
    "3": 16,
    "2": 5,
    "1": 12
}

allowed_items = [
    "均平度",
    "幅",
    "厚さ",
    "基準高",
    "法長",
    "延長",
    "深さ",
    "天端高",
    "出来高",
    "掘削深",
    "盛土高"
]


def to_mm_text(value):
    try:
        return str(int(round(float(value) * 1000)))
    except:
        return ""


def gpt_ocr(image_path, model_name, log):

    with open(image_path, "rb") as f:
        base64_image = base64.b64encode(f.read()).decode("utf-8")

    response = client.responses.create(
        model=model_name,
        temperature=0,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": """
このSSK出来形測定写真から情報を読み取ってください。

重要:
- 田番は上部の「田番」欄の数字
- 大きく丸で書かれた手書き数字は田番にしない

測定項目は次の候補から選択してください。

- 均平度
- 幅
- 厚さ
- 基準高
- 法長
- 延長
- 深さ
- 天端高
- 出来高
- 掘削深
- 盛土高

必ず上記候補から選択すること。
候補に無い場合は「不明」を返すこと。

読む項目:
- 田番
- 工種
- 測定項目
- 面積
- 測定基準
- 規格値
- 社内目標値
- 平均値
- Xmax
- Xmin
- 番号と手書き実測値

条件:
- 番号と手書き実測値を対応させる
- 空欄は無視
- 実測値は1.300〜1.600程度
- 実測値は小数3桁
- JSONのみ返す
- 説明不要
- 推測しない
- 読めない値は空文字または除外

返却形式:
{
  "taban": "19",
  "work_type": "整地工",
  "measurement_item": "均平度",
  "area": "9750㎡",
  "standard": "10a当たり3点以上",
  "spec_value": "±50mm",
  "target_value": "±40mm",
  "average": "1.410",
  "xmax": "1.400",
  "xmin": "1.421",
  "values": [
    {"no": 1, "value": 1.418},
    {"no": 2, "value": 1.400}
  ]
}
"""
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{base64_image}"
                    }
                ]
            }
        ]
    )

    result_text = response.output_text.strip()

    log(f"\nGPT結果 ({model_name})")
    log(result_text)

    result_text = result_text.replace("```json", "")
    result_text = result_text.replace("```", "")

    match_json = re.search(r"\{.*\}", result_text, re.DOTALL)

    if not match_json:
        log("JSONが見つかりません")
        return {}

    try:
        return json.loads(match_json.group())
    except Exception as e:
        log("JSON変換失敗")
        log(e)
        return {}


def run_ocr(image_folder, output_folder, log, progress):

    os.makedirs(output_folder, exist_ok=True)

    csv_by_taban = {}
    meta_by_taban = {}
    log_lines = []

    def save_log(message):
        log(message)
        log_lines.append(str(message))

    image_files = sorted([
        f for f in os.listdir(image_folder)
        if f.lower().endswith((".png", ".jpg", ".jpeg"))
    ])

    total_images = len(image_files)

    if total_images == 0:
        save_log("画像がありません")
        return

    save_log("SSK写真 OCR → デキスパートCSV 自動作成開始")
    save_log(f"画像枚数: {total_images}枚")

    for index, image_name in enumerate(image_files, start=1):

        progress(index, total_images)

        image_path = os.path.join(image_folder, image_name)

        save_log(f"\n処理中 ({index}/{total_images}): {image_path}")

        result = gpt_ocr(image_path, "gpt-4.1-mini", save_log)

        taban = str(result.get("taban", "")).strip()

        work_type = str(result.get("work_type", "整地工")).strip()

        measurement_item = str(
            result.get("measurement_item", "不明")
        ).strip()

        if measurement_item not in allowed_items:
            measurement_item = "不明"

        design_value_raw = str(result.get("average", "")).strip()
        design_value = to_mm_text(design_value_raw)

        if work_type == "":
            work_type = "整地工"

        if taban not in expected_counts:
            taban = "未分類"

        if taban not in meta_by_taban:
            meta_by_taban[taban] = {
                "工種": work_type,
                "測定項目": measurement_item,
                "面積": result.get("area", ""),
                "測定基準": result.get("standard", ""),
                "規格値": result.get("spec_value", ""),
                "社内目標値": result.get("target_value", ""),
                "設計値": design_value,
                "Xmax": result.get("xmax", ""),
                "Xmin": result.get("xmin", ""),
            }

        values = result.get("values", [])
        value_dict = {}

        for item in values:
            try:
                no = int(item["no"])
                value = float(item["value"])
                value_dict[no] = value
            except:
                pass

        total_count = expected_counts.get(taban, 0)

        missing_no = []

        for no in range(1, total_count + 1):
            if no not in value_dict:
                missing_no.append(no)

        if missing_no:

            save_log("\n未読No検出")
            save_log(missing_no)
            save_log("\n4.1で再OCR実施")

            retry_result = gpt_ocr(image_path, "gpt-4.1", save_log)

            for item in retry_result.get("values", []):
                try:
                    no = int(item["no"])
                    value = float(item["value"])

                    if no not in value_dict:
                        value_dict[no] = value
                except:
                    pass

        if taban not in csv_by_taban:
            csv_by_taban[taban] = []

        for no in range(1, total_count + 1):

            point_name = f"No.{no}"

            if no in value_dict:
                value_text = to_mm_text(value_dict[no])
            else:
                value_text = ""

            csv_by_taban[taban].append([
                point_name,
                f"{work_type}田番{taban}",
                measurement_item,
                design_value,
                value_text
            ])

    for taban, rows in csv_by_taban.items():

        missing_no = []

        for row in rows:
            if row[4] == "":
                missing_no.append(row[0])

        if missing_no:
            save_log(f"\n未読あり: 田番{taban}")
            save_log("未読No: " + ", ".join(missing_no))
        else:
            save_log(f"\n未読なし: 田番{taban}")

        output_csv = os.path.join(output_folder, f"田番{taban}.csv")

        with open(output_csv, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)

            writer.writerow([
                "測点",
                "工種名",
                "測定項目",
                "設計値",
                "実測値1"
            ])

            writer.writerows(rows)

        save_log(f"CSV保存完了: {output_csv}")

    meta_csv = os.path.join(output_folder, "測定情報.csv")

    with open(meta_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)

        writer.writerow([
            "田番",
            "工種",
            "測定項目",
            "面積",
            "測定基準",
            "規格値",
            "社内目標値",
            "設計値",
            "Xmax",
            "Xmin"
        ])

        for taban, meta in meta_by_taban.items():
            writer.writerow([
                taban,
                meta.get("工種", ""),
                meta.get("測定項目", ""),
                meta.get("面積", ""),
                meta.get("測定基準", ""),
                meta.get("規格値", ""),
                meta.get("社内目標値", ""),
                meta.get("設計値", ""),
                meta.get("Xmax", ""),
                meta.get("Xmin", "")
            ])

    log_path = os.path.join(output_folder, "ssk_ocr_log.txt")

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))

    save_log("\n全部完了")
    save_log(f"測定情報CSV保存完了: {meta_csv}")
    save_log(f"ログ保存完了: {log_path}")


class App:

    def __init__(self, root):

        self.root = root
        self.root.title("SSK OCR デキスパートCSV作成 安定版")
        self.root.geometry("820x600")

        self.image_folder = tk.StringVar()
        self.output_folder = tk.StringVar(value="ssk_output")
        self.status_text = tk.StringVar(value="待機中")

        self.message_queue = queue.Queue()
        self.is_running = False

        tk.Label(root, text="写真フォルダ").pack(anchor="w", padx=10, pady=(10, 0))

        frame1 = tk.Frame(root)
        frame1.pack(fill="x", padx=10)

        tk.Entry(frame1, textvariable=self.image_folder).pack(side="left", fill="x", expand=True)

        tk.Button(
            frame1,
            text="選択",
            command=self.select_image_folder
        ).pack(side="left", padx=5)

        tk.Label(root, text="保存先フォルダ").pack(anchor="w", padx=10, pady=(10, 0))

        frame2 = tk.Frame(root)
        frame2.pack(fill="x", padx=10)

        tk.Entry(frame2, textvariable=self.output_folder).pack(side="left", fill="x", expand=True)

        tk.Button(
            frame2,
            text="選択",
            command=self.select_output_folder
        ).pack(side="left", padx=5)

        self.start_button = tk.Button(
            root,
            text="CSV作成開始",
            command=self.start,
            height=2
        )
        self.start_button.pack(fill="x", padx=10, pady=10)

        self.progress_bar = ttk.Progressbar(
            root,
            orient="horizontal",
            mode="determinate"
        )
        self.progress_bar.pack(fill="x", padx=10)

        tk.Label(
            root,
            textvariable=self.status_text
        ).pack(anchor="w", padx=10, pady=(5, 0))

        self.log_text = tk.Text(root)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)

        frame3 = tk.Frame(root)
        frame3.pack(fill="x", padx=10, pady=(0, 10))

        tk.Button(
            frame3,
            text="保存先を開く",
            command=self.open_output_folder
        ).pack(side="left")

        tk.Button(
            frame3,
            text="ログを消す",
            command=self.clear_log
        ).pack(side="left", padx=5)

        self.root.after(100, self.process_queue)

    def select_image_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.image_folder.set(folder)

    def select_output_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_folder.set(folder)

    def log(self, message):
        self.message_queue.put(("log", str(message)))

    def progress(self, current, total):
        self.message_queue.put(("progress", current, total))

    def process_queue(self):
        try:
            while True:
                item = self.message_queue.get_nowait()

                if item[0] == "log":
                    self.log_text.insert("end", item[1] + "\n")
                    self.log_text.see("end")

                elif item[0] == "progress":
                    current = item[1]
                    total = item[2]
                    self.progress_bar["maximum"] = total
                    self.progress_bar["value"] = current
                    self.status_text.set(f"処理中: {current}/{total}")

                elif item[0] == "done":
                    self.finish_success()

                elif item[0] == "error":
                    self.finish_error(item[1])

        except queue.Empty:
            pass

        self.root.after(100, self.process_queue)

    def start(self):

        if self.is_running:
            return

        image_folder = self.image_folder.get()
        output_folder = self.output_folder.get()

        if image_folder == "":
            messagebox.showerror("エラー", "写真フォルダを選択してください")
            return

        if output_folder == "":
            messagebox.showerror("エラー", "保存先フォルダを選択してください")
            return

        self.is_running = True
        self.start_button.config(state="disabled", text="処理中...")
        self.progress_bar["value"] = 0
        self.status_text.set("開始しました")
        self.log_text.insert("end", "\n--- 実行開始 ---\n")

        thread = threading.Thread(
            target=self.run_thread,
            args=(image_folder, output_folder),
            daemon=True
        )

        thread.start()

    def run_thread(self, image_folder, output_folder):

        try:
            run_ocr(
                image_folder,
                output_folder,
                self.log,
                self.progress
            )

            self.message_queue.put(("done",))

        except Exception:
            error_text = traceback.format_exc()
            self.message_queue.put(("error", error_text))

    def finish_success(self):

        self.is_running = False
        self.start_button.config(state="normal", text="CSV作成開始")
        self.status_text.set("完了")
        messagebox.showinfo("完了", "CSV作成が完了しました")

    def finish_error(self, error_text):

        self.is_running = False
        self.start_button.config(state="normal", text="CSV作成開始")
        self.status_text.set("エラー発生")

        self.log_text.insert("end", "\n--- エラー詳細 ---\n")
        self.log_text.insert("end", error_text + "\n")
        self.log_text.see("end")

        messagebox.showerror("エラー", "処理中にエラーが発生しました。ログを確認してください。")

    def open_output_folder(self):

        folder = self.output_folder.get()

        if folder == "":
            messagebox.showerror("エラー", "保存先フォルダが空です")
            return

        os.makedirs(folder, exist_ok=True)
        os.startfile(folder)

    def clear_log(self):
        self.log_text.delete("1.0", "end")


root = tk.Tk()
app = App(root)
root.mainloop()