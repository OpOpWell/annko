"""
工事写真自動整理システム v2.0
改善点:
  - 設定ファイル化 (config.yml)
  - API非同期化 (asyncio + ThreadPoolExecutor)
  - エラーハンドリング強化
  - ファイル名重複対策
  - ログ出力 (logging)
  - 再実行安全性
"""

import os
import shutil
import base64
import json
import csv
import re
import asyncio
import logging
import hashlib
from pathlib import Path
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, tostring
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import yaml
from openai import OpenAI
from dotenv import load_dotenv
from PIL import Image
import imagehash

# ─────────────────────────────────────────
# ログ設定
# ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("photo_organizer.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────
# 設定ファイル読み込み
# ─────────────────────────────────────────
def load_config(config_path: str = "config.yml") -> dict:
    """config.yml を読み込む。なければデフォルト値を返す。"""
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        log.info(f"設定ファイル読込: {config_path}")
        return cfg

    log.warning(f"{config_path} が見つかりません。デフォルト設定を使用します。")
    return {
        "base_folder": r"C:\Users\user\foolder\杏子",
        "input_folder": r"C:\Users\user\OneDrive\hhh",
        "openai_model": "gpt-4.1-mini",
        "max_workers": 5,
        "hash_threshold": 8,
    }


CONFIG = load_config()

BASE_FOLDER   = CONFIG["base_folder"]
INPUT_FOLDER  = CONFIG["input_folder"]
MODEL         = CONFIG.get("openai_model", "gpt-4.1-mini")
MAX_WORKERS   = CONFIG.get("max_workers", 5)
HASH_THRESHOLD = CONFIG.get("hash_threshold", 8)

MASTER_PROJECT     = os.path.join(BASE_FOLDER, "master_project.csv")
MASTER_COMMON      = os.path.join(BASE_FOLDER, "master_common.csv")
SYNONYM_MASTER     = os.path.join(BASE_FOLDER, "synonym_master.csv")
KEYWORD_RULES      = os.path.join(BASE_FOLDER, "keyword_rules.csv")

PHOTO_ROOT     = os.path.join(BASE_FOLDER, "selected_photos", "PHOTO")
PHOTO_XML_PATH = os.path.join(PHOTO_ROOT, "PHOTO.XML")
PIC_FOLDER     = os.path.join(PHOTO_ROOT, "PIC")
CHECK_FOLDER   = os.path.join(PHOTO_ROOT, "CHECK")
EXCLUDE_FOLDER = os.path.join(PHOTO_ROOT, "EXCLUDE")

CHECK_CSV_PATH       = os.path.join(PHOTO_ROOT, "CHECK一覧.csv")
RESULT_CSV_PATH      = os.path.join(PHOTO_ROOT, "処理結果一覧.csv")
ADD_CANDIDATE_CSV_PATH = os.path.join(PHOTO_ROOT, "master追加候補.csv")
SOURCE_DTD           = os.path.join(BASE_FOLDER, "PHOTO05.DTD")

# ─────────────────────────────────────────
# フォルダ初期化
# ─────────────────────────────────────────
for folder in [PHOTO_ROOT, PIC_FOLDER, CHECK_FOLDER, EXCLUDE_FOLDER]:
    os.makedirs(folder, exist_ok=True)

if os.path.exists(SOURCE_DTD):
    shutil.copy2(SOURCE_DTD, os.path.join(PHOTO_ROOT, "PHOTO05.DTD"))
    log.info("PHOTO05.DTD コピーOK")
else:
    log.warning(f"PHOTO05.DTD が見つかりません: {SOURCE_DTD}")

# ─────────────────────────────────────────
# OpenAI クライアント
# ─────────────────────────────────────────
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ─────────────────────────────────────────
# ユーティリティ
# ─────────────────────────────────────────
def safe_text(v) -> str:
    return "" if v is None else str(v).strip()


def normalize_text(text: str) -> str:
    text = safe_text(text)
    replace_map = {
        " ": "", "　": "", "\n": "", "\r": "",
        "施工": "", "状況": "", "写真": "", "工事": "", "測定": "",
        "敷均しし": "敷均し", "敷敷均しし": "敷均し", "敷き均し": "敷均し",
        "敷均": "敷均し", "据付け": "据付", "接合け": "据付",
        "布設": "据付", "設置": "据付", "床掘り": "床掘", "床堀": "床掘",
        "底付": "底付け", "堀削": "掘削", "平均平度": "均平度",
        "平坦度": "均平度", "基盤整地": "整地仕上げ",
        "甘船整地丁": "基盤整地", "甘縄整地丁": "基盤整地",
    }
    for old, new in replace_map.items():
        text = text.replace(old, new)
    return text


def load_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        log.warning(f"CSVが見つかりません: {path}")
        return []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


project_master = load_csv(MASTER_PROJECT)
common_master  = load_csv(MASTER_COMMON)
synonym_master = load_csv(SYNONYM_MASTER)
keyword_rules  = load_csv(KEYWORD_RULES)

log.info(f"master_project: {len(project_master)}件, master_common: {len(common_master)}件, "
         f"synonym: {len(synonym_master)}件, keyword_rules: {len(keyword_rules)}件")

VALID_PHOTO_TYPES = [
    "着手前及び完成写真", "施工状況写真", "安全管理写真", "使用材料写真",
    "品質管理写真", "出来形管理写真", "災害写真", "事故写真", "その他",
]

# ─────────────────────────────────────────
# テキスト正規化
# ─────────────────────────────────────────
def apply_synonym(text: str) -> str:
    text = safe_text(text)
    for row in synonym_master:
        src, dst = safe_text(row.get("現場語")), safe_text(row.get("正式語"))
        if src and dst:
            text = text.replace(src, dst)
    return text


def normalize_photo_type(photo_type, blackboard_text="", scene_description=""):
    raw  = safe_text(photo_type)
    text = normalize_text(raw + blackboard_text + scene_description)
    if "熱中症" in text or "安全" in text:     return "安全管理写真"
    if "均平度" in text or "出来形" in text \
       or "Xmax" in blackboard_text or "Xmin" in blackboard_text:
                                                return "出来形管理写真"
    if "品質" in text:                          return "品質管理写真"
    if "材料" in text:                          return "使用材料写真"
    if "完成" in text or "着手前" in text:      return "着手前及び完成写真"
    if any(k in text for k in ["掘削","床掘","敷均","転圧","据付","整地","作業"]):
                                                return "施工状況写真"
    if raw in VALID_PHOTO_TYPES:                return raw
    return "その他"


def normalize_work_name(work, blackboard_text=""):
    source = apply_synonym(safe_text(work) + "\n" + safe_text(blackboard_text))
    text   = normalize_text(source)
    if "熱中症" in text or "安全" in text:                         return "安全管理"
    if "土工" in text or "土方" in text:                           return "土工"
    if any(k in text for k in ["小用水路","用水路","水路"]) \
       or "BF" in source:                                          return "水路工"
    if "排水管" in text or "排水路" in text:                       return "水路工"
    if any(k in text for k in ["均平度","整地","ほ場整備"]):       return "整地工"
    if "路盤" in text:                                             return "路盤工"
    return safe_text(work)


def normalize_type_name(type_name, detail_name="", blackboard_text=""):
    source = apply_synonym(safe_text(type_name) + "\n" + safe_text(detail_name) + "\n" + safe_text(blackboard_text))
    text   = normalize_text(source)
    if "熱中症" in text:                                           return "安全管理"
    if "均平度" in text or "整地仕上げ" in text or "基盤整地" in text: return "整地仕上げ"
    if "据付" in text:                                             return "据付工"
    if "敷均し" in text or "転圧" in text or "均し" in text:      return "均し工"
    if "掘削" in text or "床掘" in text or "根切" in text:        return "掘削"
    return safe_text(type_name)


def normalize_detail_name(detail_name, blackboard_text=""):
    source = apply_synonym(safe_text(detail_name) + "\n" + safe_text(blackboard_text))
    text   = normalize_text(source)
    if "熱中症" in text:                           return "熱中症対策"
    if "均平度" in text:                           return "均平度"
    if "据付" in text:                             return "据付状況"
    if "敷均し" in text or "転圧" in text:        return "敷均・転圧状況"
    if "基盤整地" in text or "整地仕上げ" in text \
       or "整地" in text:                          return "基盤整地"
    if "掘削" in text or "床掘" in text or "根切" in text:
                                                   return "床掘・底付け状況"
    return safe_text(detail_name)


def apply_keyword_rules(
    photo_type,
    work,
    type_name,
    detail_name,
    title,
    blackboard_text,
    scene_description
):

    # --------------------------------
    # keyword_rules 未使用
    # --------------------------------

    if not keyword_rules:

        return (
            photo_type,
            work,
            type_name,
            detail_name,
            title
        )

    # --------------------------------
    # 判定元テキスト
    # --------------------------------

    source = normalize_text(
        apply_synonym(
            blackboard_text
            + "\n"
            + scene_description
        )
    )

    # --------------------------------
    # 最良候補
    # --------------------------------

    best = None
    best_score = 0

    # --------------------------------
    # keyword_rules 全走査
    # --------------------------------

    for row in keyword_rules:

        keywords = safe_text(
            row.get("keyword")
            or row.get("キーワード")
        )

        if not keywords:
            continue

        # --------------------------------
        # Python 3.13対応
        # --------------------------------

        score = 0

        split_keywords = re.split(
            r"[,\n、/／]+",
            keywords
        )

        for kw in split_keywords:

            kw2 = normalize_text(kw)

            if not kw2:
                continue

            if kw2 in source:
                score += 1

        # --------------------------------
        # 最大スコア更新
        # --------------------------------

        if score > best_score:

            best_score = score
            best = row

    # --------------------------------
    # 採用
    # --------------------------------

    if best and best_score > 0:

        photo_type = (
            safe_text(
                best.get("写真区分")
            )
            or photo_type
        )

        work = (
            safe_text(
                best.get("工種")
            )
            or work
        )

        type_name = (
            safe_text(
                best.get("種別")
            )
            or type_name
        )

        detail_name = (
            safe_text(
                best.get("細別")
            )
            or detail_name
        )

        title = (
            safe_text(
                best.get("写真タイトル")
            )
            or title
        )

    # --------------------------------
    # return
    # --------------------------------

    return (
        photo_type,
        work,
        type_name,
        detail_name,
        title
    )
    return photo_type, work, type_name, detail_name, title


def final_rule_fix(photo_type, work, type_name, detail_name, title, blackboard_text, scene_description):
    src = normalize_text(apply_synonym(blackboard_text))
    if "熱中症" in src:
        return "安全管理写真", "安全管理", "安全管理", "熱中症対策", "熱中症対策"
    if "均平度" in src or "Xmax" in blackboard_text or "Xmin" in blackboard_text:
        return "出来形管理写真", "整地工", "整地仕上げ", "均平度", "均平度"
    if any(k in src for k in ["据付", "布設", "設置"]):
        return "施工状況写真", "水路工", "据付工", "据付状況", "小用水路 据付状況"
    if "敷均し" in src or "転圧" in src:
        w = normalize_work_name(work, blackboard_text)
        if w == "土工":
            t = "土工 敷均・転圧状況"
        else:
            w, t = "水路工", "小用水路 敷均・転圧状況"
        return "施工状況写真", w, "均し工", "敷均・転圧状況", t
    if "基盤整地" in src or "整地仕上げ" in src:
        return "施工状況写真", "整地工", "整地仕上げ", "基盤整地", "基盤整地施工状況写真"
    if "掘削" in src or "床掘" in src:
        if not any(k in src for k in ["敷均し","転圧","据付","布設","設置"]):
            w = normalize_work_name(work, blackboard_text)
            if w == "土工":
                t = "土工 掘削床掘状況"
            else:
                w, t = "水路工", "小用水路 掘削床掘状況"
            return "施工状況写真", w, "掘削", "床掘・底付け状況", t
    photo_type  = normalize_photo_type(photo_type, blackboard_text, scene_description)
    work        = normalize_work_name(work, blackboard_text)
    type_name   = normalize_type_name(type_name, detail_name, blackboard_text)
    detail_name = normalize_detail_name(detail_name, blackboard_text)
    return photo_type, work, type_name, detail_name, title


def fix_location(location, blackboard_text):
    text = safe_text(location) + "\n" + safe_text(blackboard_text)
    patterns = [
        r"測点\s*田番\s*([0-9０-９]+)",
        r"位置\s*田番\s*([0-9０-９]+)",
        r"田番\s*([0-9０-９]+)",
        r"\b([0-9]{1,2})\s*\(A\s*=",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            num = m.group(1).translate(str.maketrans("０１２３４５６７８９", "0123456789"))
            return f"田番{num}"
    return location if location not in ["不明", ""] else ""


def is_indoor_office(result: dict) -> bool:
    scene = "".join(safe_text(result.get(k)) for k in
                    ["reason","location","photo_type","work","type_name",
                     "detail_name","title","scene_description"])
    keywords = ["室内","会議室","事務所内","オフィス内","机","デスク","椅子",
                "パソコン","PC","書類","棚","ホワイトボード","蛍光灯",
                "天井","事務用品","打合せ"]
    return any(k in scene for k in keywords)

# ─────────────────────────────────────────
# AI解析（同期関数 → ThreadPoolExecutor で並列化）
# ─────────────────────────────────────────
def analyze_image(image_path: str) -> dict:
    """1枚の画像をAIで解析して分類情報を返す。"""
    fallback = {
        "usable": False, "reason": "AI失敗", "scene_description": "",
        "blackboard_text": "", "location": "", "photo_type": "その他",
        "work": "", "type_name": "", "detail_name": "", "title": "",
        "unrelated": True, "indoor_office": False, "confidence": 0,
    }
    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": """
工事写真を解析してください。黒板文字を最優先してください。
ただし写真全体も見てください。JSONのみ返してください。

{
  "usable": true,
  "reason": "",
  "scene_description": "",
  "blackboard_text": "",
  "location": "",
  "photo_type": "",
  "work": "",
  "type_name": "",
  "detail_name": "",
  "title": "",
  "unrelated": false,
  "indoor_office": false,
  "confidence": 90
}

photo_type は必ず以下から選択:
着手前及び完成写真 / 施工状況写真 / 安全管理写真 / 使用材料写真
品質管理写真 / 出来形管理写真 / 災害写真 / 事故写真 / その他

黒板が読めない場合は usable=false。scene_description は詳しく。
均平度→出来形管理写真 / 熱中症対策→安全管理写真
敷均し・転圧→均し工・敷均・転圧状況
据付・布設・設置→据付工・据付状況
掘削・床掘（敷均し等なし）→掘削・床掘・底付け状況
小用水路/用水路/水路/BF→水路工 / 土工・土方→土工
"""},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            }],
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except json.JSONDecodeError as e:
        log.error(f"JSONパースエラー ({image_path}): {e}")
        return fallback
    except Exception as e:
        log.error(f"AIエラー ({image_path}): {e}")
        return fallback

# ─────────────────────────────────────────
# 重複検出
# ─────────────────────────────────────────
hash_db: dict[str, str] = {}
hash_db_lock = asyncio.Lock() if False else None  # スレッドセーフ用（後述）

import threading
_hash_lock = threading.Lock()

def is_duplicate(image_path: str) -> bool:
    try:
        img = Image.open(image_path)
        h   = str(imagehash.phash(img))
        with _hash_lock:
            if h in hash_db:
                return True
            hash_db[h] = image_path
        return False
    except Exception as e:
        log.warning(f"ハッシュ計算失敗 ({image_path}): {e}")
        return False

# ─────────────────────────────────────────
# ファイル名重複対策
# ─────────────────────────────────────────
_used_names: set[str] = set()
_serial_lock = threading.Lock()
_serial_counter = [1]

def next_serial_name() -> str:
    """重複しないシリアル番号ファイル名を生成する。"""
    with _serial_lock:
        while True:
            name = f"P{_serial_counter[0]:07}.JPG"
            _serial_counter[0] += 1
            dest = os.path.join(PIC_FOLDER, name)
            if name not in _used_names and not os.path.exists(dest):
                _used_names.add(name)
                return name


def safe_copy(src: str, dst: str) -> bool:
    """コピー失敗時にエラーログを出してFalseを返す。"""
    try:
        shutil.copy2(src, dst)
        return True
    except PermissionError as e:
        log.error(f"権限エラー: {src} → {dst}: {e}")
    except OSError as e:
        log.error(f"コピー失敗: {src} → {dst}: {e}")
    return False

# ─────────────────────────────────────────
# マスター照合
# ─────────────────────────────────────────
def score_master_row(row, photo_type, work, type_name, detail_name, title, blackboard_text):
    score = 0
    r_photo_type = normalize_text(row.get("写真区分"))
    r_work       = normalize_text(row.get("工種"))
    r_type       = normalize_text(row.get("種別"))
    r_detail     = normalize_text(row.get("細別"))
    r_title      = normalize_text(row.get("写真タイトル"))
    n_photo_type = normalize_text(photo_type)
    n_work       = normalize_text(work)
    n_type       = normalize_text(type_name)
    n_detail     = normalize_text(detail_name)
    n_title      = normalize_text(title)
    source       = normalize_text(blackboard_text)

    if r_photo_type and r_photo_type == n_photo_type: score += 30
    if r_work and r_work == n_work:                   score += 120
    if r_type and r_type == n_type:                   score += 120
    if r_detail and r_detail == n_detail:             score += 180
    if r_title and r_title == n_title:                score += 80

    if ("敷均し" in source or "転圧" in source) and ("敷均し" in r_detail or "転圧" in r_detail): score += 300
    if ("敷均し" in source or "転圧" in source) and ("掘削" in r_type or "床掘" in r_detail):     score -= 250
    if "据付" in source and ("据付" in r_type or "据付" in r_detail):   score += 300
    if "据付" in source and ("掘削" in r_type or "床掘" in r_detail):   score -= 250
    if "均平度" in source and "均平度" in r_detail:                     score += 300
    if "均平度" in source and "基盤整地" in r_detail:                   score -= 200
    return score


def match_master(photo_type, work, type_name, detail_name, title, blackboard_text):
    best, best_score, best_source = None, 0, ""
    for row in project_master:
        s = score_master_row(row, photo_type, work, type_name, detail_name, title, blackboard_text)
        if s > best_score:
            best_score, best, best_source = s, row, "project"
    if best_score < 100:
        for row in common_master:
            s = int(score_master_row(row, photo_type, work, type_name, detail_name, title, blackboard_text) * 0.5)
            if s > best_score:
                best_score, best, best_source = s, row, "common"
    return best, best_score, best_source


def master_conflict(matched, blackboard_text) -> bool:
    if not matched:
        return False
    source   = normalize_text(blackboard_text)
    m_type   = normalize_text(matched.get("種別"))
    m_detail = normalize_text(matched.get("細別"))
    if ("敷均し" in source or "転圧" in source) and ("掘削" in m_type or "床掘" in m_detail): return True
    if "据付" in source and ("掘削" in m_type or "床掘" in m_detail):                        return True
    if "均平度" in source and "基盤整地" in m_detail:                                        return True
    return False

# ─────────────────────────────────────────
# CSVヘルパー
# ─────────────────────────────────────────
def make_check_row(filename, reason, result, photo_type, work, type_name, detail_name, title, score, source):
    return {
        "ファイル名": filename, "確認理由": reason,
        "AI理由": safe_text(result.get("reason")),
        "写真内容": safe_text(result.get("scene_description")),
        "黒板文字": safe_text(result.get("blackboard_text")),
        "写真区分": photo_type, "工種": work, "種別": type_name,
        "細別": detail_name, "写真タイトル": title,
        "master一致": score, "master種別": source,
        "信頼度": result.get("confidence", ""),
    }

def make_result_row(filename, status, reason, photo_type, work, type_name, detail_name, title, score, source, saved_name=""):
    return {
        "ファイル名": filename, "判定": status, "理由": reason, "保存名": saved_name,
        "写真区分": photo_type, "工種": work, "種別": type_name,
        "細別": detail_name, "写真タイトル": title,
        "master一致": score, "master種別": source,
    }

def make_candidate_row(filename, reason, result, photo_type, work, type_name, detail_name, title, score, source):
    return {
        "ファイル名": filename, "追加理由": reason,
        "写真区分": photo_type, "工種": work, "種別": type_name,
        "細別": detail_name, "写真タイトル": title,
        "master一致": score, "master種別": source,
        "信頼度": result.get("confidence", ""),
        "黒板文字": safe_text(result.get("blackboard_text")),
        "写真内容": safe_text(result.get("scene_description")),
    }

def write_csv(path: str, rows: list[dict], empty_label: str = "データなし"):
    if rows:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    else:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerow([empty_label])
    log.info(f"CSV出力: {path} ({len(rows)}件)")

# ─────────────────────────────────────────
# 1枚の画像を処理するメイン関数
# ─────────────────────────────────────────
def process_image(img_path: Path) -> dict:
    """
    1枚の画像を処理して結果dictを返す。
    {check_row, result_row, candidate_row, xml_info} のいずれかが入る。
    """
    result_data = {
        "check_row": None,
        "result_row": None,
        "candidate_row": None,
        "xml_info": None,
        "filename": img_path.name,
    }

    log.info(f"処理中: {img_path.name}")

    # 重複チェック
    if is_duplicate(str(img_path)):
        log.info(f"重複 → EXCLUDE: {img_path.name}")
        safe_copy(str(img_path), os.path.join(EXCLUDE_FOLDER, img_path.name))
        result_data["result_row"] = make_result_row(img_path.name, "EXCLUDE", "重複検出", "", "", "", "", "", 0, "")
        return result_data

    # AI解析
    result = analyze_image(str(img_path))

    usable      = result.get("usable", False)
    unrelated   = result.get("unrelated", False)
    blackboard_text  = apply_synonym(safe_text(result.get("blackboard_text")))
    scene_description = safe_text(result.get("scene_description"))
    location    = safe_text(result.get("location"))
    photo_type  = safe_text(result.get("photo_type"))
    work        = safe_text(result.get("work"))
    type_name   = safe_text(result.get("type_name"))
    detail_name = safe_text(result.get("detail_name"))
    title       = safe_text(result.get("title"))
    confidence  = result.get("confidence", 0)

    photo_type, work, type_name, detail_name, title = apply_keyword_rules(
        photo_type, work, type_name, detail_name, title, blackboard_text, scene_description)
    photo_type, work, type_name, detail_name, title = final_rule_fix(
        photo_type, work, type_name, detail_name, title, blackboard_text, scene_description)
    location = fix_location(location, blackboard_text)

    log.info(f"  黒板:{blackboard_text[:40]} 区分:{photo_type} 工種:{work} 種別:{type_name} 細別:{detail_name} 信頼度:{confidence}")

    # 黒板なし
    if not blackboard_text.strip():
        log.info(f"  黒板なし → CHECK")
        safe_copy(str(img_path), os.path.join(CHECK_FOLDER, img_path.name))
        result_data["check_row"]   = make_check_row(img_path.name, "黒板なし", result, photo_type, work, type_name, detail_name, title, 0, "")
        result_data["result_row"]  = make_result_row(img_path.name, "CHECK", "黒板なし", photo_type, work, type_name, detail_name, title, 0, "")
        return result_data

    # 室内・事務所
    if is_indoor_office(result):
        log.info(f"  室内写真 → CHECK")
        safe_copy(str(img_path), os.path.join(CHECK_FOLDER, img_path.name))
        result_data["check_row"]   = make_check_row(img_path.name, "室内・事務所写真", result, photo_type, work, type_name, detail_name, title, 0, "")
        result_data["result_row"]  = make_result_row(img_path.name, "CHECK", "室内・事務所写真", photo_type, work, type_name, detail_name, title, 0, "")
        return result_data

    # マスター照合
    matched, score, source = match_master(photo_type, work, type_name, detail_name, title, blackboard_text)

    if matched and not master_conflict(matched, blackboard_text):
        photo_type  = matched.get("写真区分") or photo_type
        work        = matched.get("工種")      or work
        type_name   = matched.get("種別")      or type_name
        detail_name = matched.get("細別")      or detail_name
        title       = matched.get("写真タイトル") or title
        photo_type, work, type_name, detail_name, title = final_rule_fix(
            photo_type, work, type_name, detail_name, title, blackboard_text, scene_description)
    elif matched and master_conflict(matched, blackboard_text):
        log.info(f"  master衝突 → AI分類優先")
        result_data["candidate_row"] = make_candidate_row(img_path.name, "master衝突候補", result, photo_type, work, type_name, detail_name, title, score, source)
    else:
        result_data["candidate_row"] = make_candidate_row(img_path.name, "master未登録候補", result, photo_type, work, type_name, detail_name, title, score, source)

    # 無関係
    if unrelated:
        log.info(f"  無関係 → EXCLUDE")
        safe_copy(str(img_path), os.path.join(EXCLUDE_FOLDER, img_path.name))
        result_data["result_row"] = make_result_row(img_path.name, "EXCLUDE", "別現場または無関係", photo_type, work, type_name, detail_name, title, score, source)
        return result_data

    # usable false
    if not usable:
        log.info(f"  usable=false → CHECK")
        safe_copy(str(img_path), os.path.join(CHECK_FOLDER, img_path.name))
        result_data["check_row"]  = make_check_row(img_path.name, "usable false", result, photo_type, work, type_name, detail_name, title, score, source)
        result_data["result_row"] = make_result_row(img_path.name, "CHECK", "usable false", photo_type, work, type_name, detail_name, title, score, source)
        return result_data

    # 分類不足
    if not work or not type_name or not detail_name:
        log.info(f"  分類不足 → CHECK")
        safe_copy(str(img_path), os.path.join(CHECK_FOLDER, img_path.name))
        result_data["check_row"]     = make_check_row(img_path.name, "分類不足", result, photo_type, work, type_name, detail_name, title, score, source)
        result_data["result_row"]    = make_result_row(img_path.name, "CHECK", "分類不足", photo_type, work, type_name, detail_name, title, score, source)
        result_data["candidate_row"] = make_candidate_row(img_path.name, "分類不足", result, photo_type, work, type_name, detail_name, title, score, source)
        return result_data

    # 採用
    new_name = next_serial_name()
    if not safe_copy(str(img_path), os.path.join(PIC_FOLDER, new_name)):
        # コピー失敗 → CHECK扱い
        safe_copy(str(img_path), os.path.join(CHECK_FOLDER, img_path.name))
        result_data["check_row"]  = make_check_row(img_path.name, "コピー失敗", result, photo_type, work, type_name, detail_name, title, score, source)
        result_data["result_row"] = make_result_row(img_path.name, "CHECK", "コピー失敗", photo_type, work, type_name, detail_name, title, score, source)
        return result_data

    log.info(f"  採用 → {new_name}")
    result_data["result_row"] = make_result_row(img_path.name, "採用", "OK", photo_type, work, type_name, detail_name, title, score, source, new_name)
    result_data["xml_info"] = {
        "new_name": new_name,
        "photo_type": photo_type,
        "work": work,
        "type_name": type_name,
        "detail_name": detail_name,
        "title": title,
        "location": location,
    }
    return result_data

# ─────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────
def main():
    # 画像ファイル収集（重複パス排除）
    image_files_dict = {}
    for ext in ["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"]:
        for p in Path(INPUT_FOLDER).rglob(ext):
            image_files_dict[str(p.resolve()).lower()] = p
    image_files = sorted(image_files_dict.values(), key=lambda x: str(x).lower())

    log.info("=" * 50)
    log.info(f"工事写真解析開始 - 対象枚数: {len(image_files)}")
    log.info("=" * 50)

    check_rows, result_rows, candidate_rows, xml_infos = [], [], [], []

    # ThreadPoolExecutor で並列AI呼び出し
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_image, p): p for p in image_files}
        for future in as_completed(futures):
            img_path = futures[future]
            try:
                data = future.result()
            except Exception as e:
                log.error(f"予期しないエラー ({img_path.name}): {e}")
                result_rows.append(make_result_row(img_path.name, "ERROR", str(e), "", "", "", "", "", 0, ""))
                continue

            if data["check_row"]:     check_rows.append(data["check_row"])
            if data["result_row"]:    result_rows.append(data["result_row"])
            if data["candidate_row"]: candidate_rows.append(data["candidate_row"])
            if data["xml_info"]:      xml_infos.append(data["xml_info"])

    # CSV出力
    write_csv(CHECK_CSV_PATH, check_rows, "CHECKなし")
    write_csv(RESULT_CSV_PATH, result_rows, "結果なし")
    write_csv(ADD_CANDIDATE_CSV_PATH, candidate_rows, "追加候補なし")

    # XML生成
    if not xml_infos:
        log.info("採用写真なし → PHOTO.XML 生成スキップ")
    else:
        root = Element("photodata")
        root.set("DTD_version", "05")
        base_info = SubElement(root, "基礎情報")
        SubElement(base_info, "写真フォルダ名").text   = "PHOTO/PIC"
        SubElement(base_info, "参考図フォルダ名").text = "PHOTO/DRA"
        SubElement(base_info, "適用要領基準").text     = "土木202303-01"

        # xml_infos はシリアル番号順に並び替え（並列処理で順不同になるため）
        xml_infos.sort(key=lambda x: x["new_name"])

        for i, info in enumerate(xml_infos, start=1):
            photo_info = SubElement(root, "写真情報")
            file_info  = SubElement(photo_info, "写真ファイル情報")
            SubElement(file_info, "シリアル番号").text = str(i)
            SubElement(file_info, "写真ファイル名").text = info["new_name"]
            SubElement(file_info, "メディア番号").text   = "1"

            category = SubElement(photo_info, "撮影工種区分")
            SubElement(category, "写真-大分類").text = "工事"
            SubElement(category, "写真区分").text    = info["photo_type"]
            SubElement(category, "工種").text        = info["work"]
            SubElement(category, "種別").text        = info["type_name"]
            SubElement(category, "細別").text        = info["detail_name"]
            SubElement(category, "写真タイトル").text = info["title"]

            shoot = SubElement(photo_info, "撮影情報")
            SubElement(shoot, "撮影年月日").text = datetime.now().strftime("%Y-%m-%d")
            SubElement(shoot, "撮影箇所").text   = info["location"]

            SubElement(photo_info, "代表写真").text   = "0"
            SubElement(photo_info, "提出頻度写真").text = "0"

        try:
            xml_body = tostring(root, encoding="shift_jis", xml_declaration=False)
            with open(PHOTO_XML_PATH, "wb") as f:
                f.write(b'<?xml version="1.0" encoding="Shift_JIS"?>\r\n')
                f.write(b'<!DOCTYPE photodata SYSTEM "PHOTO05.DTD">\r\n')
                f.write(xml_body)
            log.info(f"PHOTO.XML 完成: {PHOTO_XML_PATH}")
        except Exception as e:
            log.error(f"PHOTO.XML 書き込み失敗: {e}")

    log.info("=" * 50)
    log.info(f"完了 - 採用:{len(xml_infos)} CHECK:{len(check_rows)} 候補:{len(candidate_rows)}")
    log.info("=" * 50)


if __name__ == "__main__":
    main()
