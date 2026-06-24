import os
import json
import fitz
import gradio as gr
from groq import Groq
import pandas as pd
import sqlite3
from pdf2image import convert_from_path
import pytesseract

conn = sqlite3.connect(
    "invoices.db",
    check_same_thread=False
)

cursor = conn.cursor()

cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS invoices(
        invoice_number TEXT PRIMARY KEY,
        date TEXT,
        vendor TEXT,
        po_number TEXT,
        total_amount TEXT
    )
    """
)

conn.commit()

# --------------------------------------
# Groq Client
# --------------------------------------
client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)


# --------------------------------------
# Read PDF using PyMuPDF
# --------------------------------------
def read_pdf(file):

    try:

        pages = convert_from_path(file.name)

        text = ""

        for page in pages:
            text += pytesseract.image_to_string(page)

        return text

    except Exception as e:

        return f"Error reading PDF: {str(e)}"


# --------------------------------------
# Query Groq
# --------------------------------------
def query_llm(prompt):

    try:

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content":
                    """
You are an expert invoice extraction engine.

Return ONLY valid JSON.

Never explain.
Never use markdown.
Never use ```json.
Preserve exact values.
Return empty strings for missing values.
"""
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0,
            top_p=1,
            response_format={"type": "json_object"}
        )

        return response.choices[0].message.content

    except Exception as e:

        return f"Request Failed: {str(e)}"


# --------------------------------------
# Duplicate Detection
# --------------------------------------
def save_invoice(data):

    try:

        cursor.execute(
            """
            INSERT INTO invoices
            VALUES (?,?,?,?,?)
            """,
            (
                data["invoice_number"],
                data["date"],
                data["vendor"],
                data["po_number"],
                data["total_amount"]
            )
        )

        conn.commit()

        return "✅ Invoice Saved"

    except sqlite3.IntegrityError:

        return "⚠️ Duplicate Invoice Found"

# --------------------------------------
# History Table
# --------------------------------------
def load_history():

    df = pd.read_sql_query(
        "SELECT * FROM invoices",
        conn
    )

    return df
    
# --------------------------------------
# Main Extraction
# --------------------------------------
def extract_invoice(file):

    if file is None:

        return (
            {"error": "Please upload a PDF."},
            "",
            "",
            "",
            pd.DataFrame()
        )

    text = read_pdf(file)

    if text is None:

        return (
            {"error": "No text found."},
            "",
            "",
            "",
            pd.DataFrame()
        )

    print("\n========== PDF TEXT ==========")
    print(text)
    print("==============================\n")

    prompt = f"""
You are an expert invoice extraction engine.

Below is invoice text.

Extract:

1. invoice_number
2. date
3. vendor
4. po_number
5. total_amount

Examples:

Invoice number: 00001
Invoice Date: 24/10/2005
Purchase Order Number: 00002
Your company name: Your Company name
Total: $90

Return ONLY valid JSON.

Schema:

{{
"invoice_number":"",
"date":"",
"vendor":"",
"po_number":"",
"total_amount":""
}}

Invoice text:

{text}
"""

    result = query_llm(prompt)

    print("\n========== RAW LLM OUTPUT ==========")
    print(result)
    print("===================================\n")

    try:

        extracted_json = json.loads(result)
        status = save_invoice(extracted_json)
        history = load_history()

        return (
            extracted_json,
            result,
            text,
            status,
            history
        )

    except Exception as e:

        return (
            {
                "error": f"JSON parsing failed: {str(e)}"
            },
            result,
            text,
             "❌ Extraction Failed",
             pd.DataFrame()
        )


# --------------------------------------
# Multiple PDF Processing
# --------------------------------------
def process_multiple(files):

    all_results = []

    for file in files:

        extracted_json, raw_output, text, status, history = extract_invoice(file)

        all_results.append(extracted_json)

    return (
        all_results,
        "",
        "",
        f"✅ {len(files)} invoices processed",
        load_history()
    )
# --------------------------------------
# --------------------------------------  


def export_excel():

    df = pd.read_sql_query(
        "SELECT * FROM invoices",
        conn
    )

    file_name = "invoice_report.xlsx"

    df.to_excel(
        file_name,
        index=False
    )

    return file_name

# --------------------------------------
# UI
# --------------------------------------
with gr.Blocks(theme=gr.themes.Soft()) as app:

    gr.Markdown(
        """
# 🧾 AI Invoice Reader

Upload Invoice PDF and extract structured data using Llama 3.3 70B.
"""
    )

    file_input = gr.File(
        label="📄 Upload Invoice PDFs",
        file_types=[".pdf"],
        file_count="multiple"
    )

    extract_btn = gr.Button(
        "🚀 Extract Data",
        variant="primary"
    )

    output_json = gr.JSON(
        label="📊 Extracted Invoice Data"
    )

    raw_output = gr.Textbox(
        label="🤖 Raw LLM Response",
        lines=8
    )

    pdf_text = gr.Textbox(
        label="📄 Extracted PDF Text",
        lines=15
    )

    status_output = gr.Textbox(
    label="📌 Status"
    )

    history_table = gr.DataFrame(
    label="📋 Invoice History"
    )

    excel_file = gr.File(
    label="📊 Download Excel Report"
    )

    excel_btn = gr.Button(
    "📥 Export Excel"
    )


    extract_btn.click(
        fn=process_multiple,
        inputs=file_input,
        outputs=[
            output_json,
            raw_output,
            pdf_text,
            status_output,
            history_table
        ]
    )

    excel_btn.click(
        fn=export_excel,
        outputs=excel_file
    )


    clear_btn = gr.Button(
        "🧹 Clear"
    )
    


# --------------------------------------
# Launch
# --------------------------------------
if __name__ == "__main__":
    app.launch()