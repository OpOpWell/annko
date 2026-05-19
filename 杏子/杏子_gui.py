import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from openai import OpenAI
import base64
import os
import csv
import re
import json
import threading

client = OpenAI()

# =========================
# マスタ読込
# =========================

expected_counts = {}

with open("master_taban.csv", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)

    for row in reader:
        expected_counts[str(row["田番"]).strip()] = int(row["測点数"])

allowed_items = []

with open("master_items.csv", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)

    for row in reader:
        allowed_items.append(row["測定項目"].strip())

work_master = {}

with open("master_work.csv", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)

    for row in reader:
        item = row["測定項目"].strip()
        work = row["工種"].strip()

        work_master[item] = work

spec_master = {}

with open("master_spec.csv", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)

    for row in reader:
        item = row["測定項目"].strip()

        spec_master[item] = {
            "spec": row["規格値"].strip(),
            "target": row["社内目標値"].strip()
        }

# =========================
# mm変換
# =========================

def to_mm_text(value):
    try:
        return str(int(round(float(value) * 1000)))
    except:
        return ""

# =========================
# GPT OCR
# =========================

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
  "measurement_item": "均平度",
  "area": "9750㎡",
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

# =========================
# OCR本体
# =========================

def run_ocr(image_folder, output_folder, log):

    os.makedirs(output_folder, exist_ok=True)

    csv_by_taban = {}
    meta_by_taban = {}
    log_lines = []

    def add_log(message):
        log(message)
        log_lines.append(str(message))

    image_files = sorted([
        f for f in os.listdir(image_folder)
        if f.lower().endswith((".png", ".jpg", ".jpeg"))
    ])

    total_images = len(image_files)

    if total_images == 0:
        add_log("画像がありません")
        return

    add_log("SSK写真 OCR → デキスパートCSV 自動作成開始")
    add_log(f"画像数: {total_images}")

    for index, image_name in enumerate(image_files, start=1):

        image_path = os.path.join(image_folder, image_name)

        add_log(f"\n[{index}/{total_images}] 処理中: {image_path}")

        result = gpt_ocr(image_path, "gpt-4.1-mini", add_log)

        taban = str(result.get("taban", "")).strip()

        measurement_item = str(
            result.get("measurement_item", "不明")
        ).strip()

        if measurement_item not in allowed_items:
            measurement_item = "不明"

        work_type = work_master.get(
            measurement_item,
            "整地工"
        )

        spec_value = spec_master.get(
            measurement_item,
            {}
        ).get("spec", "")

        target_value = spec_master.get(
            measurement_item,
            {}
        ).get("target", "")

        design_value_raw = str(
            result.get("average", "")
        ).strip()

        design_value = to_mm_text(design_value_raw)

        if taban not in expected_counts:
            taban = "未分類"

        if taban not in meta_by_taban:
            meta_by_taban[taban] = {
                "工種": work_type,
                "測定項目": measurement_item,
                "面積": result.get("area", ""),
                "測定基準": "10a当たり3点以上",
                "規格値": spec_value,
                "社内目標値": target_value,
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

            add_log("\n未読No検出")
            add_log(missing_no)

            add_log("\n4.1で再OCR実施")

            retry_result = gpt_ocr(
                image_path,
                "gpt-4.1",
                add_log
            )

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

    # CSV保存

    for taban, rows in csv_by_taban.items():

        output_csv = os.path.join(
            output_folder,
            f"田番{taban}.csv"
        )

        with open(
            output_csv,
            "w",
            newline="",
            encoding="utf-8-sig"
        ) as f:

            writer = csv.writer(f)

            writer.writerow([
                "測点",
                "工種名",
                "測定項目",
                "設計値",
                "実測値1"
            ])

            writer.writerows(rows)

        add_log(f"CSV保存完了: {output_csv}")

    # 測定情報CSV

    meta_csv = os.path.join(
        output_folder,
        "測定情報.csv"
    )

    with open(
        meta_csv,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:

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

    # ログ保存

    log_path = os.path.join(
        output_folder,
        "ssk_ocr_log.txt"
    )

    with open(
        log_path,
        "w",
        encoding="utf-8"
    ) as f:

        f.write("\n".join(log_lines))

    add_log("\n全部完了")
    add_log(f"測定情報CSV保存完了: {meta_csv}")
    add_log(f"ログ保存完了: {log_path}")

    messagebox.showinfo(
        "完了",
        "OCR処理が完了しました"
    )

# =========================
# GUI
# =========================

root = tk.Tk()
root.title("SSK OCR GUI")
root.geometry("900x700")

image_folder_var = tk.StringVar()
output_folder_var = tk.StringVar()

# -------------------------

def select_image_folder():
    folder = filedialog.askdirectory()

    if folder:
        image_folder_var.set(folder)

# -------------------------

def select_output_folder():
    folder = filedialog.askdirectory()

    if folder:
        output_folder_var.set(folder)

# -------------------------

def write_log(message):

    log_text.insert(tk.END, str(message) + "\n")
    log_text.see(tk.END)

# -------------------------

def start_ocr():

    image_folder = image_folder_var.get()
    output_folder = output_folder_var.get()

    if not image_folder:
        messagebox.showerror(
            "エラー",
            "画像フォルダを選択してください"
        )
        return

    if not output_folder:
        messagebox.showerror(
            "エラー",
            "出力フォルダを選択してください"
        )
        return

    thread = threading.Thread(
        target=run_ocr,
        args=(image_folder, output_folder, write_log)
    )

    thread.start()

# =========================
# GUI配置
# =========================

tk.Label(
    root,
    text="画像フォルダ"
).pack(pady=5)

tk.Entry(
    root,
    textvariable=image_folder_var,
    width=100
).pack()

tk.Button(
    root,
    text="画像フォルダ選択",
    command=select_image_folder
).pack(pady=5)

# -------------------------

tk.Label(
    root,
    text="出力フォルダ"
).pack(pady=5)

tk.Entry(
    root,
    textvariable=output_folder_var,
    width=100
).pack()

tk.Button(
    root,
    text="出力フォルダ選択",
    command=select_output_folder
).pack(pady=5)

# -------------------------

tk.Button(
    root,
    text="OCR実行",
    command=start_ocr,
    bg="green",
    fg="white",
    height=2,
    width=20
).pack(pady=10)

# -------------------------

log_text = scrolledtext.ScrolledText(
    root,
    width=120,
    height=30
)

log_text.pack(padx=10, pady=10)

# =========================
# 起動
# =========================

root.mainloop()


