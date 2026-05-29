# 杏子 - 建設写真AI整理システム

## なぜ作ったか

建設現場の写真整理や出来形管理は多くの作業が手作業で行われています。

入社後すぐに業務上の課題を発見し、約3週間で写真分類・OCR・CSV生成を効率化するツールを独学で開発しました。

現場業務の負担軽減と作業時間短縮を目的として改善を継続しています。

---

## 概要

建設現場写真をAIで分類し、電子納品用PHOTO.XMLおよびデキスパート連携CSVを自動生成する業務支援ツールです。

黒板OCR・画像解析・現場別マスタを組み合わせ、採用写真・CHECK写真・除外写真へ自動分類します。

さらに出来形管理写真から実測値OCRを実施し、田番別CSVを自動生成します。

---

## 主な機能

* 工事写真AI分類
* PHOTO.XML自動生成
* tree_import.csv生成
* CHECK写真分離
* 重複写真除外
* ブレ写真判定
* GPT OCR
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

## システム構成

### 統合GUI

* 写真分類実行
* PHOTO.XML生成
* 出来形OCR起動

### 写真分類エンジン

* 黒板OCR
* 工種判定
* 種別判定
* 細別判定
* CHECK判定
* 重複判定
* ブレ判定

### 出来形OCR

* GPT OCR
* 測定値抽出
* 田番判定
* CSV出力

---

## 使用技術

* Python 3
* OpenAI API
* Tkinter
* Pillow
* OpenCV
* imagehash
* CSV
* XML
* Git
* GitHub

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

---

## 最新GUI

### 統合GUI

ファイル

```text
杏子/app/integrated_gui.py
```

機能

* 写真分類
* PHOTO.XML生成
* 出来形OCR起動

### 写真分類エンジン

```text
杏子/app/photo_core.py
```

### 出来形OCR GUI

```text
杏子/app/ssk_ocr_gui.py
```

---

## 今後の改善予定

* 写真分類精度向上
* 工種マスタ拡張
* OCR精度向上
* GUI改善
* GitHubドキュメント整備

---

## 開発環境

* Windows
* Python 3.x
* VS Code
* GitHub

```
```









