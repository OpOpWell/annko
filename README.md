# 杏子 - 建設写真AI整理システム

## 概要

建設現場写真をAIで分類し、電子納品用PHOTO.XMLおよびデキスパート連携CSVを自動生成する業務支援ツールです。

黒板OCR・写真内容解析・現場別マスタを組み合わせ、採用写真・CHECK写真・除外写真へ自動分類します。

さらに出来形管理写真から実測値OCRを実施し、田番別CSVを自動生成します。

---

## 主な機能

* 工事写真AI分類
* PHOTO.XML自動生成
* tree_import.csv生成
* CHECK写真分離
* 重複写真除外
* ブレ写真判定
* GPT-4.1 OCR
* 実測値OCR
* 田番別CSV生成
* デキスパート連携CSV生成
* GUI操作対応

---

## 実行実績

### 写真分類

* 採用写真 21枚
* CHECK写真 2枚
* PHOTO.XML生成

### 出来形OCR

* GPT OCR実施
* 田番別CSV自動生成
* デキスパート取込対応

---

## 使用技術

* Python
* OpenAI API
* Tkinter
* OCR
* CSV
* XML
* GitHub

---

## 最新GUI

### 統合GUI

* 写真分類
* PHOTO.XML生成
* 出来形OCR起動

ファイル:

```text
杏子/app/integrated_gui.py
```

### 写真分類エンジン

```text
杏子/app/photo_core.py
```

### 出来形OCR GUI

```text
杏子/app/ssk_ocr_gui.py
```

---

## フォルダ構成

```text
杏子/
├─ app/
│  ├─ integrated_gui.py
│  ├─ photo_core.py
│  ├─ photo_core_old.py
│  └─ ssk_ocr_gui.py
│
├─ master/
├─ backup_before整理/
├─ logs/
└─ output/
```



