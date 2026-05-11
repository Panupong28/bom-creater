# Prompt Templates — สำหรับ Extract Catalog เป็น JSON

ใช้กับ Gemini, ChatGPT, Claude, NotebookLM ฯลฯ
รองรับ catalog ทุกยี่ห้อและทุกประเภทอุปกรณ์

---

## 🎯 Prompt หลัก — Universal (ใช้ได้กับทุก catalog)

Copy ไปวางในแชท AI พร้อมแนบ PDF:

```
อ่าน PDF catalog ที่แนบมานี้ทั้งเล่ม แล้วสกัด Part Number / Model Number
ทุกตัวที่พบ ใช้ได้กับ catalog ทุกยี่ห้อ ทุกประเภทอุปกรณ์

กฎเข้มงวด:
1. สกัดทุก Part No. ที่ปรากฏในเอกสาร ห้ามตกหล่นแม้แต่ตัวเดียว
2. รวมทั้ง main part, option, accessory, spare parts, cable, connector
3. ถ้ามีตาราง Part No. หลายแถว ต้องคัดทุกแถว
4. บอกจำนวนรวมที่พบก่อนเริ่มลิสต์
5. ใช้ Part No. ที่ปรากฏจริงในเอกสาร ห้ามแต่งเอง

สำหรับแต่ละ Part No. ระบุ 6 fields:

- brand: ยี่ห้อ (เช่น "OMRON", "Mitsubishi", "Siemens", "Schneider",
  "ABB", "Allen-Bradley", "Panasonic", "Keyence", "SMC", "Festo")

- category: หมวดอุปกรณ์ เลือกจากนี้:
  PLC: "CPU Unit" / "Power Supply" / "Digital Input" / "Digital Output"
       / "Analog Input" / "Analog Output" / "Mixed I/O" / "Pulse I/O"
       / "Communication" / "Memory Card" / "Option Board"
  HMI: "HMI Touchscreen" / "Operator Panel"
  Drive: "VFD / Inverter" / "Servo Drive" / "Servo Motor" / "Stepper"
  Motor: "AC Motor" / "DC Motor" / "Gear Motor"
  Sensor: "Proximity Sensor" / "Photoelectric Sensor" / "Pressure Sensor"
          / "Temperature Sensor" / "Flow Sensor" / "Vision Sensor"
          / "Encoder" / "Load Cell"
  Safety: "Safety Relay" / "Light Curtain" / "Safety Switch"
          / "Emergency Stop" / "Safety Controller"
  Switch: "Limit Switch" / "Push Button" / "Selector Switch"
          / "Pilot Lamp" / "Cam Switch"
  Pneumatic: "Solenoid Valve" / "Cylinder" / "Air Prep Unit"
             / "Fitting" / "Tubing"
  Power: "Power Supply Unit (PSU)" / "UPS" / "Transformer"
         / "Battery Backup"
  Protection: "MCB" / "MCCB" / "RCBO" / "Surge Protector"
              / "Fuse" / "Contactor" / "Thermal Overload"
  Cable: "Cable" / "Connector" / "Terminal Block" / "Cable Gland"
  Network: "Switch" / "Router" / "Gateway" / "Converter"
  อื่นๆ: "Accessory" / "Spare Part" / "Software"
  ถ้าไม่ตรงหมวดไหน → ใส่หมวดที่เหมาะสม

- description: คำอธิบายสั้น 1 ประโยค (ภาษาไทยหรืออังกฤษ)

- key_specs: spec สำคัญ รวมในบรรทัดเดียว (เช่น "64 points, 24VDC, FCN")
  ใส่เฉพาะที่จำเป็นต่อการเลือก: rating, port count, voltage, current

- use_when: เมื่อไหร่ควรเลือกใช้ตัวนี้ (1 ประโยคสั้น ภาษาไทย)

- source: ชื่อไฟล์ PDF

ตอบเป็น JSON เท่านั้น ไม่ต้องมีคำอธิบาย ไม่ต้องมี markdown code block:

{
  "PART-NO-1": {
    "brand": "...",
    "category": "...",
    "description": "...",
    "key_specs": "...",
    "use_when": "...",
    "source": "ชื่อไฟล์.pdf"
  },
  "PART-NO-2": {...}
}
```

---

## 🎯 Prompt สำหรับ PDF ใหญ่ — แบ่งทำเป็นรอบๆ

ใช้เมื่อ PDF > 50 หน้า แต่ละรอบเปลี่ยน `[CATEGORY]`:

```
อ่าน PDF catalog ที่แนบมา ลิสต์ Part No. เฉพาะหมวด [CATEGORY] ทุกตัว

กฎ:
- เฉพาะหมวด [CATEGORY] เท่านั้น ห้ามตกหล่น
- บอกจำนวนที่พบก่อนเริ่มลิสต์
- ใช้ Part No. ที่ปรากฏจริงในเอกสาร

format JSON:
{
  "PART-NO": {
    "brand": "ยี่ห้อ",
    "category": "[CATEGORY]",
    "description": "...",
    "key_specs": "...",
    "use_when": "...",
    "source": "ชื่อไฟล์.pdf"
  }
}
```

ทำทีละหมวด แล้ว **Merge** ใน app ทุกครั้ง

---

## 🎯 Prompt ต่อยอด (ถ้า AI ตอบไม่ครบ)

```
ขอเพิ่มเติม Part No. ที่เหลือใน PDF ที่ยังไม่ได้ลิสต์ในรอบก่อน
ลิสต์เฉพาะตัวที่ยังไม่มี ใช้ format JSON เดียวกัน
ถ้าครบทุกตัวแล้ว ตอบ "ครบแล้ว"
```

---

## 🎯 Prompt สำหรับ catalog ที่ไม่ใช่ industrial automation

ใช้กับ catalog ทั่วไป — electronics, hardware, อุปกรณ์ใดๆ ที่มี Part No.:

```
อ่าน PDF catalog ที่แนบ สกัด Part Number / SKU / Model Number ทุกตัว

สำหรับแต่ละตัว ระบุ:
- brand: ยี่ห้อ
- category: หมวดสินค้า (กำหนดเองให้เหมาะสม)
- subcategory: หมวดย่อย (ถ้ามี)
- description: คำอธิบายสั้น
- key_specs: spec สำคัญต่อการเลือก
- use_when: เมื่อไหร่ควรเลือกใช้
- price_range: ช่วงราคา (ถ้ามี)
- source: ชื่อไฟล์ PDF

ตอบเป็น JSON เท่านั้น:
{
  "PART-NO": {
    "brand": "...",
    "category": "...",
    "subcategory": "...",
    "description": "...",
    "key_specs": "...",
    "use_when": "...",
    "price_range": "...",
    "source": "..."
  }
}
```

---

## 💡 Tips ใช้งาน

| สถานการณ์ | ทำยังไง |
|---|---|
| PDF > 100 หน้า | ใช้ **NotebookLM** (notebooklm.google.com) แทน chat ปกติ |
| AI สรุปแทนลิสต์ | เพิ่ม "ห้ามสรุป ห้ามตัดทอน ต้องลิสต์ทุกตัว" |
| ภาษาไทยพิมพ์ผิด | เปลี่ยนเป็น "ใช้ภาษาอังกฤษทั้งหมด" |
| AI ใส่ markdown ```json``` | app จะตัดให้อัตโนมัติ ไม่ต้องห่วง |
| Catalog หลายไฟล์ | ทำทีละไฟล์ แล้ว **Merge** ทุกรอบ |
| ภาษา catalog ญี่ปุ่น/เยอรมัน | บอก AI ให้แปลเป็นไทย/อังกฤษก่อนตอบ |

---

## 🔄 Workflow แนะนำ

```
1. ดาวน์โหลด catalog PDF
   ↓
2. เปิด gemini.google.com หรือ notebooklm.google.com
   ↓
3. Upload PDF + paste prompt ด้านบน
   ↓
4. ได้ JSON → copy
   ↓
5. ไปที่ app tab "Catalog OMRON" → Import JSON (paste/upload)
   ↓
6. เลือก "Merge" ถ้ามีของเดิม / "Replace" ถ้าจะแทนที่
   ↓
7. ไปสร้าง BOM ที่ tab "สร้าง BOM"
```

---

## 📌 ตัวอย่าง Output ที่ถูกต้อง

```json
{
  "FX5U-32MT/ES": {
    "brand": "Mitsubishi",
    "category": "CPU Unit",
    "description": "MELSEC iQ-F Series CPU พร้อม Transistor Output 16 จุด",
    "key_specs": "32 I/O, AC100-240V, Transistor sink output, Built-in Ethernet",
    "use_when": "ระบบอัตโนมัติขนาดเล็ก-กลาง ต้องการ Ethernet ในตัว",
    "source": "fx5u_catalog.pdf"
  },
  "6ES7212-1AE40-0XB0": {
    "brand": "Siemens",
    "category": "CPU Unit",
    "description": "SIMATIC S7-1200 CPU 1212C DC/DC/DC",
    "key_specs": "8 DI / 6 DO / 2 AI, 24VDC, 75KB program memory",
    "use_when": "ระบบขนาดเล็ก ใช้ไฟ DC, ต้องการ Profinet",
    "source": "s7-1200_manual.pdf"
  }
}
```
