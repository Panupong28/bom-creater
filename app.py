import streamlit as st
import json
import os
import re
import time
import hashlib
import pdfplumber
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from google import genai
from google.genai import types as genai_types

KNOWLEDGE_FILE = "knowledge_base.json"
PART_INDEX_FILE = "part_index.json"
TOKEN_USAGE_FILE = "token_usage.json"
CHROMA_DIR = "chroma_db"
OMRON_PN = re.compile(r'\b([A-Z]{1,4}\d*[A-Z]*-[A-Z0-9\-]{2,15})\b')

# ── Token tracking ───────────────────────────────────────────────────────────

def load_token_usage() -> dict:
    if os.path.exists(TOKEN_USAGE_FILE):
        with open(TOKEN_USAGE_FILE, "r") as f:
            return json.load(f)
    return {"total_input": 0, "total_output": 0, "total_calls": 0, "by_function": {}}

def save_token_usage(usage: dict):
    with open(TOKEN_USAGE_FILE, "w") as f:
        json.dump(usage, f, indent=2)

def track_tokens(response, function_name: str):
    """อ่าน usage_metadata จาก response แล้ว save"""
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return
    # google-genai SDK ใช้ field ชื่อ prompt_token_count / candidates_token_count
    in_tok = getattr(meta, "prompt_token_count", 0) or 0
    out_tok = getattr(meta, "candidates_token_count", 0) or 0
    # fallback: ใช้ total_token_count ถ้า candidates_token_count = 0
    if out_tok == 0:
        total = getattr(meta, "total_token_count", 0) or 0
        if total > in_tok:
            out_tok = total - in_tok
    if in_tok == 0 and out_tok == 0:
        return

    usage = load_token_usage()
    usage["total_input"] += in_tok
    usage["total_output"] += out_tok
    usage["total_calls"] += 1
    fn = usage["by_function"].setdefault(function_name, {"input": 0, "output": 0, "calls": 0})
    fn["input"] += in_tok
    fn["output"] += out_tok
    fn["calls"] += 1
    save_token_usage(usage)
    # session counter
    if "session_tokens" not in st.session_state:
        st.session_state.session_tokens = {"input": 0, "output": 0, "calls": 0}
    st.session_state.session_tokens["input"] += in_tok
    st.session_state.session_tokens["output"] += out_tok
    st.session_state.session_tokens["calls"] += 1

# ── Helpers ──────────────────────────────────────────────────────────────────

def load_knowledge():
    if os.path.exists(KNOWLEDGE_FILE):
        with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"rules": [], "examples": []}

def save_knowledge(kb):
    with open(KNOWLEDGE_FILE, "w", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)

def load_part_index() -> dict:
    if os.path.exists(PART_INDEX_FILE):
        with open(PART_INDEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_part_index(index: dict):
    with open(PART_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

def extract_parts_from_text(text: str, source: str) -> dict:
    """สกัด Part No. + บริบทรอบข้าง (regex-only, ไม่ใช้ LLM)"""
    parts = {}
    for m in OMRON_PN.finditer(text):
        pn = m.group(1)
        start = max(0, m.start() - 150)
        end = min(len(text), m.end() + 150)
        context = text[start:end].replace("\n", " ").strip()
        if pn not in parts:
            parts[pn] = {"source": source, "context": context}
    return parts

@st.cache_resource
def get_gemini_client():
    # รองรับทั้ง Streamlit secrets และ environment variable (HF Spaces)
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        try:
            api_key = st.secrets["GEMINI_API_KEY"]
        except Exception:
            st.error("⚠️ ไม่พบ GEMINI_API_KEY กรุณาตั้งค่าใน Settings → Variables and secrets")
            st.stop()
    return genai.Client(api_key=api_key)

GEMINI_MODEL = "gemini-2.5-flash"

def llm_extract_structured(chunk: str) -> dict:
    """ใช้ Gemini อ่าน chunk แล้วสกัดเป็น structured JSON"""
    client = get_gemini_client()
    system = """คุณเป็น engineer วิเคราะห์ catalog OMRON สกัด Part No. ที่ปรากฏในข้อความ พร้อมข้อมูล:
- category: หมวด (เช่น "CPU Unit", "Power Supply", "Digital Input", "Digital Output", "Analog I/O", "Communication", "Cable", "Terminal Block", "Connector")
- description: คำอธิบายสั้นๆ
- key_specs: spec สำคัญ (เช่น "64 points, 24VDC, FCN connector")
- use_when: เมื่อไหร่ควรใช้ (1 ประโยคสั้นๆ ภาษาไทยหรืออังกฤษก็ได้)

ตอบเป็น JSON เท่านั้น ไม่ต้องมีคำอธิบาย format:
{"PART-NO-1": {"category":"...","description":"...","key_specs":"...","use_when":"..."}}

ถ้าไม่มี Part No. ใน text ให้ตอบ {}"""
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=chunk[:2000],
        config=genai_types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.0,
            response_mime_type="application/json",
        ),
    )
    track_tokens(response, "extract_pdf")
    try:
        text = response.text.strip()
        m = re.search(r'\{.*\}', text, re.DOTALL)
        return json.loads(m.group()) if m else {}
    except Exception:
        return {}

@st.cache_resource
def get_chroma_collection():
    ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    return client.get_or_create_collection("omron_catalog", embedding_function=ef)

def extract_pdf_text(pdf_file) -> str:
    with pdfplumber.open(pdf_file) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)

def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return [c.strip() for c in chunks if len(c.strip()) > 50]

def add_pdf_to_db(collection, pdf_name: str, text: str, use_llm_extract: bool = True, progress_callback=None):
    chunks = chunk_text(text)
    ids, docs, metas = [], [], []
    for i, chunk in enumerate(chunks):
        uid = hashlib.md5(f"{pdf_name}_{i}".encode()).hexdigest()
        ids.append(uid)
        docs.append(chunk)
        metas.append({"source": pdf_name, "chunk": i})
    collection.upsert(ids=ids, documents=docs, metadatas=metas)

    # อัปเดต Part No. index
    index = load_part_index()

    if use_llm_extract:
        # หา chunk ที่มี Part No. เท่านั้น
        chunks_with_pn = [c for c in chunks if OMRON_PN.search(c)]
        total = len(chunks_with_pn)
        for i, chunk in enumerate(chunks_with_pn):
            if progress_callback:
                progress_callback(i, total, f"กำลังให้ LLM อ่าน chunk {i+1}/{total}")
            try:
                extracted = llm_extract_structured(chunk)
                for pn, info in extracted.items():
                    info["source"] = pdf_name
                    if pn not in index or "category" not in index.get(pn, {}):
                        index[pn] = info
                save_part_index(index)  # save บ่อยๆ กันงานหาย
            except Exception as e:
                # rate limit → รอ 30 วินาที แล้วข้าม
                if "rate_limit" in str(e).lower() or "429" in str(e):
                    time.sleep(30)
                    continue
            time.sleep(0.5)  # delay เล็กน้อยกัน burst
    else:
        new_parts = extract_parts_from_text(text, pdf_name)
        index.update(new_parts)
        save_part_index(index)

    return len(chunks), len([k for k in index if index[k].get("source") == pdf_name])

def search_catalog(collection, query: str, n: int = 5) -> list[str]:
    results = collection.query(query_texts=[query], n_results=min(n, collection.count()))
    return results["documents"][0] if results["documents"] else []

def ask_llm(system_prompt: str, user_input: str, fn_name: str = "ask_llm") -> str:
    client = get_gemini_client()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=user_input,
        config=genai_types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.1,
        ),
    )
    track_tokens(response, fn_name)
    return response.text

def get_component_queries(user_input: str) -> list[str]:
    """ให้ LLM แยก component แล้วสร้าง search query ทีละตัว"""
    client = get_gemini_client()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=user_input,
        config=genai_types.GenerateContentConfig(
            system_instruction="""แยก component ที่ต้องการจาก input แล้วสร้าง search query ภาษาอังกฤษสำหรับค้นหาใน OMRON catalog
ตอบเป็น JSON array ของ string เท่านั้น ไม่ต้องมีคำอธิบาย
ตัวอย่าง: ["CJ2M CPU unit", "power supply CJ1W", "digital input module 64 point FCN connector", "digital output module 64 point FCN connector"]""",
            temperature=0.0,
            response_mime_type="application/json",
        ),
    )
    track_tokens(response, "component_query")
    text = response.text.strip()
    match = re.search(r'\[.*?\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return [user_input]

def multi_search_catalog(collection, user_input: str) -> str:
    """ค้นหาแยกทีละ component แล้วรวมผลลัพธ์"""
    queries = get_component_queries(user_input)
    seen, all_chunks = set(), []
    for q in queries:
        for chunk in search_catalog(collection, q, n=4):
            if chunk not in seen:
                seen.add(chunk)
                all_chunks.append(f"[Query: {q}]\n{chunk}")
    return "\n\n---\n\n".join(all_chunks)

# ── BOM helpers ──────────────────────────────────────────────────────────────

def find_relevant_parts(collection, part_index: dict, queries: list[str], max_items: int = 60) -> dict:
    """ใช้ semantic search หา chunks ที่เกี่ยวข้อง แล้วสกัด Part No. จาก chunks เหล่านั้น"""
    if not part_index or collection.count() == 0:
        return {}
    relevant_pns = set()
    for q in queries:
        chunks = search_catalog(collection, q, n=6)
        for chunk in chunks:
            for m in OMRON_PN.finditer(chunk):
                relevant_pns.add(m.group(1))
    # คืนเฉพาะ Part No. ที่อยู่ใน index
    result = {pn: part_index[pn] for pn in relevant_pns if pn in part_index}
    if len(result) > max_items:
        result = dict(list(result.items())[:max_items])
    return result

def build_bom_prompt(kb, part_index: dict, queries: list[str] = None, collection=None) -> str:
    rules = "\n".join(f"- {r}" for r in kb["rules"]) or "ยังไม่มีกฎ"
    examples = ""
    for ex in kb["examples"]:
        examples += f"\nInput: {ex['input']}\nOutput: {ex['output']}\n---"

    if part_index:
        # ถ้ามี structured info ใช้แบบ structured ถ้าไม่มีใช้ fallback
        has_structured = any("category" in v for v in part_index.values())

        if has_structured:
            # group by category
            by_cat = {}
            for pn, info in part_index.items():
                cat = info.get("category", "Uncategorized")
                by_cat.setdefault(cat, []).append((pn, info))

            sections = []
            for cat, items in sorted(by_cat.items()):
                lines = [f"### {cat}"]
                for pn, info in sorted(items):
                    brand = info.get("brand", "")
                    desc = info.get("description", "")
                    specs = info.get("key_specs", "")
                    use = info.get("use_when", "")
                    brand_prefix = f"[{brand}] " if brand else ""
                    lines.append(f"- **{pn}** | {brand_prefix}{desc} | spec: {specs} | ใช้เมื่อ: {use}")
                sections.append("\n".join(lines))
            parts_list = "\n\n".join(sections)
        else:
            parts_list = ", ".join(sorted(part_index.keys()))

        catalog_section = f"""
รายการ Part No. จาก Catalog (เลือกจากรายการนี้เท่านั้น):
{parts_list}

กฎเข้มงวด:
- ใช้เฉพาะ Part No. ที่ตรงกับรายการด้านบนเท่านั้น (เทียบตัวอักษรทุกตัว)
- เลือกตาม category และ use case ที่ระบุไว้
- ห้ามแต่งหรือคาดเดา Part No. โดยเด็ดขาด
- ถ้าไม่มีรหัสที่เหมาะสมให้ใส่ "ไม่พบใน Catalog" แทน"""
    else:
        catalog_section = "\nไม่มีข้อมูล Catalog — ห้ามระบุ Part No. ใดๆ ให้ใส่ '-' แทนทุกครั้ง"

    return f"""คุณเป็นผู้ช่วยสร้าง BOM (Bill of Materials) สำหรับฝ่ายผลิต OMRON PLC

กฎที่ต้องปฏิบัติตามเสมอ:
{rules}

ตัวอย่างที่ถูกต้อง:
{examples if examples else "ยังไม่มีตัวอย่าง"}
{catalog_section}

สร้าง BOM เป็นตารางที่ชัดเจน มี: ลำดับ, รายการ, Part No., จำนวน, หน่วย, หมายเหตุ"""

# ── UI ───────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="BOM + OMRON Catalog", layout="wide")
st.title("BOM Generator + OMRON Catalog")

kb = load_knowledge()
collection = get_chroma_collection()

tab_bom, tab_catalog, tab_db, tab_teach = st.tabs(["สร้าง BOM", "Catalog OMRON", "ดูฐานข้อมูล", "สอน LLM"])

# ── Tab 1: BOM ────────────────────────────────────────────────────────────────
with tab_bom:
    st.subheader("ระบุข้อมูลเพื่อสร้าง BOM")

    use_catalog = False
    if collection.count() > 0:
        use_catalog = st.toggle("ใช้ข้อมูลจาก OMRON Catalog ประกอบด้วย", value=True)

    user_input = st.text_area(
        "อธิบายสิ่งที่ต้องการผลิตหรืออุปกรณ์ที่ต้องการ",
        placeholder="เช่น: ต้องการ PLC สำหรับควบคุม conveyor belt มี I/O 16 จุด รองรับ Ethernet",
        height=140,
    )

    if st.button("สร้าง BOM", type="primary", use_container_width=True):
        if user_input.strip():
            part_index = load_part_index() if use_catalog else {}
            queries = []
            if part_index:
                with st.spinner("วิเคราะห์ component..."):
                    queries = get_component_queries(user_input)
            with st.spinner("กำลังประมวลผล..."):
                result = ask_llm(build_bom_prompt(kb, part_index, queries, collection), user_input)
            st.markdown("---")
            st.subheader("BOM ที่ได้:")
            st.markdown(result)

            if part_index:
                with st.expander(f"🔍 Debug — Part No. ทั้งหมดที่ส่งให้ LLM ({len(part_index)} รายการ)"):
                    for pn in sorted(part_index.keys()):
                        st.write(f"- {pn}")
        else:
            st.warning("กรุณากรอกข้อมูลก่อน")

    if kb["rules"]:
        with st.expander(f"กฎที่ใช้อยู่ ({len(kb['rules'])} ข้อ)"):
            for r in kb["rules"]:
                st.write(f"• {r}")

# ── Tab 2: Catalog ────────────────────────────────────────────────────────────
with tab_catalog:
    # ── Section: Import JSON จาก AI Chat ภายนอก ──────────────────────────────
    with st.expander("⚡ Import จาก AI Chat ภายนอก (ประหยัด token)", expanded=False):
        st.markdown("""
**วิธีใช้ — ทำใน Gemini / Claude / ChatGPT (ฟรี ไม่จำกัด)**

1. ไปที่ [gemini.google.com](https://gemini.google.com) หรือ [claude.ai](https://claude.ai) หรือ [chatgpt.com](https://chatgpt.com)
2. **Upload PDF catalog** เข้าแชท
3. Copy prompt ด้านล่างไป paste แล้วส่ง:
""")
        prompt_template = """อ่าน PDF catalog ที่แนบมาทั้งเล่ม สกัด Part Number/Model ทุกตัว
(ใช้กับ catalog ทุกยี่ห้อ ทุกประเภทอุปกรณ์)

กฎเข้มงวด:
1. สกัด Part No. ทุกตัว ห้ามตกหล่นแม้แต่ตัวเดียว
2. รวม option, accessory, cable, connector ด้วย
3. บอกจำนวนรวมที่พบก่อนเริ่มลิสต์
4. ใช้ Part No. ที่ปรากฏในเอกสารจริง ห้ามแต่งเอง

สำหรับแต่ละ Part No. ระบุ 6 fields:
- brand: ยี่ห้อ (เช่น OMRON, Mitsubishi, Siemens, Schneider, ABB)
- category: หมวด เช่น "CPU Unit", "Power Supply", "Digital Input", "Digital Output",
  "Analog I/O", "Communication", "VFD / Inverter", "Servo Drive", "HMI Touchscreen",
  "Proximity Sensor", "Safety Relay", "Cable", "Terminal Block", "Connector",
  "MCB", "Contactor", "Solenoid Valve", "Push Button" ฯลฯ
- description: คำอธิบายสั้น 1 ประโยค (ภาษาไทยหรืออังกฤษ)
- key_specs: spec สำคัญในบรรทัดเดียว (เช่น "64 points, 24VDC, FCN connector")
- use_when: เมื่อไหร่ควรเลือกใช้ (1 ประโยคสั้นภาษาไทย)
- source: ชื่อไฟล์ PDF

ตอบเป็น JSON เท่านั้น ไม่ต้องมีคำอธิบาย ไม่ต้องห่อ markdown:
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

ดูคู่มือเพิ่มเติมที่ PROMPT_TEMPLATES.md (รวม prompt สำหรับ PDF ใหญ่ และต่อยอด)"""
        st.code(prompt_template, language="text")

        st.markdown("4. Copy JSON ที่ได้ → save เป็นไฟล์ `.json` → upload ที่นี่:")

        st.markdown("**ทาง 1: Upload ไฟล์ .json**")
        json_file = st.file_uploader("อัปโหลด JSON", type=["json", "txt"], key="json_import")

        st.markdown("**ทาง 2: Paste JSON ตรงๆ (สะดวกกว่า)**")
        json_text = st.text_area(
            "วาง JSON ที่ copy จาก AI",
            placeholder='{"CJ2M-CPU34": {"category": "CPU Unit", ...}}',
            height=150,
            key="json_paste",
        )

        merge_mode = st.radio(
            "วิธี import",
            ["รวมกับของเดิม (merge)", "แทนที่ทั้งหมด (replace)"],
            horizontal=True,
        )

        if st.button("📥 Import JSON", type="primary", use_container_width=True):
            raw_text = ""
            if json_file:
                raw_text = json_file.read().decode("utf-8")
                st.info(f"อ่านจากไฟล์: {json_file.name} ({len(raw_text):,} ตัวอักษร)")
            elif json_text.strip():
                raw_text = json_text.strip()
                st.info(f"อ่านจาก textarea ({len(raw_text):,} ตัวอักษร)")
            else:
                st.warning("กรุณาเลือกไฟล์หรือวาง JSON ก่อน")
                st.stop()

            # ลอกพวก markdown code block ออก ```json ... ```
            cleaned = re.sub(r'^```(?:json)?\s*', '', raw_text.strip())
            cleaned = re.sub(r'\s*```\s*$', '', cleaned)
            # ดึง JSON object ที่ใหญ่สุดออกมา (กันมีคำอธิบายปนหน้าหรือหลัง)
            m = re.search(r'\{[\s\S]*\}', cleaned)
            if m:
                cleaned = m.group()

            try:
                new_data = json.loads(cleaned)
            except json.JSONDecodeError as e:
                st.error(f"❌ JSON ผิด format: {e}")
                with st.expander("ดูข้อความที่พยายาม parse"):
                    st.code(cleaned[:1000])
                st.stop()

            if not isinstance(new_data, dict):
                st.error(f"❌ ต้องเป็น dict {{PART-NO: {{...}}}} แต่ได้ {type(new_data).__name__}")
                st.stop()

            # ตรวจ format
            valid_count = sum(1 for v in new_data.values() if isinstance(v, dict))
            if valid_count == 0:
                st.error("❌ ไม่มี Part No. ที่มีโครงสร้างถูกต้อง")
                st.stop()

            try:
                if merge_mode == "แทนที่ทั้งหมด (replace)":
                    save_part_index(new_data)
                    final = new_data
                else:
                    existing = load_part_index()
                    existing.update(new_data)
                    save_part_index(existing)
                    final = existing

                # ตรวจสอบว่าบันทึกจริง
                check = load_part_index()
                st.success(f"✅ บันทึกสำเร็จ — ฐานข้อมูลมี {len(check)} Part No. (เพิ่ม/อัปเดต {len(new_data)} รายการ)")
                st.info(f"📁 บันทึกที่: {os.path.abspath(PART_INDEX_FILE)}")

                with st.expander(f"ตัวอย่าง Part No. ที่ import (5 รายการแรก)"):
                    for pn, info in list(new_data.items())[:5]:
                        st.write(f"**{pn}** → {info.get('category','?')}: {info.get('description','')}")

                st.balloons()
                st.session_state["just_imported"] = True
            except Exception as e:
                st.error(f"❌ บันทึกไม่ได้: {e}")
                st.exception(e)

    st.markdown("---")

    col_upload, col_query = st.columns([1, 1])

    with col_upload:
        st.subheader("อัปโหลด Catalog / Manual")
        st.caption("ดาวน์โหลด PDF จาก omron.com แล้วอัปโหลดที่นี่")

        st.markdown("""
**ลิงก์ดาวน์โหลด OMRON:**
- [CP2E Series Catalog](https://www.ia.omron.com/products/family/3450/)
- [NX/NJ Series Catalog](https://www.ia.omron.com/products/family/3657/)
- [CJ2 Series Catalog](https://www.ia.omron.com/products/family/1804/)
- [OMRON IA รวม Catalog](https://www.ia.omron.com/support/catalogs/)
""")

        uploaded_files = st.file_uploader(
            "เลือก PDF (เลือกหลายไฟล์ได้)",
            type="pdf",
            accept_multiple_files=True,
        )

        use_llm = st.checkbox(
            "ใช้ LLM วิเคราะห์เชิงลึก (แนะนำ)",
            value=True,
            help="LLM จะอ่านแต่ละหน้าเพื่อแยก category, spec, use case ของแต่ละ Part No. — ทำให้ตอนสร้าง BOM แม่นยำขึ้นมาก แต่ใช้เวลานานกว่า (~5-10 นาที/PDF)",
        )

        if uploaded_files and st.button("ประมวลผลและบันทึกลงฐานข้อมูล", type="primary"):
            for pdf_file in uploaded_files:
                with st.spinner(f"กำลังอ่าน {pdf_file.name}..."):
                    text = extract_pdf_text(pdf_file)

                progress_bar = st.progress(0.0)
                status_text = st.empty()

                def update_progress(i, total, msg):
                    progress_bar.progress((i + 1) / max(total, 1))
                    status_text.text(msg)

                n_chunks, n_parts = add_pdf_to_db(
                    collection, pdf_file.name, text,
                    use_llm_extract=use_llm,
                    progress_callback=update_progress,
                )
                progress_bar.empty()
                status_text.empty()
                st.success(f"{pdf_file.name}: บันทึก {n_chunks} chunks, พบ {n_parts} Part No.")
            st.rerun()

        if collection.count() > 0:
            st.info(f"ฐานข้อมูลมี {collection.count()} chunks จาก Catalog")
            stored = set(m["source"] for m in collection.get(include=["metadatas"])["metadatas"])
            for s in stored:
                st.write(f"📄 {s}")

            if st.button("ล้างฐานข้อมูลทั้งหมด"):
                collection.delete(where={"source": {"$ne": ""}})
                st.success("ล้างแล้ว")
                st.rerun()

    with col_query:
        st.subheader("ถามเกี่ยวกับอุปกรณ์")
        st.caption("ถามการเลือกรุ่น, spec, การใช้งาน จาก catalog ที่ import")

        q_part_index = load_part_index()
        has_any_data = collection.count() > 0 or bool(q_part_index)

        if not has_any_data:
            st.warning("ยังไม่มีข้อมูล กรุณา Import JSON หรืออัปโหลด PDF ก่อน")
        else:
            question = st.text_area(
                "คำถาม",
                placeholder="เช่น: PLC รุ่นไหนเหมาะสำหรับงาน motion control 4 แกน?\nCP2E กับ NX1 ต่างกันอย่างไร?",
                height=120,
            )
            if st.button("ถาม", type="primary", use_container_width=True):
                if question.strip():
                    # รวม context จากทั้ง 2 source
                    context_parts = []
                    if collection.count() > 0:
                        with st.spinner("ค้นหาใน Catalog (ChromaDB)..."):
                            chunks = search_catalog(collection, question, n=6)
                            if chunks:
                                context_parts.append("=== จาก PDF chunks ===\n" + "\n\n---\n\n".join(chunks))
                    if q_part_index:
                        # สร้าง list Part No. แบบมี description+spec ให้ LLM เห็น
                        struct_lines = []
                        for pn, info in q_part_index.items():
                            brand = info.get("brand", "")
                            cat = info.get("category", "")
                            desc = info.get("description", "")
                            specs = info.get("key_specs", "")
                            use = info.get("use_when", "")
                            bp = f"[{brand}] " if brand else ""
                            struct_lines.append(f"- {pn} | {bp}{cat} | {desc} | spec: {specs} | ใช้เมื่อ: {use}")
                        context_parts.append("=== Part No. แบบ structured ===\n" + "\n".join(struct_lines))

                    context = "\n\n".join(context_parts)
                    system = f"""คุณเป็นผู้เชี่ยวชาญด้านอุปกรณ์อุตสาหกรรม ตอบคำถามจากข้อมูล catalog ต่อไปนี้เท่านั้น
อ้างอิงรุ่นและ spec ให้ชัดเจน ถ้าไม่มีข้อมูลใน catalog ให้บอกตรงๆ ห้ามแต่ง

ข้อมูลจาก Catalog:
{context}"""
                    with st.spinner("กำลังวิเคราะห์..."):
                        answer = ask_llm(system, question)
                    st.markdown("---")
                    st.markdown(answer)
                else:
                    st.warning("กรุณาพิมพ์คำถาม")

# ── Tab 3: Teach ──────────────────────────────────────────────────────────────
# ── Tab 3: Database Viewer ────────────────────────────────────────────────────
with tab_db:
    st.subheader("ฐานข้อมูล Catalog")

    struct_index = load_part_index()
    has_chroma = collection.count() > 0
    has_struct = bool(struct_index)

    if not has_chroma and not has_struct:
        st.warning("ยังไม่มีข้อมูล — อัปโหลด PDF ที่ tab Catalog หรือ Import JSON")
    else:
        # ดึงข้อมูลทั้งหมดจาก ChromaDB (ถ้ามี)
        if has_chroma:
            all_data = collection.get(include=["documents", "metadatas"])
            all_docs = all_data["documents"]
            all_metas = all_data["metadatas"]
        else:
            all_docs, all_metas = [], []

        # สกัด Part No. ทั้งหมด (OMRON pattern เช่น CJ2M-CPU34, CJ1W-ID211)
        omron_pattern = re.compile(r'\b[A-Z]{1,4}\d*[A-Z]*-[A-Z0-9]{2,10}\b')
        part_numbers = {}
        for doc, meta in zip(all_docs, all_metas):
            for pn in omron_pattern.findall(doc):
                src = meta.get("source", "unknown")
                if pn not in part_numbers:
                    part_numbers[pn] = {"source": src, "context": doc[:200]}

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Chunks ChromaDB", collection.count())
        col2.metric("Part No. (regex)", len(part_numbers))
        col3.metric("Part No. (structured)", len(struct_index))
        sources = set(m["source"] for m in all_metas) | set(v.get("source","") for v in struct_index.values() if v.get("source"))
        col4.metric("ไฟล์ทั้งหมด", len(sources))

        st.markdown("---")

        # ค้นหา Part No.
        search_pn = st.text_input("ค้นหา Part No. หรือคำที่ต้องการ", placeholder="เช่น: CJ1W, output, power supply")

        has_structured = any("category" in v for v in struct_index.values()) if struct_index else False

        if has_structured:
            st.subheader(f"📦 Part No. แบบ Structured ({len(struct_index)} รายการ)")

            # group by category
            by_cat = {}
            for pn, info in struct_index.items():
                cat = info.get("category", "Uncategorized")
                by_cat.setdefault(cat, []).append((pn, info))

            for cat, items in sorted(by_cat.items()):
                with st.expander(f"**{cat}** ({len(items)} รายการ)"):
                    for pn, info in sorted(items):
                        if search_pn and search_pn.upper() not in pn.upper() \
                                and search_pn.lower() not in str(info).lower():
                            continue
                        st.markdown(f"**{pn}**")
                        st.write(f"- {info.get('description','')}")
                        st.caption(f"Spec: {info.get('key_specs','-')} | ใช้เมื่อ: {info.get('use_when','-')}")
                        st.markdown("---")
        elif part_numbers:
            st.subheader(f"Part No. ที่พบใน Catalog ({len(part_numbers)} รายการ)")
            st.info("💡 เพื่อความแม่นยำ: ลบฐานข้อมูลแล้วอัปโหลด PDF ใหม่ พร้อมเปิด 'ใช้ LLM วิเคราะห์เชิงลึก'")
            filtered = {k: v for k, v in part_numbers.items()
                        if not search_pn or search_pn.upper() in k.upper() or search_pn.lower() in v["context"].lower()}

            if filtered:
                for pn, info in sorted(filtered.items()):
                    with st.expander(f"**{pn}** — {info['source']}"):
                        st.text(info["context"])
            else:
                st.info("ไม่พบ Part No. ที่ตรงกับคำค้นหา")

        st.markdown("---")

        # ค้นหาใน chunk โดยตรง
        st.subheader("ค้นหาข้อความใน Catalog")
        keyword = st.text_input("ค้นหาคำ", placeholder="เช่น: FCN, power supply, output module")
        if keyword:
            found_chunks = [(doc, meta) for doc, meta in zip(all_docs, all_metas)
                            if keyword.lower() in doc.lower()]
            st.write(f"พบ {len(found_chunks)} chunk ที่มีคำว่า '{keyword}'")
            for i, (doc, meta) in enumerate(found_chunks[:10]):
                with st.expander(f"Chunk {i+1} — {meta.get('source','')} หน้า {meta.get('chunk','')}"):
                    # highlight keyword
                    highlighted = doc.replace(keyword, f"**{keyword}**")
                    st.markdown(highlighted[:800])

with tab_teach:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("เพิ่มกฎ (Rules)")
        new_rule = st.text_input("กฎใหม่", placeholder="เช่น: เพิ่ม buffer 10% ในทุก quantity")
        if st.button("บันทึกกฎ", use_container_width=True):
            if new_rule.strip():
                kb["rules"].append(new_rule.strip())
                save_knowledge(kb)
                st.success("บันทึกแล้ว!")
                st.rerun()

        if kb["rules"]:
            st.markdown("**กฎทั้งหมด:**")
            for i, rule in enumerate(kb["rules"]):
                c1, c2 = st.columns([5, 1])
                c1.write(f"{i+1}. {rule}")
                if c2.button("ลบ", key=f"del_{i}"):
                    kb["rules"].pop(i)
                    save_knowledge(kb)
                    st.rerun()

    with col2:
        st.subheader("เพิ่มตัวอย่าง (Examples)")
        ex_in = st.text_area("Input ตัวอย่าง", height=100, placeholder="ข้อมูลที่ป้อนเข้า")
        ex_out = st.text_area("Output ที่ถูกต้อง", height=100, placeholder="BOM ที่ควรได้รับ")
        if st.button("บันทึกตัวอย่าง", use_container_width=True):
            if ex_in.strip() and ex_out.strip():
                kb["examples"].append({"input": ex_in.strip(), "output": ex_out.strip()})
                save_knowledge(kb)
                st.success("บันทึกแล้ว!")
                st.rerun()

        if kb["examples"]:
            st.info(f"มีตัวอย่างทั้งหมด {len(kb['examples'])} รายการ")

# ── Sidebar: Token Usage (render LAST so values reflect ทุก LLM call ในรอบนี้) ──
with st.sidebar:
    st.header("📊 Token Usage")
    usage = load_token_usage()
    sess = st.session_state.get("session_tokens", {"input": 0, "output": 0, "calls": 0})

    st.subheader("Session นี้")
    c1, c2 = st.columns(2)
    c1.metric("Input", f"{sess['input']:,}")
    c2.metric("Output", f"{sess['output']:,}")
    st.caption(f"จำนวน call: {sess['calls']}")

    st.subheader("รวมทั้งหมด")
    c3, c4 = st.columns(2)
    c3.metric("Input", f"{usage['total_input']:,}")
    c4.metric("Output", f"{usage['total_output']:,}")
    total_all = usage['total_input'] + usage['total_output']
    st.caption(f"รวม: {total_all:,} tokens · {usage['total_calls']} calls")

    if usage["by_function"]:
        with st.expander("แยกตามฟังก์ชัน"):
            for fn, v in sorted(usage["by_function"].items(), key=lambda x: -(x[1]["input"]+x[1]["output"])):
                tot = v["input"] + v["output"]
                st.write(f"**{fn}**: {tot:,} ({v['calls']} calls)")

    if st.button("🔄 รีเซ็ตยอดทั้งหมด"):
        save_token_usage({"total_input": 0, "total_output": 0, "total_calls": 0, "by_function": {}})
        st.session_state.session_tokens = {"input": 0, "output": 0, "calls": 0}
        st.rerun()

    st.markdown("---")
    st.caption("💰 Gemini 2.5 Flash ฟรี 250 calls/วัน")
