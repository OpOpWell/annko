from openai import OpenAI
import base64
from ocr_checker import check_ocr_result
import os
import csv
import re
import json
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
    except Exception:
        return ""


def get_value_dict(result, log=None, error_log=None, image_name=""):
    value_dict = {}

    values = result.get("values", [])

    for item in values:
        try:
            no = int(item["no"])
            value = float(item["value"])
            value_dict[no] = value

        except Exception as e:
            if log:
                log("実測値変換エラー")
                log(f"画像: {image_name}")
                log(f"item内容: {item}")
                log(f"エラー内容: {e}")

            if error_log:
                error_log("実測値変換エラー")
                error_log(f"画像: {image_name}")
                error_log(f"item内容: {item}")
                error_log(traceback.format_exc())

    return value_dict


def fix_xmax_xmin_from_values(result):
    """
    GPTがXmax/Xminを逆に読むことがあるため、
    valuesから最大値・最小値を自動計算して上書きする。
    """

    try:
        values = result.get("values", [])

        nums = []

        for item in values:
            nums.append(float(item["value"]))

        if nums:
            result["xmax"] = f"{max(nums):.3f}"
            result["xmin"] = f"{min(nums):.3f}"

    except Exception:
        pass

    return result


# =========================
# 田番マスタ読込
# =========================

expected_counts = {}

with open("master_taban.csv", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)

    for row in reader:
        expected_counts[str(row["田番"]).strip()] = int(row["測点数"])

print("田番マスタ読込:", expected_counts)


# =========================
# 測定項目マスタ読込
# =========================

allowed_items = []

with open("master_items.csv", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)

    for row in reader:
        allowed_items.append(row["測定項目"].strip())

print("測定項目マスタ読込:", ", ".join(allowed_items))


# =========================
# 工種マスタ読込
# =========================

work_master = {}

with open("master_work.csv", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)

    for row in reader:
        item = row["測定項目"].strip()
        work = row["工種"].strip()
        work_master[item] = work

print("工種マスタ読込:", work_master)


# =========================
# 規格値マスタ読込
# =========================

spec_master = {}

with open("master_spec.csv", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)

    for row in reader:
        item = row["測定項目"].strip()

        spec_master[item] = {
            "spec": row["規格値"].strip(),
            "target": row["社内目標値"].strip()
        }

print("規格値マスタ読込:", spec_master)


# =========================
# GPT OCR
# =========================

def gpt_ocr(image_path, model_name, log, error_log):

    try:
        with open(image_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode("utf-8")

    except Exception as e:
        log("画像読込失敗")
        log(f"画像: {image_path}")
        log(f"エラー内容: {e}")

        error_log("画像読込失敗")
        error_log(f"画像: {image_path}")
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

    except Exception as e:
        log("OpenAI APIエラー")
        log(f"画像: {image_path}")
        log(f"モデル: {model_name}")
        log(f"エラー内容: {e}")

        error_log("OpenAI APIエラー")
        error_log(f"画像: {image_path}")
        error_log(f"モデル: {model_name}")
        error_log(traceback.format_exc())

        return {}

    try:
        result_text = response.output_text.strip()

    except Exception as e:
        log("GPT返答取得失敗")
        log(f"画像: {image_path}")
        log(f"エラー内容: {e}")

        error_log("GPT返答取得失敗")
        error_log(f"画像: {image_path}")
        error_log(traceback.format_exc())

        return {}

    log(f"\nGPT結果 ({model_name})")
    log(result_text)

    result_text = result_text.replace("```json", "")
    result_text = result_text.replace("```", "")

    match_json = re.search(r"\{.*\}", result_text, re.DOTALL)

    if not match_json:
        log("JSONが見つかりません")
        log("GPT生データ:")
        log(result_text)

        error_log("JSONが見つかりません")
        error_log(f"画像: {image_path}")
        error_log(f"モデル: {model_name}")
        error_log(result_text)

        return {}

    try:
        result = json.loads(match_json.group())

        # ここでXmax/Xminを実測値から上書き
        result = fix_xmax_xmin_from_values(result)

        return result

    except Exception as e:
        log("JSON変換失敗")
        log(f"エラー内容: {e}")
        log("GPT生データ:")
        log(result_text)

        error_log("JSON変換失敗")
        error_log(f"画像: {image_path}")
        error_log(f"モデル: {model_name}")
        error_log(f"エラー内容: {e}")
        error_log("GPT生データ:")
        error_log(result_text)
        error_log(traceback.format_exc())

        return {}


# =========================
# OCRメイン
# =========================

def run_ocr(image_folder, output_folder):

    os.makedirs(output_folder, exist_ok=True)

    csv_by_taban = {}
    meta_by_taban = {}
    log_lines = []
    error_lines = []
    check_report_rows = []

    def log(message):
        print(message)
        log_lines.append(safe_text(message))

    def error_log(message):
        line = f"[{now_text()}] {safe_text(message)}"
        error_lines.append(line)

    try:
        image_files = sorted([
            f for f in os.listdir(image_folder)
            if f.lower().endswith((".png", ".jpg", ".jpeg"))
        ])

    except Exception as e:
        log("画像フォルダ読込失敗")
        log(f"フォルダ: {image_folder}")
        log(f"エラー内容: {e}")

        error_log("画像フォルダ読込失敗")
        error_log(f"フォルダ: {image_folder}")
        error_log(traceback.format_exc())

        return

    if len(image_files) == 0:
        log("画像がありません")
        return

    log("SSK写真 OCR → デキスパートCSV 自動作成開始")
    log(f"対象画像数: {len(image_files)}")

    for image_name in image_files:

        image_path = os.path.join(image_folder, image_name)

        log(f"\n処理中: {image_path}")

        try:
            result = gpt_ocr(
                image_path,
                "gpt-4.1-mini",
                log,
                error_log
            )

            result = fix_xmax_xmin_from_values(result)

            try:
                check = check_ocr_result(
                    result,
                    taban_master=expected_counts
                )

            except Exception as e:
                log("OCR信頼度チェック失敗")
                log(f"画像: {image_name}")
                log(f"エラー内容: {e}")

                error_log("OCR信頼度チェック失敗")
                error_log(f"画像: {image_name}")
                error_log(f"result: {result}")
                error_log(traceback.format_exc())

                check = {
                    "score": 0,
                    "level": "ERROR",
                    "warnings": [f"OCR信頼度チェック失敗: {e}"]
                }

            log(f"OCR信頼度: {check['score']}")
            log(f"OCR判定: {check['level']}")

            for warning in check["warnings"]:
                log(f"注意: {warning}")

            # =========================
            # 信頼度が低い場合は4.1で再OCR
            # =========================

            if check["level"] != "OK":

                log("")
                log("OCR判定が要確認のため、gpt-4.1で再OCRします")
                log(f"再OCR対象画像: {image_name}")

                retry_result = gpt_ocr(
                    image_path,
                    "gpt-4.1",
                    log,
                    error_log
                )

                retry_result = fix_xmax_xmin_from_values(retry_result)

                try:
                    retry_check = check_ocr_result(
                        retry_result,
                        taban_master=expected_counts
                    )

                except Exception as e:
                    log("再OCR信頼度チェック失敗")
                    log(f"画像: {image_name}")
                    log(f"エラー内容: {e}")

                    error_log("再OCR信頼度チェック失敗")
                    error_log(f"画像: {image_name}")
                    error_log(f"retry_result: {retry_result}")
                    error_log(traceback.format_exc())

                    retry_check = {
                        "score": 0,
                        "level": "ERROR",
                        "warnings": [f"再OCR信頼度チェック失敗: {e}"]
                    }

                log(f"再OCR信頼度: {retry_check['score']}")
                log(f"再OCR判定: {retry_check['level']}")

                for warning in retry_check["warnings"]:
                    log(f"再OCR注意: {warning}")

                if retry_check["score"] > check["score"]:

                    log("再OCR結果を採用します")

                    result = retry_result
                    check = retry_check

                else:

                    log("初回OCR結果を採用します")

            if check["level"] != "OK":

                check_report_rows.append([
                    image_name,
                    result.get("taban", ""),
                    result.get("measurement_item", ""),
                    check["score"],
                    check["level"],
                    " / ".join(check["warnings"])
                ])

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
                log(f"田番がマスタにありません: {taban}")
                error_log(f"田番がマスタにありません: {taban}")
                error_log(f"画像: {image_name}")
                taban = "未分類"

            value_dict = get_value_dict(
                result,
                log=log,
                error_log=error_log,
                image_name=image_name
            )

            total_count = expected_counts.get(taban, 0)

            missing_no = []

            for no in range(1, total_count + 1):
                if no not in value_dict:
                    missing_no.append(no)

            if missing_no:

                log("\n未読No検出")
                log(missing_no)

                log("\n4.1で再OCR実施")
                log(f"未読補完対象画像: {image_name}")

                retry_result = gpt_ocr(
                    image_path,
                    "gpt-4.1",
                    log,
                    error_log
                )

                retry_result = fix_xmax_xmin_from_values(retry_result)

                retry_value_dict = get_value_dict(
                    retry_result,
                    log=log,
                    error_log=error_log,
                    image_name=image_name
                )

                for no, value in retry_value_dict.items():
                    if no not in value_dict:
                        value_dict[no] = value

            # =========================
            # 測定情報作成
            # Xmax / Xmin はGPTではなく実測値から計算
            # =========================

            xmax_value = ""
            xmin_value = ""

            if value_dict:
                xmax_value = f"{max(value_dict.values()):.3f}"
                xmin_value = f"{min(value_dict.values()):.3f}"

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

        except Exception as e:
            log("画像処理中に予期しないエラー")
            log(f"画像: {image_name}")
            log(f"エラー内容: {e}")

            error_log("画像処理中に予期しないエラー")
            error_log(f"画像: {image_name}")
            error_log(traceback.format_exc())

            check_report_rows.append([
                image_name,
                "",
                "",
                0,
                "ERROR",
                f"画像処理中にエラー: {e}"
            ])

            continue

    # =========================
    # CSV保存
    # =========================

    for taban, rows in csv_by_taban.items():

        missing_no = []

        for row in rows:
            if row[4] == "":
                missing_no.append(row[0])

        if missing_no:
            log(f"\n未読あり: 田番{taban}")
            log("未読No: " + ", ".join(missing_no))
        else:
            log(f"\n未読なし: 田番{taban}")

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

            log(f"CSV保存完了: {output_csv}")

        except Exception as e:
            log("CSV保存失敗")
            log(f"保存先: {output_csv}")
            log(f"エラー内容: {e}")

            error_log("CSV保存失敗")
            error_log(f"保存先: {output_csv}")
            error_log(traceback.format_exc())

    # =========================
    # 測定情報CSV
    # =========================

    meta_csv = os.path.join(
        output_folder,
        "測定情報.csv"
    )

    try:
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

        log(f"測定情報CSV保存完了: {meta_csv}")

    except Exception as e:
        log("測定情報CSV保存失敗")
        log(f"保存先: {meta_csv}")
        log(f"エラー内容: {e}")

        error_log("測定情報CSV保存失敗")
        error_log(f"保存先: {meta_csv}")
        error_log(traceback.format_exc())

    # =========================
    # 要確認レポートCSV
    # =========================

    report_csv = os.path.join(
        output_folder,
        "ocr_check_report.csv"
    )

    try:
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
                "信頼度",
                "判定",
                "注意内容"
            ])

            writer.writerows(check_report_rows)

        log(f"要確認レポートCSV保存完了: {report_csv}")

    except Exception as e:
        log("要確認レポートCSV保存失敗")
        log(f"保存先: {report_csv}")
        log(f"エラー内容: {e}")

        error_log("要確認レポートCSV保存失敗")
        error_log(f"保存先: {report_csv}")
        error_log(traceback.format_exc())

    # =========================
    # ログ保存
    # =========================

    log_path = os.path.join(
        output_folder,
        "ssk_ocr_log.txt"
    )

    error_log_path = os.path.join(
        output_folder,
        "ssk_ocr_error_log.txt"
    )

    try:
        with open(
            log_path,
            "w",
            encoding="utf-8"
        ) as f:

            f.write("\n".join(log_lines))

        log(f"ログ保存完了: {log_path}")

    except Exception as e:
        print("ログ保存失敗")
        print(e)

    try:
        with open(
            error_log_path,
            "w",
            encoding="utf-8"
        ) as f:

            f.write("\n".join(error_lines))

        log(f"エラーログ保存完了: {error_log_path}")

    except Exception as e:
        print("エラーログ保存失敗")
        print(e)

    log("\n全部完了")


# =========================
# 実行
# =========================

image_folder = r"C:\Users\user\foolder\634\photo_sorted\出来形測定写真"

output_folder = r"C:\Users\user\foolder\zzz"

run_ocr(
    image_folder,
    output_folder
)