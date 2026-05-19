import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from openai import OpenAI
import base64
import os
import csv
import re
import json
import threading
import traceback
from datetime import datetime

client = OpenAI()

# =========================
# 共通
# =========================

def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_text(value):
    try:
        return str(value)
    except:
        return "<文字変換できません>"


def to_mm_text(value):
    try:
        return str(int(round(float(value) * 1000)))
    except:
        return ""


# =========================
# GPT返却形式統一
# =========================

def normalize_result(result):
    if not isinstance(result, dict):
        return {}

    values = []

    # 英語キー形式
    raw_values = result.get("values", [])

    if isinstance(raw_values, list):
        for item in raw_values:
            try:
                values.append({
                    "no": int(item["no"]),
                    "value": float(item["value"])
                })
            except:
                pass

    # 日本語キー: 番号と手書き実測値
    raw_jp_values = result.get("番号と手書き実測値", {})

    if isinstance(raw_jp_values, dict):
        for no, value in raw_jp_values.items():
            try:
                values.append({
                    "no": int(no),
                    "value": float(value)
                })
            except:
                pass

    # 日本語キー: 測定値 [1.409, 1.396, ...]
    raw_list_values = result.get("測定値", [])

    if isinstance(raw_list_values, list):
        for i, value in enumerate(raw_list_values, start=1):
            try:
                values.append({
                    "no": i,
                    "value": float(value)
                })
            except:
                pass

    # 重複Noがある場合、後勝ち
    value_map = {}

    for item in values:
        try:
            value_map[int(item["no"])] = float(item["value"])
        except:
            pass

    fixed_values = []

    for no in sorted(value_map.keys()):
        fixed_values.append({
            "no": no,
            "value": value_map[no]
        })

    remarks = result.get("備考", {})

    if not isinstance(remarks, dict):
        remarks = {}

    return {
        "taban": str(
            result.get(
                "taban",
                result.get("田番", "")
            )
        ),
        "measurement_item": str(
            result.get(
                "measurement_item",
                result.get("測定項目", "")
            )
        ),
        "area": str(
            result.get(
                "area",
                result.get("面積", "")
            )
        ),
        "average": str(
            result.get(
                "average",
                result.get(
                    "平均値",
                    remarks.get("平均値", "")
                )
            )
        ),
        "xmax": str(
            result.get(
                "xmax",
                result.get(
                    "Xmax",
                    remarks.get("Xmax", "")
                )
            )
        ),
        "xmin": str(
            result.get(
                "xmin",
                result.get(
                    "Xmin",
                    remarks.get("Xmin", "")
                )
            )
        ),
        "values": fixed_values
    }


# =========================
# Xmax Xmin補正
# =========================

def fix_xmax_xmin_from_values(result):
    try:
        nums = []

        for item in result.get("values", []):
            nums.append(float(item["value"]))

        if nums:
            result["xmax"] = f"{max(nums):.3f}"
            result["xmin"] = f"{min(nums):.3f}"

    except:
        pass

    return result


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
# GPT OCR
# =========================

def gpt_ocr(image_path, model_name, log, error_log):

    try:
        with open(image_path, "rb") as f:
            base64_image = base64.b64encode(
                f.read()
            ).decode("utf-8")

    except Exception as e:
        log("画像読込失敗")
        log(e)
        error_log(traceback.format_exc())
        return {}

    try:
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
- 返却は必ずJSONのみ
- 説明文は禁止
- 日本語キーは禁止
- 「測定値」だけの配列は禁止
- 必ず下の英語キーを使うこと
- 田番は上部の「田番」欄の数字
- 大きく丸で書かれた手書き数字は田番にしない
- 写真がSSK出来形測定写真でない場合は {} を返すこと

測定項目は次の候補から選択してください。
候補に無い場合は "不明" とすること。

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

読む項目:
- taban
- measurement_item
- area
- average
- xmax
- xmin
- values

条件:
- 番号と手書き実測値を対応させる
- 空欄は無視
- 実測値は小数3桁
- 推測しない
- 読めない値は除外
- values は必ず {"no": 番号, "value": 実測値} の配列にすること

返却形式は必ずこれ:
{
  "taban": "9",
  "measurement_item": "均平度",
  "area": "3270㎡",
  "average": "1.452",
  "xmax": "1.465",
  "xmin": "1.444",
  "values": [
    {"no": 1, "value": 1.446},
    {"no": 2, "value": 1.456}
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

    except Exception as e:
        log("OpenAI APIエラー")
        log(e)
        error_log(traceback.format_exc())
        return {}

    try:
        result_text = response.output_text.strip()

    except Exception as e:
        log("GPT返答取得失敗")
        log(e)
        error_log(traceback.format_exc())
        return {}

    log(f"\nGPT結果 ({model_name})")
    log(result_text)

    result_text = result_text.replace("```json", "")
    result_text = result_text.replace("```", "")

    match_json = re.search(
        r"\{.*\}",
        result_text,
        re.DOTALL
    )

    if not match_json:
        log("JSONが見つかりません")
        error_log(result_text)
        return {}

    try:
        result = json.loads(match_json.group())

        result = normalize_result(result)
        result = fix_xmax_xmin_from_values(result)

        return result

    except Exception as e:
        log("JSON変換失敗")
        log(e)
        error_log(traceback.format_exc())
        return {}


# =========================
# OCR本体
# =========================

def run_ocr(image_folder, output_folder, log):

    os.makedirs(output_folder, exist_ok=True)

    csv_by_taban = {}
    meta_by_taban = {}
    log_lines = []
    error_lines = []
    check_report_rows = []

    def add_log(message):
        log(message)
        log_lines.append(safe_text(message))

    def error_log(message):
        line = f"[{now_text()}] {safe_text(message)}"
        error_lines.append(line)

    try:
        image_files = sorted([
            f for f in os.listdir(image_folder)
            if f.lower().endswith(
                (".png", ".jpg", ".jpeg")
            )
        ])

    except Exception as e:
        add_log("画像フォルダ読込失敗")
        add_log(e)
        return

    total_images = len(image_files)

    if total_images == 0:
        add_log("画像がありません")
        return

    add_log("SSK写真 OCR → デキスパートCSV 自動作成開始")
    add_log(f"画像数: {total_images}")

    for index, image_name in enumerate(image_files, start=1):

        image_path = os.path.join(image_folder, image_name)

        add_log(f"\n[{index}/{total_images}] 処理中: {image_path}")

        try:
            result = gpt_ocr(
                image_path,
                "gpt-4.1-mini",
                add_log,
                error_log
            )

            taban = str(result.get("taban", "")).strip()

            measurement_item = str(
                result.get("measurement_item", "不明")
            ).strip()

            values = result.get("values", [])

            # =========================
            # 除外判定
            # =========================

            if (
                taban in ["", "なし", "不明", "未分類"]
                or measurement_item in ["", "なし", "不明"]
                or len(values) < 3
            ):
                add_log(
                    "出来形測定写真ではない、または実測値不足のため除外"
                )

                check_report_rows.append([
                    image_name,
                    taban,
                    measurement_item,
                    "除外",
                    "田番・測定項目なし、または実測値3点未満"
                ])

                continue

            # =========================
            # 測定項目チェック
            # =========================

            if measurement_item not in allowed_items:
                measurement_item = "不明"

            if measurement_item == "不明":
                add_log("測定項目が不明のため除外")

                check_report_rows.append([
                    image_name,
                    taban,
                    measurement_item,
                    "除外",
                    "測定項目がマスタにありません"
                ])

                continue

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
                add_log(f"田番がマスタにないため除外: {taban}")

                check_report_rows.append([
                    image_name,
                    taban,
                    measurement_item,
                    "除外",
                    "田番がmaster_taban.csvにありません"
                ])

                continue

            # =========================
            # values
            # =========================

            value_dict = {}

            for item in values:
                try:
                    no = int(item["no"])
                    value = float(item["value"])
                    value_dict[no] = value

                except Exception as e:
                    add_log("実測値変換エラー")
                    add_log(e)

            total_count = expected_counts.get(taban, 0)

            missing_no = []

            for no in range(1, total_count + 1):
                if no not in value_dict:
                    missing_no.append(no)

            # =========================
            # 未読時再OCR
            # =========================

            if missing_no:
                add_log("\n未読No検出")
                add_log(missing_no)

                add_log("\n4.1で再OCR実施")

                retry_result = gpt_ocr(
                    image_path,
                    "gpt-4.1",
                    add_log,
                    error_log
                )

                retry_values = retry_result.get("values", [])

                for item in retry_values:
                    try:
                        no = int(item["no"])
                        value = float(item["value"])

                        if no not in value_dict:
                            value_dict[no] = value

                    except:
                        pass

                missing_no = []

                for no in range(1, total_count + 1):
                    if no not in value_dict:
                        missing_no.append(no)

            # =========================
            # Xmax Xmin
            # =========================

            xmax_value = ""
            xmin_value = ""

            if value_dict:
                xmax_value = f"{max(value_dict.values()):.3f}"
                xmin_value = f"{min(value_dict.values()):.3f}"

            # =========================
            # 測定情報
            # =========================

            if taban not in meta_by_taban:
                meta_by_taban[taban] = {
                    "工種": work_type,
                    "測定項目": measurement_item,
                    "面積": result.get("area", ""),
                    "測定基準": "10a当たり3点以上",
                    "規格値": spec_value,
                    "社内目標値": target_value,
                    "設計値": design_value,
                    "Xmax": xmax_value,
                    "Xmin": xmin_value,
                }

            # =========================
            # CSV
            # =========================

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

            # =========================
            # 要確認
            # =========================

            if missing_no:
                check_report_rows.append([
                    image_name,
                    taban,
                    measurement_item,
                    "未読あり",
                    ",".join(map(str, missing_no))
                ])

        except Exception as e:
            add_log("画像処理中エラー")
            add_log(e)
            error_log(traceback.format_exc())

    # =========================
    # CSV保存
    # =========================

    for taban, rows in csv_by_taban.items():

        output_csv = os.path.join(
            output_folder,
            f"田番{taban}.csv"
        )

        try:
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

        except Exception as e:
            add_log("CSV保存失敗")
            add_log(e)

    # =========================
    # 測定情報CSV
    # =========================

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

    # =========================
    # 要確認CSV
    # =========================

    report_csv = os.path.join(
        output_folder,
        "ocr_check_report.csv"
    )

    with open(
        report_csv,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.writer(f)

        writer.writerow([
            "画像名",
            "田番",
            "測定項目",
            "内容",
            "詳細"
        ])

        writer.writerows(check_report_rows)

    # =========================
    # ログ保存
    # =========================

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

    error_log_path = os.path.join(
        output_folder,
        "ssk_ocr_error_log.txt"
    )

    with open(
        error_log_path,
        "w",
        encoding="utf-8"
    ) as f:

        f.write("\n".join(error_lines))

    add_log("\n全部完了")

    messagebox.showinfo(
        "完了",
        "OCR処理が完了しました"
    )


# =========================
# GUI
# =========================

root = tk.Tk()
root.title("杏子 OCR GUI")
root.geometry("950x750")

image_folder_var = tk.StringVar()
output_folder_var = tk.StringVar()


def select_image_folder():
    folder = filedialog.askdirectory()

    if folder:
        image_folder_var.set(folder)


def select_output_folder():
    folder = filedialog.askdirectory()

    if folder:
        output_folder_var.set(folder)


def write_log(message):
    log_text.insert(
        tk.END,
        str(message) + "\n"
    )

    log_text.see(tk.END)


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
        args=(
            image_folder,
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
    text="画像フォルダ"
).pack(pady=5)

tk.Entry(
    root,
    textvariable=image_folder_var,
    width=110
).pack()

tk.Button(
    root,
    text="画像フォルダ選択",
    command=select_image_folder
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
    text="OCR実行",
    command=start_ocr,
    bg="green",
    fg="white",
    height=2,
    width=20
).pack(pady=10)

log_text = scrolledtext.ScrolledText(
    root,
    width=130,
    height=35
)

log_text.pack(
    padx=10,
    pady=10
)

root.mainloop()