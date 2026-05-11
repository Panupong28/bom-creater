# BOM Generator — คู่มือใช้งานแบบ Local

## รัน 2 วินาที — ทำครั้งเดียว
ดับเบิลคลิก **`setup_local.bat`** (ติดตั้ง package ที่จำเป็น)

## เปิดแอป — ทุกครั้งที่ใช้
ดับเบิลคลิก **`run_local.bat`**

แอปจะเปิดที่ **http://localhost:8501** อัตโนมัติ
หยุดด้วย Ctrl+C ใน terminal

---

## โครงสร้างไฟล์

```
Local LLM tester/
├── app.py                   ← แอปหลัก
├── requirements.txt         ← Python packages
├── run_local.bat            ← ⭐ ดับเบิลคลิกเปิดแอป
├── setup_local.bat          ← ติดตั้งครั้งแรก
├── Dockerfile               ← สำหรับ HF Space
├── .streamlit/
│   ├── config.toml          ← ปิด telemetry
│   └── secrets.toml         ← Gemini API Key (ไม่ขึ้น git)
├── .devcontainer/
│   └── devcontainer.json    ← สำหรับ GitHub Codespaces
└── chroma_db/, *.json       ← ฐานข้อมูล (ไม่ขึ้น git)
```

## ฐานข้อมูล Local
- `part_index.json` — Part No. แบบ structured
- `knowledge_base.json` — กฎที่สอน LLM
- `token_usage.json` — สถิติ token
- `chroma_db/` — vector database

## Deploy ไป HF Space
```bash
git add .
git commit -m "ข้อความ"
git push hf main      # → HF Space
git push origin main  # → GitHub
```

HF Space rebuild อัตโนมัติ ~3 นาที
