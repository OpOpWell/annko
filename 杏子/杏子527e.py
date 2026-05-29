"""
工事写真自動整理システム v2.9
v2.7安定版ベース + 日本語パス対応 + 水路優先 + 田番厳格化 + CHECK調整版
"""

import os
import shutil
import base64
import json
import csv
import re
import logging
import threading
from pathlib import Path
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, tostring
from concurrent.futures import ThreadPoolExecutor, as_completed

import yaml
import cv2
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv
from PIL import Image
import imagehash


# =========================================================
# ログ
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("photo_organizer.log", encoding="utf-8"),
    ],
)

log = logging.getLogger(__name__)


# =========================================================
# config
# =========================================================

def load_config(config_path="config.yml"):
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        log.info(f"設定ファイル読込: {config_path}")
        return cfg

    log.warning("config.yml が見つかりません。デフォルト設定を使用します。")

    return {
        "base_folder": r"C:\Users\user\foolder\杏子",
        "input_folder": r"C:\Users\user\OneDrive\hhh",
        "openai_model": "gpt-4.1-mini",
        "max_workers": 5,
    }


CONFIG = load_config()

BASE_FOLDER = CONFIG["base_folder"]
INPUT_FOLDER = CONFIG["input_folder"]
MODEL = CONFIG.get("openai_model", "gpt-4.1-mini")
MAX_WORKERS = CONFIG.get("max_workers", 5)

MASTER_PROJECT = os.path.join(BASE_FOLDER, "master_project.csv")
MASTER_COMMON = os.path.join(BASE_FOLDER, "master_common.csv")
SYNONYM_MASTER = os.path.join(BASE_FOLDER, "synonym_master.csv")
KEYWORD_RULES = os.path.join(BASE_FOLDER, "keyword_rules.csv")

PHOTO_ROOT = os.path.join(BASE_FOLDER, "selected_photos", "PHOTO")
PHOTO_XML_PATH = os.path.join(PHOTO_ROOT, "PHOTO.XML")
PIC_FOLDER = os.path.join(PHOTO_ROOT, "PIC")
CHECK_FOLDER = os.path.join(PHOTO_ROOT, "CHECK")
EXCLUDE_FOLDER = os.path.join(PHOTO_ROOT, "EXCLUDE")
OCR_DEBUG_FOLDER = os.path.join(PHOTO_ROOT, "OCR_DEBUG")

CHECK_CSV_PATH = os.path.join(PHOTO_ROOT, "CHECK一覧.csv")
RESULT_CSV_PATH = os.path.join(PHOTO_ROOT, "処理結果一覧.csv")
ADD_CANDIDATE_CSV_PATH = os.path.join(PHOTO_ROOT, "master追加候補.csv")
TREE_IMPORT_CSV_PATH = os.path.join(PHOTO_ROOT, "tree_import.csv")

SOURCE_DTD = os.path.join(BASE_FOLDER, "PHOTO05.DTD")


# =========================================================
# folder
# =========================================================

for folder in [PHOTO_ROOT, PIC_FOLDER, CHECK_FOLDER, EXCLUDE_FOLDER, OCR_DEBUG_FOLDER]:
    os.makedirs(folder, exist_ok=True)

if os.path.exists(SOURCE_DTD):
    shutil.copy2(SOURCE_DTD, os.path.join(PHOTO_ROOT, "PHOTO05.DTD"))
    log.info("PHOTO05.DTD コピーOK")
else:
    log.warning(f"PHOTO05.DTD が見つかりません: {SOURCE_DTD}")


# =========================================================
# OpenAI
# =========================================================

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# =========================================================
# utility
# =========================================================

def safe_text(v):
    if v is None:
        return ""
    return str(v).strip()


def zenkaku_to_hankaku(text):
    return safe_text(text).translate(
        str.maketrans("０１２３４５６７８９", "0123456789")
    )


def normalize_text(text):
    text = safe_text(text)

    replace_map = {
        " ": "",
        "　": "",
        "\n": "",
        "\r": "",

        "施工": "",
        "状況": "",
        "写真": "",

        "床堀": "床掘",
        "床掘り": "床掘",
        "掘さく": "掘削",
        "堀削": "掘削",

        "底付": "底付け",
        "床付": "床付け",

        "表土剥取": "表土剥ぎ取り",
        "表土はぎ取り": "表土剥ぎ取り",
        "表土剥ぎ取": "表土剥ぎ取り",

        "敷き均し": "敷均し",
        "敷均": "敷均し",

        "据え付け": "据付",
        "据付け": "据付",
        "布設": "据付",
        "設置": "据付",

        "平坦度": "均平度",
        "平均平度": "均平度",

        "甘船整地丁": "基盤整地",
        "甘船整地工": "基盤整地",
        "甘縄整地丁": "基盤整地",
        "甘縄整地工": "基盤整地",
        "甘鰐整地丁": "基盤整地",
        "甘鰐整地工": "基盤整地",
        "甘乾整地丁": "基盤整地",
        "甘乾整地工": "基盤整地",
        "甘紺整地丁": "基盤整地",
        "甘紺整地工": "基盤整地",
        "甘艦整地丁": "基盤整地",
        "甘艦整地工": "基盤整地",
        "甘幹整地丁": "基盤整地",
        "甘幹整地工": "基盤整地",
        "甘鮒整地丁": "基盤整地",
        "甘鮒整地工": "基盤整地",
        "甘鱒整地丁": "基盤整地",
        "甘鱒整地工": "基盤整地",

        "基磐整地": "基盤整地",
        "基板整地": "基盤整地",
        "基盤整池": "基盤整地",
    }

    for old, new in replace_map.items():
        text = text.replace(old, new)

    return text


def load_csv(path):
    if not os.path.exists(path):
        log.warning(f"CSVが見つかりません: {path}")
        return []

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


project_master = load_csv(MASTER_PROJECT)
common_master = load_csv(MASTER_COMMON)
synonym_master = load_csv(SYNONYM_MASTER)
keyword_rules = load_csv(KEYWORD_RULES)

log.info(
    f"master_project: {len(project_master)}件, "
    f"master_common: {len(common_master)}件, "
    f"synonym: {len(synonym_master)}件, "
    f"keyword_rules: {len(keyword_rules)}件"
)


# =========================================================
# 日本語パス対応 OpenCV
# =========================================================

def cv2_imread_unicode(path):
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        log.warning(f"画像読込失敗: {path}: {e}")
        return None


def cv2_imwrite_unicode(path, img):
    try:
        ext = os.path.splitext(str(path))[1]
        ok, buf = cv2.imencode(ext, img)

        if ok:
            buf.tofile(str(path))
            return True

        return False

    except Exception as e:
        log.warning(f"画像保存失敗: {path}: {e}")
        return False


# =========================================================
# OCR前処理
# =========================================================

def preprocess_blackboard(image_path):
    try:
        img = cv2_imread_unicode(image_path)

        if img is None:
            return None

        h, w = img.shape[:2]
        target_w = 1800

        if w < target_w:
            scale = target_w / w
            img = cv2.resize(
                img,
                None,
                fx=scale,
                fy=scale,
                interpolation=cv2.INTER_CUBIC,
            )

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        denoise = cv2.fastNlMeansDenoising(
            gray,
            None,
            10,
            7,
            21,
        )

        clahe = cv2.createCLAHE(
            clipLimit=2.5,
            tileGridSize=(8, 8),
        )

        contrast = clahe.apply(denoise)

        kernel = np.array([
            [-1, -1, -1],
            [-1,  9, -1],
            [-1, -1, -1],
        ])

        sharp = cv2.filter2D(contrast, -1, kernel)

        binary = cv2.adaptiveThreshold(
            sharp,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            2,
        )

        debug_path = os.path.join(
            OCR_DEBUG_FOLDER,
            f"ocr_{Path(image_path).stem}.png"
        )

        cv2_imwrite_unicode(debug_path, binary)

        return debug_path

    except Exception as e:
        log.error(f"OCR前処理失敗: {image_path}: {e}")
        return None


def image_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


# =========================================================
# synonym
# =========================================================

def apply_synonym(text):
    text = safe_text(text)

    for row in synonym_master:
        src = safe_text(row.get("現場語"))
        dst = safe_text(row.get("正式語"))

        if src and dst:
            text = text.replace(src, dst)

    return text


# =========================================================
# 工事番号 / 田番
# =========================================================

def looks_like_date(value):
    value = safe_text(value)

    if re.search(r"[0-9]{4}[-/年]", value):
        return True

    if "月" in value and "日" in value:
        return True

    if "令和" in value and "年" in value:
        return True

    return False


def clean_construction_no(value):
    value = zenkaku_to_hankaku(value)
    value = value.replace("－", "-").strip()

    if not value:
        return ""

    if looks_like_date(value):
        return ""

    if value.upper().startswith("NO"):
        return ""

    if value.startswith("N:"):
        return ""

    if re.match(r"^[0-9]{1,2}-[0-9]{1,2}$", value):
        return ""

    if "=" in value:
        return ""

    if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", value) and not re.search(r"[0-9]", value):
        return ""

    patterns = [
        r"\b([0-9]{5}-?[A-Za-z][0-9]{2})\b",
        r"\b([0-9]{4,6}-[0-9]{2,4})\b",
        r"\b([0-9]{4,6}[A-Za-z][0-9]{2})\b",
        r"\b([A-Za-z][0-9]-[A-Za-z0-9]+)\b",
    ]

    for p in patterns:
        m = re.search(p, value)
        if m:
            return m.group(1)

    return ""


def clean_field_no(value):
    value = zenkaku_to_hankaku(value).strip()

    if not value:
        return ""

    if "=" in value:
        return ""

    if "号" in value:
        return ""

    if value.upper().startswith("NO"):
        return ""

    if value.upper().startswith("N:"):
        return ""

    if re.search(r"[A-Za-z]", value):
        return ""

    if re.match(r"^[1-9][0-9]{2,}-[0-9]+$", value):
        return ""

    m = re.search(r"\b([0-9]{1,2}(?:-[0-9]{1,2})?)\b", value)

    if m:
        return m.group(1)

    return ""


def extract_site_numbers(location, blackboard_text):
    raw = zenkaku_to_hankaku(
        safe_text(location) + "\n" + safe_text(blackboard_text)
    )

    construction_no = ""
    field_no = ""

    construction_patterns = [
        r"工事番号[:：]?\s*([A-Za-z0-9\-－_]+)",
        r"工事No\.?[:：]?\s*([A-Za-z0-9\-－_]+)",
        r"工事NO\.?[:：]?\s*([A-Za-z0-9\-－_]+)",
        r"施工番号[:：]?\s*([A-Za-z0-9\-－_]+)",
    ]

    field_patterns = [
        r"田番[:：]?\s*([0-9]{1,3}(?:-[0-9]{1,3})?)",
        r"田番号[:：]?\s*([0-9]{1,3}(?:-[0-9]{1,3})?)",
        r"場所[:：]?\s*田番[:：]?\s*([0-9]{1,3}(?:-[0-9]{1,3})?)",
        r"位置[:：]?\s*田番[:：]?\s*([0-9]{1,3}(?:-[0-9]{1,3})?)",
    ]

    for p in construction_patterns:
        m = re.search(p, raw, flags=re.IGNORECASE)
        if m:
            construction_no = clean_construction_no(m.group(1))
            if construction_no:
                break

    if not construction_no:
        m = re.search(r"([0-9]{5}[-]?[A-Za-z][0-9]{2})", raw)
        if m:
            construction_no = clean_construction_no(m.group(1))

    if not construction_no:
        m = re.search(r"\b([0-9]{4,6}-[0-9]{2,4})\b", raw)
        if m:
            construction_no = clean_construction_no(m.group(1))

    # 田番は「田番」「田番号」「位置 田番」「場所 田番」がある時だけ拾う
    if "田番" in raw or "田番号" in raw:
        for p in field_patterns:
            m = re.search(p, raw)
            if m:
                field_no = clean_field_no(m.group(1))
                if field_no:
                    break

    parts = []

    if construction_no:
        parts.append(f"工事番号{construction_no}")

    if field_no:
        parts.append(f"田番{field_no}")

    return {
        "construction_no": construction_no,
        "field_no": field_no,
        "shoot_location": " ".join(parts),
    }


# =========================================================
# normalize
# =========================================================

def normalize_photo_type(photo_type, blackboard_text="", scene_description=""):
    text = normalize_text(
        safe_text(photo_type) + blackboard_text + scene_description
    )

    construction_keywords = [
        "側溝",
        "水路",
        "小用水路",
        "用水路",
        "掘削",
        "床掘",
        "床付け",
        "底付け",
        "表土",
        "敷均し",
        "転圧",
        "据付",
        "基盤整地",
    ]

    if any(k in text for k in construction_keywords):
        return "施工状況写真"

    if "熱中症" in text or "安全" in text:
        return "安全管理写真"

    if "均平度" in text or "出来形" in text or "Xmax" in blackboard_text or "Xmin" in blackboard_text:
        return "出来形管理写真"

    if "品質" in text:
        return "品質管理写真"

    if "材料" in text:
        return "使用材料写真"

    if "完成" in text or "着手前" in text:
        return "着手前及び完成写真"

    return safe_text(photo_type) or "施工状況写真"


def normalize_work_name(work, blackboard_text="", scene_description=""):
    text = normalize_text(
        safe_text(work) + blackboard_text + scene_description
    )

    if "熱中症" in text or "安全" in text:
        return "安全管理"

    # 水路を側溝より優先
    if "小用水路" in text or "用水路" in text or "水路" in text or "BF" in text:
        return "水路工"

    if "側溝" in text:
        return "側溝工"

    if "路盤" in text:
        return "路盤工"

    if "土工" in text or "土方" in text:
        return "土工"

    if "基盤整地" in text:
        if "土工" in text:
            return "土工"
        return safe_text(work) or "基盤整地工"

    if "整地" in text or "均平度" in text:
        return safe_text(work) or "整地工"

    return safe_text(work) or "土工"


def fix_work_for_type(work, type_name, detail_name):
    w = safe_text(work)
    t = normalize_text(type_name)
    d = normalize_text(detail_name)

    if w in ["掘削", "床掘", "床付け", "底付け"]:
        return "土工"

    if any(k in t + d for k in ["掘削", "床掘", "床付け", "底付け", "表土"]):
        if not w or w in ["掘削", "床掘", "床付け", "底付け"]:
            return "土工"

    return w


def make_title(work, type_name, detail_name, current_title=""):
    current_title = safe_text(current_title)

    if current_title and current_title not in ["不明", "その他"]:
        return current_title

    parts = [safe_text(work), safe_text(type_name), safe_text(detail_name)]
    parts = [p for p in parts if p]

    return " ".join(parts)


# =========================================================
# keyword rules
# =========================================================

def apply_keyword_rules(photo_type, work, type_name, detail_name, title, blackboard_text, scene_description):
    if not keyword_rules:
        return photo_type, work, type_name, detail_name, title

    source = normalize_text(apply_synonym(blackboard_text + "\n" + scene_description))

    best = None
    best_score = 0

    for row in keyword_rules:
        keywords = safe_text(row.get("keyword") or row.get("キーワード"))

        if not keywords:
            continue

        score = 0

        for kw in re.split(r"[,\n、/／]+", keywords):
            kw2 = normalize_text(kw)

            if kw2 and kw2 in source:
                score += 1

        if score > best_score:
            best_score = score
            best = row

    if best and best_score > 0:
        photo_type = safe_text(best.get("写真区分")) or photo_type
        work = safe_text(best.get("工種")) or work
        type_name = safe_text(best.get("種別")) or type_name
        detail_name = safe_text(best.get("細別")) or detail_name
        title = safe_text(best.get("写真タイトル")) or title

    return photo_type, work, type_name, detail_name, title


# =========================================================
# final rules
# =========================================================

def final_rule_fix(photo_type, work, type_name, detail_name, title, blackboard_text, scene_description):
    raw = apply_synonym(
        safe_text(blackboard_text) + "\n" + safe_text(scene_description)
    )

    src = normalize_text(raw)

    fixed_photo_type = normalize_photo_type(photo_type, blackboard_text, scene_description)
    fixed_work = normalize_work_name(work, blackboard_text, scene_description)

    if "熱中症" in src:
        return "安全管理写真", "安全管理", "安全管理", "熱中症対策", "熱中症対策"

    # 水路工を側溝工より優先
    if "小用水路" in src or "用水路" in src or "水路" in src or "BF" in src:
        if "床付け" in src:
            return "施工状況写真", "水路工", "床付け", "床付け状況", "水路工 床付け状況"

        if "底付け" in src:
            return "施工状況写真", "水路工", "底付け", "底付け状況", "水路工 底付け状況"

        if "床掘" in src:
            return "施工状況写真", "水路工", "床掘", "床掘状況", "水路工 床掘状況"

        if "掘削" in src or "根切" in src:
            return "施工状況写真", "水路工", "掘削", "掘削状況", "水路工 掘削状況"

        if "据付" in src:
            return "施工状況写真", "水路工", "据付工", "据付状況", "水路工 据付状況"

        if "敷均し" in src or "転圧" in src:
            return "施工状況写真", "水路工", "均し工", "敷均・転圧状況", "水路工 敷均・転圧状況"

        return "施工状況写真", "水路工", "水路工", "水路施工状況", "水路工 施工状況"

    if "草刈" in src or "増水" in src or "用水路管理" in src:
        return "施工状況写真", "水路工", "その他", "要確認", "水路工 要確認"

    if "側溝" in src:
        if "据付" in src:
            return "施工状況写真", "側溝工", "据付工", "側溝据付状況", "側溝 据付状況"

        if "床掘" in src:
            return "施工状況写真", "側溝工", "床掘", "側溝床掘状況", "側溝 床掘状況"

        if "掘削" in src:
            return "施工状況写真", "側溝工", "掘削", "側溝掘削状況", "側溝 掘削状況"

        if "床付け" in src:
            return "施工状況写真", "側溝工", "床付け", "側溝床付け状況", "側溝 床付け状況"

        if "底付け" in src:
            return "施工状況写真", "側溝工", "底付け", "側溝底付け状況", "側溝 底付け状況"

        return "施工状況写真", "側溝工", "側溝工", "側溝施工状況", "側溝 施工状況"

    if "表土" in src:
        return "施工状況写真", "土工", "表土剥ぎ取り", "表土剥ぎ取り状況", "表土剥ぎ取り状況"

    if "床付け" in src:
        fixed_work = fix_work_for_type(fixed_work, "床付け", "床付け状況")
        return "施工状況写真", fixed_work, "床付け", "床付け状況", "床付け状況"

    if "底付け" in src:
        fixed_work = fix_work_for_type(fixed_work, "底付け", "底付け状況")
        return "施工状況写真", fixed_work, "底付け", "底付け状況", "底付け状況"

    if "床掘" in src:
        fixed_work = fix_work_for_type(fixed_work, "床掘", "床掘状況")
        return "施工状況写真", fixed_work, "床掘", "床掘状況", "床掘状況"

    if "掘削" in src or "根切" in src:
        fixed_work = fix_work_for_type(fixed_work, "掘削", "掘削状況")
        return "施工状況写真", fixed_work, "掘削", "掘削状況", "掘削状況"

    if "据付" in src:
        return "施工状況写真", fixed_work, "据付工", "据付状況", "据付状況"

    if "基盤整地" in src:
        if "土工" in src or fixed_work == "土工":
            fixed_work = "土工"
        else:
            fixed_work = "基盤整地工"

        return (
            "施工状況写真",
            fixed_work,
            "基盤整地",
            "基盤整地状況",
            f"{fixed_work} 基盤整地状況",
        )

    if "敷均し" in src or "転圧" in src:
        return "施工状況写真", fixed_work, "均し工", "敷均・転圧状況", "敷均・転圧状況"

    if "均平度" in src or "Xmax" in blackboard_text or "Xmin" in blackboard_text:
        return "出来形管理写真", "整地工", "整地仕上げ", "均平度", "均平度"

    fixed_work = fix_work_for_type(fixed_work, type_name, detail_name)
    fixed_title = make_title(fixed_work, type_name, detail_name, title)

    return fixed_photo_type, fixed_work, type_name, detail_name, fixed_title


# =========================================================
# indoor
# =========================================================

def is_indoor_office(result):
    scene = "".join(
        safe_text(result.get(k))
        for k in [
            "reason",
            "location",
            "photo_type",
            "work",
            "type_name",
            "detail_name",
            "title",
            "scene_description",
        ]
    )

    scene2 = normalize_text(scene)

    field_keywords = [
        "均平度",
        "掘削",
        "床掘",
        "床付け",
        "底付け",
        "側溝",
        "水路",
        "小用水路",
        "用水路",
        "基盤整地",
        "表土",
        "敷均し",
        "転圧",
        "据付",
    ]

    if any(k in scene2 for k in field_keywords):
        return False

    indoor_keywords = [
        "室内",
        "会議室",
        "事務所",
        "事務所内",
        "オフィス",
        "机",
        "椅子",
        "PC",
        "パソコン",
        "棚",
        "ホワイトボード",
    ]

    return any(k in scene for k in indoor_keywords)


# =========================================================
# AI
# =========================================================

def analyze_image(image_path):
    fallback = {
        "usable": False,
        "reason": "AI失敗",
        "scene_description": "",
        "blackboard_text": "",
        "location": "",
        "construction_no": "",
        "field_no": "",
        "photo_type": "その他",
        "work": "",
        "type_name": "",
        "detail_name": "",
        "title": "",
        "unrelated": True,
        "confidence": 0,
    }

    try:
        original_b64 = image_to_base64(image_path)

        processed_path = preprocess_blackboard(image_path)
        processed_b64 = None

        if processed_path and os.path.exists(processed_path):
            processed_b64 = image_to_base64(processed_path)

        content = [
            {
                "type": "text",
                "text": """
工事写真を解析してください。

元画像とOCR前処理画像を渡します。
元画像で写真全体を見て、OCR前処理画像で黒板文字を読み取ってください。

黒板文字を最優先してください。
ただし写真全体も必ず確認してください。
JSONのみ返してください。

必ずこの形式で返してください。

{
  "usable": true,
  "reason": "",
  "scene_description": "",
  "blackboard_text": "",
  "location": "",
  "construction_no": "",
  "field_no": "",
  "photo_type": "",
  "work": "",
  "type_name": "",
  "detail_name": "",
  "title": "",
  "unrelated": false,
  "confidence": 90
}

分類ルール:
- 小用水路 / 用水路 / 水路 / BF → 水路工を優先
- 側溝 → 施工状況写真 / 側溝工
- 側溝を均平度や整地工にしない
- 土工 / 土方 → 土工
- 表土 / 表土剥ぎ取り → 表土剥ぎ取り
- 掘削 → 掘削 / 掘削状況
- 床掘 → 床掘 / 床掘状況
- 床付け → 床付け / 床付け状況
- 底付け → 底付け / 底付け状況
- 底付けと床付けは分ける
- 床掘と掘削もできるだけ分ける
- 掘削を敷均し・転圧にしない
- 基盤整地は、土工と書いてある場合は土工の基盤整地として扱う
- 甘船整地丁 / 甘乾整地丁 などは基盤整地として扱う
- 基盤整地を整地仕上げや均平度にしない
- 均平度 → 出来形管理写真 / 整地工 / 整地仕上げ / 均平度
- ただし側溝、水路、掘削、床掘、表土、基盤整地がある場合は均平度よりそちらを優先
- 熱中症対策 → 安全管理写真
- 工事番号と田番は分けて読む
- 工事番号は 02502-K06 / 02502K06 / 2023-0457 のような形式を拾う
- 日付を工事番号にしない
- Q= / W= / H= / N: / NO.+ は田番ではない
- 測点 NO.+50m は田番ではない
- 小用水路 10-1 の 10-1 は田番とは限らない
- 黒板が少しでも読める場合は usable=true
- 本当に黒板が読めない場合だけ usable=false
"""
            },
            {
                "type": "text",
                "text": "これは元画像です。写真全体、現場状況、黒板位置を確認してください。"
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{original_b64}"
                },
            },
        ]

        if processed_b64:
            content.extend([
                {
                    "type": "text",
                    "text": "これはOCR前処理画像です。黒板文字の読み取りに使ってください。"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{processed_b64}"
                    },
                },
            ])

        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "user",
                    "content": content,
                }
            ],
            response_format={"type": "json_object"},
        )

        return json.loads(response.choices[0].message.content)

    except Exception as e:
        log.error(f"AIエラー ({image_path}): {e}")
        return fallback


# =========================================================
# duplicate / copy / serial
# =========================================================

hash_db = {}
hash_lock = threading.Lock()

used_names = set()
serial_lock = threading.Lock()
serial_counter = [1]


def is_duplicate(image_path):
    try:
        img = Image.open(image_path)
        h = str(imagehash.phash(img))

        with hash_lock:
            if h in hash_db:
                return True

            hash_db[h] = image_path

        return False

    except Exception as e:
        log.warning(f"ハッシュ計算失敗: {image_path}: {e}")
        return False


def next_serial_name():
    with serial_lock:
        while True:
            name = f"P{serial_counter[0]:07}.JPG"
            serial_counter[0] += 1

            dest = os.path.join(PIC_FOLDER, name)

            if name not in used_names and not os.path.exists(dest):
                used_names.add(name)
                return name


def safe_copy(src, dst):
    try:
        shutil.copy2(src, dst)
        return True

    except Exception as e:
        log.error(f"コピー失敗: {src} → {dst}: {e}")
        return False


# =========================================================
# CSV rows
# =========================================================

def make_result_row(filename, status, reason, photo_type, work, type_name, detail_name, title, saved_name="", site_info=None):
    site_info = site_info or {}

    return {
        "ファイル名": filename,
        "判定": status,
        "理由": reason,
        "保存名": saved_name,
        "工事番号": site_info.get("construction_no", ""),
        "田番": site_info.get("field_no", ""),
        "撮影箇所": site_info.get("shoot_location", ""),
        "写真区分": photo_type,
        "工種": work,
        "種別": type_name,
        "細別": detail_name,
        "写真タイトル": title,
    }


def make_check_row(filename, reason, result, photo_type, work, type_name, detail_name, title, site_info=None):
    site_info = site_info or {}

    return {
        "ファイル名": filename,
        "確認理由": reason,
        "AI理由": safe_text(result.get("reason")),
        "写真内容": safe_text(result.get("scene_description")),
        "黒板文字": safe_text(result.get("blackboard_text")),
        "工事番号": site_info.get("construction_no", ""),
        "田番": site_info.get("field_no", ""),
        "撮影箇所": site_info.get("shoot_location", ""),
        "写真区分": photo_type,
        "工種": work,
        "種別": type_name,
        "細別": detail_name,
        "写真タイトル": title,
        "信頼度": result.get("confidence", ""),
    }


def make_candidate_row(filename, reason, result, photo_type, work, type_name, detail_name, title, site_info=None):
    site_info = site_info or {}

    return {
        "ファイル名": filename,
        "追加理由": reason,
        "工事番号": site_info.get("construction_no", ""),
        "田番": site_info.get("field_no", ""),
        "撮影箇所": site_info.get("shoot_location", ""),
        "写真区分": photo_type,
        "工種": work,
        "種別": type_name,
        "細別": detail_name,
        "写真タイトル": title,
        "信頼度": result.get("confidence", ""),
        "黒板文字": safe_text(result.get("blackboard_text")),
        "写真内容": safe_text(result.get("scene_description")),
    }


def write_csv(path, rows, empty_label):
    if rows:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    else:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerow([empty_label])

    log.info(f"CSV出力: {path} ({len(rows)}件)")


def write_tree_import_csv(result_rows):
    tree_rows = []
    seen = set()

    for r in result_rows:
        if r.get("判定") != "採用":
            continue

        row = {
            "写真区分": r.get("写真区分", ""),
            "工種": r.get("工種", ""),
            "種別": r.get("種別", ""),
            "細別": r.get("細別", ""),
            "写真タイトル": r.get("写真タイトル", ""),
        }

        key = (
            row["写真区分"],
            row["工種"],
            row["種別"],
            row["細別"],
            row["写真タイトル"],
        )

        if key in seen:
            continue

        seen.add(key)
        tree_rows.append(row)

    write_csv(TREE_IMPORT_CSV_PATH, tree_rows, "tree_importなし")


# =========================================================
# process
# =========================================================

def process_image(img_path):
    result_data = {
        "result_row": None,
        "check_row": None,
        "candidate_row": None,
        "xml_info": None,
    }

    log.info(f"処理中: {img_path.name}")

    if is_duplicate(str(img_path)):
        log.info("  重複 → EXCLUDE")

        safe_copy(str(img_path), os.path.join(EXCLUDE_FOLDER, img_path.name))

        result_data["result_row"] = make_result_row(
            img_path.name,
            "EXCLUDE",
            "重複",
            "",
            "",
            "",
            "",
            "",
        )

        return result_data

    result = analyze_image(str(img_path))

    usable = result.get("usable", False)
    unrelated = result.get("unrelated", False)

    blackboard_text = apply_synonym(safe_text(result.get("blackboard_text")))
    scene_description = safe_text(result.get("scene_description"))
    location = safe_text(result.get("location"))

    photo_type = safe_text(result.get("photo_type"))
    work = safe_text(result.get("work"))
    type_name = safe_text(result.get("type_name"))
    detail_name = safe_text(result.get("detail_name"))
    title = safe_text(result.get("title"))

    site_info = extract_site_numbers(location, blackboard_text)

    ai_construction_no = clean_construction_no(safe_text(result.get("construction_no")))
    ai_field_no = clean_field_no(safe_text(result.get("field_no")))

    if ai_construction_no and not site_info["construction_no"]:
        site_info["construction_no"] = ai_construction_no

    # AIの田番は「田番」と明記がある時だけ採用
    raw_for_field = zenkaku_to_hankaku(location + "\n" + blackboard_text)
    if ai_field_no and not site_info["field_no"] and ("田番" in raw_for_field or "田番号" in raw_for_field):
        site_info["field_no"] = ai_field_no

    parts = []

    if site_info["construction_no"]:
        parts.append(f"工事番号{site_info['construction_no']}")

    if site_info["field_no"]:
        parts.append(f"田番{site_info['field_no']}")

    site_info["shoot_location"] = " ".join(parts)

    photo_type, work, type_name, detail_name, title = apply_keyword_rules(
        photo_type,
        work,
        type_name,
        detail_name,
        title,
        blackboard_text,
        scene_description,
    )

    photo_type, work, type_name, detail_name, title = final_rule_fix(
        photo_type,
        work,
        type_name,
        detail_name,
        title,
        blackboard_text,
        scene_description,
    )

    work = fix_work_for_type(work, type_name, detail_name)

    if not title:
        title = make_title(work, type_name, detail_name, title)

    log.info(
        f"  黒板:{blackboard_text[:40]} "
        f"工事番号:{site_info.get('construction_no')} "
        f"田番:{site_info.get('field_no')} "
        f"区分:{photo_type} "
        f"工種:{work} "
        f"種別:{type_name} "
        f"細別:{detail_name}"
    )

    if not blackboard_text.strip():
        log.info("  黒板なし → CHECK")

        safe_copy(str(img_path), os.path.join(CHECK_FOLDER, img_path.name))

        result_data["check_row"] = make_check_row(
            img_path.name,
            "黒板なし",
            result,
            photo_type,
            work,
            type_name,
            detail_name,
            title,
            site_info,
        )

        result_data["result_row"] = make_result_row(
            img_path.name,
            "CHECK",
            "黒板なし",
            photo_type,
            work,
            type_name,
            detail_name,
            title,
            site_info=site_info,
        )

        return result_data

    if is_indoor_office(result):
        log.info("  室内写真 → CHECK")

        safe_copy(str(img_path), os.path.join(CHECK_FOLDER, img_path.name))

        result_data["check_row"] = make_check_row(
            img_path.name,
            "室内・事務所写真",
            result,
            photo_type,
            work,
            type_name,
            detail_name,
            title,
            site_info,
        )

        result_data["result_row"] = make_result_row(
            img_path.name,
            "CHECK",
            "室内・事務所写真",
            photo_type,
            work,
            type_name,
            detail_name,
            title,
            site_info=site_info,
        )

        return result_data

    if unrelated:
        log.info("  無関係 → EXCLUDE")

        safe_copy(str(img_path), os.path.join(EXCLUDE_FOLDER, img_path.name))

        result_data["result_row"] = make_result_row(
            img_path.name,
            "EXCLUDE",
            "別現場または無関係",
            photo_type,
            work,
            type_name,
            detail_name,
            title,
            site_info=site_info,
        )

        return result_data

    if not usable:
        log.info("  usable=false → CHECK")

        safe_copy(str(img_path), os.path.join(CHECK_FOLDER, img_path.name))

        result_data["check_row"] = make_check_row(
            img_path.name,
            "usable false",
            result,
            photo_type,
            work,
            type_name,
            detail_name,
            title,
            site_info,
        )

        result_data["result_row"] = make_result_row(
            img_path.name,
            "CHECK",
            "usable false",
            photo_type,
            work,
            type_name,
            detail_name,
            title,
            site_info=site_info,
        )

        return result_data

    # CHECK条件を少し緩める
    # 写真区分・工種・種別があれば採用
    # 細別だけ空なら「その他」で埋める
    if not photo_type or not work or not type_name:
        log.info("  分類不足 → CHECK")

        safe_copy(str(img_path), os.path.join(CHECK_FOLDER, img_path.name))

        result_data["check_row"] = make_check_row(
            img_path.name,
            "分類不足",
            result,
            photo_type,
            work,
            type_name,
            detail_name,
            title,
            site_info,
        )

        result_data["result_row"] = make_result_row(
            img_path.name,
            "CHECK",
            "分類不足",
            photo_type,
            work,
            type_name,
            detail_name,
            title,
            site_info=site_info,
        )

        result_data["candidate_row"] = make_candidate_row(
            img_path.name,
            "分類不足",
            result,
            photo_type,
            work,
            type_name,
            detail_name,
            title,
            site_info,
        )

        return result_data

    if not detail_name:
        detail_name = "その他"

    if not title:
        title = make_title(work, type_name, detail_name, "")

    new_name = next_serial_name()

    if not safe_copy(str(img_path), os.path.join(PIC_FOLDER, new_name)):
        log.info("  コピー失敗 → CHECK")

        safe_copy(str(img_path), os.path.join(CHECK_FOLDER, img_path.name))

        result_data["check_row"] = make_check_row(
            img_path.name,
            "コピー失敗",
            result,
            photo_type,
            work,
            type_name,
            detail_name,
            title,
            site_info,
        )

        result_data["result_row"] = make_result_row(
            img_path.name,
            "CHECK",
            "コピー失敗",
            photo_type,
            work,
            type_name,
            detail_name,
            title,
            site_info=site_info,
        )

        return result_data

    log.info(f"  採用 → {new_name}")

    result_data["result_row"] = make_result_row(
        img_path.name,
        "採用",
        "OK",
        photo_type,
        work,
        type_name,
        detail_name,
        title,
        saved_name=new_name,
        site_info=site_info,
    )

    result_data["xml_info"] = {
        "new_name": new_name,
        "photo_type": photo_type,
        "work": work,
        "type_name": type_name,
        "detail_name": detail_name,
        "title": title,
        "location": site_info.get("shoot_location", ""),
    }

    return result_data


# =========================================================
# main
# =========================================================

def main():
    image_files_dict = {}

    for ext in ["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"]:
        for p in Path(INPUT_FOLDER).rglob(ext):
            image_files_dict[str(p.resolve()).lower()] = p

    image_files = sorted(image_files_dict.values(), key=lambda x: str(x).lower())

    log.info("=" * 50)
    log.info(f"工事写真解析開始 - 対象枚数: {len(image_files)}")
    log.info("=" * 50)

    check_rows = []
    result_rows = []
    candidate_rows = []
    xml_infos = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_image, p): p for p in image_files}

        for future in as_completed(futures):
            img_path = futures[future]

            try:
                data = future.result()

            except Exception as e:
                log.error(f"予期しないエラー ({img_path.name}): {e}")

                result_rows.append(
                    make_result_row(
                        img_path.name,
                        "ERROR",
                        str(e),
                        "",
                        "",
                        "",
                        "",
                        "",
                    )
                )

                continue

            if not data:
                continue

            if data["check_row"]:
                check_rows.append(data["check_row"])

            if data["result_row"]:
                result_rows.append(data["result_row"])

            if data["candidate_row"]:
                candidate_rows.append(data["candidate_row"])

            if data["xml_info"]:
                xml_infos.append(data["xml_info"])

    write_csv(CHECK_CSV_PATH, check_rows, "CHECKなし")
    write_csv(RESULT_CSV_PATH, result_rows, "結果なし")
    write_csv(ADD_CANDIDATE_CSV_PATH, candidate_rows, "追加候補なし")
    write_tree_import_csv(result_rows)

    if not xml_infos:
        log.info("採用写真なし → PHOTO.XML 生成スキップ")

    else:
        root = Element("photodata")
        root.set("DTD_version", "05")

        base_info = SubElement(root, "基礎情報")
        SubElement(base_info, "写真フォルダ名").text = "PHOTO/PIC"
        SubElement(base_info, "参考図フォルダ名").text = "PHOTO/DRA"
        SubElement(base_info, "適用要領基準").text = "土木202303-01"

        xml_infos.sort(key=lambda x: x["new_name"])

        for i, info in enumerate(xml_infos, start=1):
            photo_info = SubElement(root, "写真情報")

            file_info = SubElement(photo_info, "写真ファイル情報")
            SubElement(file_info, "シリアル番号").text = str(i)
            SubElement(file_info, "写真ファイル名").text = info["new_name"]
            SubElement(file_info, "メディア番号").text = "1"

            category = SubElement(photo_info, "撮影工種区分")
            SubElement(category, "写真-大分類").text = "工事"
            SubElement(category, "写真区分").text = info["photo_type"]
            SubElement(category, "工種").text = info["work"]
            SubElement(category, "種別").text = info["type_name"]
            SubElement(category, "細別").text = info["detail_name"]
            SubElement(category, "写真タイトル").text = info["title"]

            shoot = SubElement(photo_info, "撮影情報")
            SubElement(shoot, "撮影年月日").text = datetime.now().strftime("%Y-%m-%d")
            SubElement(shoot, "撮影箇所").text = info["location"]

            SubElement(photo_info, "代表写真").text = "0"
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
    log.info(
        f"完了 - 採用:{len(xml_infos)} CHECK:{len(check_rows)} 候補:{len(candidate_rows)}"
    )
    log.info("=" * 50)


if __name__ == "__main__":
    main()