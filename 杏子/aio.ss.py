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

# =========================
# API
# =========================

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# =========================
# 現場デフォルト工種
# =========================

DEFAULT_WORK_TYPE = "整地工"

# =========================
# 時間
# =========================

def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# =========================
# ファイル名安全化
# =========================

def safe_filename(name):

    return (
        name
        .replace("\\", "_")
        .replace("/", "_")
        .replace(":", "_")
    )

# =========================
# AI分類
# =========================

def classify_photo(image_path, log):

    try:

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
この工事写真を分類してください。

返却はJSONのみ。

分類:
- 着手前及び完成写真
- 施工状況写真
- 安全管理写真
- 使用材料写真
- 品質管理写真
- 出来形管理写真
- 災害写真
- 事故写真
- その他

さらに工種も判定してください。

工種:
- 整地工
- 掘削工
- 盛土工
- 法面工
- 排水工
- 舗装工
- 構造物工
- 安全施設工
- その他

重要:

巻尺、スタッフ、測量ポール、スケール、
測点杭、手書き数値、測定黒板、
出来形黒板が写っている場合は、
作業中に見えても
「出来形管理写真」を優先してください。

黒板やホワイトボードに
「整地」「整地仕上げ」
などの記載がある場合は
工種を「整地工」にしてください。

掘削深さ測定なら「掘削工」。

法面測定なら「法面工」。

返却形式:

{
  "category": "出来形管理写真",
  "work_type": "整地工",
  "reason": "巻尺と測定ポールを使用した出来形測定状況が写っているため"
}
"""
                        },
                        {
                            "type": "input_image",
                            "image_url": (
                                f"data:image/jpeg;base64,"
                                f"{base64_image}"
                            )
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

        match = re.search(
            r"\{.*\}",
            text,
            re.DOTALL
        )

        if not match:

            return {
                "category": "その他",
                "work_type": DEFAULT_WORK_TYPE,
                "reason": "JSONが見つかりません"
            }

        data = json.loads(match.group())

        category = str(
            data.get("category", "その他")
        ).strip()

        work_type = str(
            data.get("work_type", "その他")
        ).strip()

        reason = str(
            data.get("reason", "")
        ).strip()

        allowed_categories = [
            "着手前及び完成写真",
            "施工状況写真",
            "安全管理写真",
            "使用材料写真",
            "品質管理写真",
            "出来形管理写真",
            "災害写真",
            "事故写真",
            "その他"
        ]

        allowed_work_types = [
            "整地工",
            "掘削工",
            "盛土工",
            "法面工",
            "排水工",
            "舗装工",
            "構造物工",
            "安全施設工",
            "その他"
        ]

        if category not in allowed_categories:
            category = "その他"

        if work_type not in allowed_work_types:
            work_type = "その他"

        # =========================
        # デフォルト工種補完
        # =========================

        if (
            category == "出来形管理写真"
            and work_type == "その他"
        ):

            work_type = DEFAULT_WORK_TYPE

        return {
            "category": category,
            "work_type": work_type,
            "reason": reason
        }

    except Exception as e:

        return {
            "category": "その他",
            "work_type": DEFAULT_WORK_TYPE,
            "reason": f"分類エラー: {e}"
        }

# =========================
# 写真分類
# =========================

def sort_photos(
    input_folder,
    output_folder,
    log
):

    os.makedirs(output_folder, exist_ok=True)

    image_files = sorted([
        f for f in os.listdir(input_folder)
        if f.lower().endswith(
            (".jpg", ".jpeg", ".png")
        )
    ])

    if not image_files:

        log("画像がありません")
        return

    log("AI写真自動分類開始")
    log(f"対象枚数: {len(image_files)}")

    report_rows = []

    for index, image_name in enumerate(
        image_files,
        start=1
    ):

        image_path = os.path.join(
            input_folder,
            image_name
        )

        log(
            f"\n[{index}/{len(image_files)}] "
            f"処理中: {image_name}"
        )

        result = classify_photo(
            image_path,
            log
        )

        category = result["category"]
        work_type = result["work_type"]
        reason = result["reason"]

        save_folder = os.path.join(
            output_folder,
            category,
            work_type
        )

        os.makedirs(
            save_folder,
            exist_ok=True
        )

        dst_path = os.path.join(
            save_folder,
            safe_filename(image_name)
        )

        shutil.copy2(
            image_path,
            dst_path
        )

        log(f"分類: {category}")
        log(f"工種: {work_type}")
        log(f"理由: {reason}")
        log(f"保存先: {dst_path}")

        report_rows.append([
            image_name,
            category,
            work_type,
            reason,
            dst_path
        ])

    # =========================
    # CSV保存
    # =========================

    report_path = os.path.join(
        output_folder,
        "photo_sort_report.csv"
    )

    with open(
        report_path,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        writer = csv.writer(f)

        writer.writerow([
            "画像名",
            "分類",
            "工種",
            "理由",
            "保存先"
        ])

        writer.writerows(report_rows)

    log("\n全部完了")

    log(
        f"分類レポート保存: "
        f"{report_path}"
    )

    messagebox.showinfo(
        "完了",
        "写真分類が完了しました"
    )

# =========================
# GUI
# =========================

root = tk.Tk()

root.title(
    "AI写真自動分類 + 工種分類 GUI"
)

root.geometry("950x750")

input_folder_var = tk.StringVar()
output_folder_var = tk.StringVar()

# =========================
# フォルダ選択
# =========================

def select_input_folder():

    folder = filedialog.askdirectory()

    if folder:
        input_folder_var.set(folder)

# -------------------------

def select_output_folder():

    folder = filedialog.askdirectory()

    if folder:
        output_folder_var.set(folder)

# =========================
# ログ
# =========================

def write_log(message):

    log_text.insert(
        tk.END,
        str(message) + "\n"
    )

    log_text.see(tk.END)

# =========================
# 開始
# =========================

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
        args=(
            input_folder,
            output_folder,
            write_log
        )
    )

    thread.start()

# =========================
# GUI配置
# =========================

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

# -------------------------

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

# -------------------------

tk.Button(
    root,
    text="写真分類実行",
    command=start_sort,
    bg="blue",
    fg="white",
    height=2,
    width=20
).pack(pady=10)

# -------------------------

log_text = scrolledtext.ScrolledText(
    root,
    width=130,
    height=35
)

log_text.pack(
    padx=10,
    pady=10
)

# =========================
# 起動
# =========================

root.mainloop()