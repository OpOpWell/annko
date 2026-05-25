import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from openai import OpenAI
from dotenv import load_dotenv
import base64
import os
import json
import re
import shutil
import threading
import csv
from datetime import datetime

load_dotenv()
client = OpenAI()


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_filename(name):
    return name.replace("\\", "_").replace("/", "_").replace(":", "_")


def classify_photo(image_path, log):
    try:
        with open(image_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode("utf-8")

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
この工事写真を分類してください。

返却はJSONのみ。
説明文は禁止。

分類は必ず次から1つ選んでください。

- 出来形測定写真
- 作業写真
- 重機写真
- 黒板写真
- 完成写真
- 着工前
- 除外

判断基準:
- 出来形測定写真: 測定表、手書き数値、測点番号、田番、出来形管理の写真
- 作業写真: 人が作業している、施工状況が分かる写真
- 重機写真: バックホウ、ローラー、ダンプなど重機が主役の写真
- 黒板写真: 工事黒板が主で、作業状況が少ない写真
- 完成写真: 施工後、完成後の状態が分かる写真
- 着工前: 施工前の状態が分かる写真
- 除外: ピンぼけ、関係ない、判別不能、暗すぎる、地面だけ、使いにくい写真

返却形式:
{
  "category": "作業写真",
  "reason": "作業員が施工している様子が写っているため"
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

        text = response.output_text.strip()

        log("\nAI分類結果")
        log(text)

        text = text.replace("```json", "")
        text = text.replace("```", "")

        match = re.search(r"\{.*\}", text, re.DOTALL)

        if not match:
            return {
                "category": "除外",
                "reason": "JSONが見つかりません"
            }

        data = json.loads(match.group())

        category = str(data.get("category", "除外")).strip()
        reason = str(data.get("reason", "")).strip()

        allowed = [
            "出来形測定写真",
            "作業写真",
            "重機写真",
            "黒板写真",
            "完成写真",
            "着工前",
            "除外"
        ]

        if category not in allowed:
            category = "除外"

        return {
            "category": category,
            "reason": reason
        }

    except Exception as e:
        return {
            "category": "除外",
            "reason": f"分類エラー: {e}"
        }


def sort_photos(input_folder, output_folder, log):
    os.makedirs(output_folder, exist_ok=True)

    categories = [
        "出来形測定写真",
        "作業写真",
        "重機写真",
        "黒板写真",
        "完成写真",
        "着工前",
        "除外"
    ]

    for category in categories:
        os.makedirs(
            os.path.join(output_folder, category),
            exist_ok=True
        )

    image_files = sorted([
        f for f in os.listdir(input_folder)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ])

    if not image_files:
        log("画像がありません")
        return

    log("AI写真自動分類開始")
    log(f"対象枚数: {len(image_files)}")

    report_rows = []

    for index, image_name in enumerate(image_files, start=1):
        image_path = os.path.join(input_folder, image_name)

        log(f"\n[{index}/{len(image_files)}] 処理中: {image_name}")

        result = classify_photo(image_path, log)

        category = result["category"]
        reason = result["reason"]

        save_folder = os.path.join(output_folder, category)
        os.makedirs(save_folder, exist_ok=True)

        dst_path = os.path.join(
            save_folder,
            safe_filename(image_name)
        )

        shutil.copy2(image_path, dst_path)

        log(f"分類: {category}")
        log(f"理由: {reason}")
        log(f"保存先: {dst_path}")

        report_rows.append([
            image_name,
            category,
            reason,
            dst_path
        ])

    report_path = os.path.join(output_folder, "photo_sort_report.csv")

    with open(report_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "画像名",
            "分類",
            "理由",
            "保存先"
        ])
        writer.writerows(report_rows)

    log("\n全部完了")
    log(f"分類レポート保存: {report_path}")

    messagebox.showinfo(
        "完了",
        "写真分類が完了しました"
    )


# =========================
# GUI
# =========================

root = tk.Tk()
root.title("杏子 写真自動分類 GUI")
root.geometry("950x750")

input_folder_var = tk.StringVar()
output_folder_var = tk.StringVar()


def select_input_folder():
    folder = filedialog.askdirectory()

    if folder:
        input_folder_var.set(folder)


def select_output_folder():
    folder = filedialog.askdirectory()

    if folder:
        output_folder_var.set(folder)


def write_log(message):
    log_text.insert(tk.END, str(message) + "\n")
    log_text.see(tk.END)


def start_sort():
    input_folder = input_folder_var.get()
    output_folder = output_folder_var.get()

    if not input_folder:
        messagebox.showerror(
            "エラー",
            "元画像フォルダを選択してください"
        )
        return

    if not output_folder:
        messagebox.showerror(
            "エラー",
            "出力フォルダを選択してください"
        )
        return

    thread = threading.Thread(
        target=sort_photos,
        args=(input_folder, output_folder, write_log)
    )

    thread.start()


tk.Label(
    root,
    text="元画像フォルダ"
).pack(pady=5)

tk.Entry(
    root,
    textvariable=input_folder_var,
    width=110
).pack()

tk.Button(
    root,
    text="元画像フォルダ選択",
    command=select_input_folder
).pack(pady=5)

tk.Label(
    root,
    text="出力フォルダ"
).pack(pady=5)

tk.Entry(
    root,
    textvariable=output_folder_var,
    width=110
).pack()

tk.Button(
    root,
    text="出力フォルダ選択",
    command=select_output_folder
).pack(pady=5)

tk.Button(
    root,
    text="写真分類実行",
    command=start_sort,
    bg="blue",
    fg="white",
    height=2,
    width=20
).pack(pady=10)

log_text = scrolledtext.ScrolledText(
    root,
    width=130,
    height=35
)

log_text.pack(padx=10, pady=10)

root.mainloop()