# Setup on GitHub Codespaces

## ขั้นตอน

### 1. Push code ขึ้น GitHub
```bash
cd "D:\Nextcloud\Project\Phiautomation\Local LLM tester"
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/bom-generator.git
git push -u origin main
```

> หมายเหตุ: `.gitignore` กรอง `secrets.toml`, `chroma_db/`, `part_index.json` ออกแล้ว — ไม่หลุด

### 2. สร้าง Codespace
1. เข้า GitHub repo ที่เพิ่ง push
2. กด **Code** → **Codespaces** → **Create codespace on main**
3. รอ ~2 นาที (Codespaces จะ install requirements อัตโนมัติ)

### 3. ตั้งค่า API Key (Codespaces Secret)
1. ไปที่ **github.com/settings/codespaces**
2. New secret → ชื่อ `ANTHROPIC_API_KEY` → ใส่ key
3. เลือก repo ที่ใช้ → Save

### 4. รันแอปใน Codespace
ใน terminal ของ Codespace:
```bash
mkdir -p .streamlit
echo "ANTHROPIC_API_KEY = \"$ANTHROPIC_API_KEY\"" > .streamlit/secrets.toml
streamlit run app.py
```

Codespaces จะ forward port 8501 อัตโนมัติ — กด **Open in Browser** ที่ pop-up

### 5. แชร์ URL ให้ทีม (ชั่วคราว)
- Tab **PORTS** ใน Codespace → คลิกขวาที่ port 8501 → **Port Visibility** → **Public**
- คัดลอก URL → ส่งให้ทีม
- ⚠️ URL ใช้ได้เฉพาะตอน Codespace เปิดอยู่
