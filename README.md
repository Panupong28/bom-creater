---
title: BOM Generator OMRON Catalog
emoji: 🏭
colorFrom: blue
colorTo: green
sdk: streamlit
sdk_version: 1.57.0
app_file: app.py
pinned: false
---

# BOM Generator + OMRON Catalog

ระบบช่วยสร้าง Bill of Materials (BOM) สำหรับงานตู้ควบคุม OMRON PLC โดยใช้ Claude AI วิเคราะห์ catalog จริง

## ความสามารถ
- อัปโหลด PDF catalog OMRON → LLM อ่านและสกัด Part No. แบบ structured
- ค้นหา Part No. ใน catalog ด้วย semantic search
- สร้าง BOM อัตโนมัติจากข้อกำหนดผู้ใช้
- ทีมสอน LLM ผ่าน rules และ examples ได้

## การใช้งาน
1. ตั้งค่า `ANTHROPIC_API_KEY` ใน Settings → Secrets
2. อัปโหลด PDF catalog ที่ tab "Catalog OMRON"
3. สร้าง BOM ที่ tab "สร้าง BOM"
