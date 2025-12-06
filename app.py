import streamlit as st
import pandas as pd
import io
import datetime

# -------------------------------
# CONFIG: INVENTORY / CONVEYOR
# (Outbound will be chosen via UI)
# -------------------------------

INV_AREA_COL = "Area"                 # partial CLD
INV_BIN_STATUS_COL = "Bin Status"     # Active
INV_HU_TYPE_COL = "HU Type"           # Cartons
INV_SKU_COL = "Sku Code"              # Column N
INV_BATCH_COL = "Batch"               # Column Q
INV_EXPIRY_COL = "Day to Batch Expiry"
INV_QUALITY_COL = "Quality"           # Good
INV_INCLUSION_COL = "Inclusion Status"  # Included
INV_HU_CODE_COL = "HU Code"           # HU in inventory

CONV_HU_COL_DEFAULT = "HU"            # default HU col in conveyor


# -------------------------------
# CLEAN INVENTORY
# -------------------------------
def clean_inventory(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Area = partial cld (or contains "partial")
    if INV_AREA_COL in df.columns:
        df = df[df[INV_AREA_COL].astype(str).str.lower().str.contains("partial", na=False)]

    # Bin Status = Active
    if INV_BIN_STATUS_COL in df.columns:
        df = df[df[INV_BIN_STATUS_COL].astype(str).str.lower() == "active"]

    # HU Type = Cartons
    if INV_HU_TYPE_COL in df.columns:
        df = df[df[INV_HU_TYPE_COL].astype(str).str.lower() == "cartons"]

    # Expiry: remove blanks & "expired"
    if INV_EXPIRY_COL in df.columns:
        exp = df[INV_EXPIRY_COL].astype(str).str.strip().str.lower()
        df = df[(exp != "") & (exp != "expired")]

    # Quality = Good
    if INV_QUALITY_COL in df.columns:
        df = df[df[INV_QUALITY_COL].astype(str).str.lower() == "good"]

    # Inclusion Status = Included
    if INV_INCLUSION_COL in df.columns:
        df = df[df[INV_INCLUSION_COL].astype(str).str.lower() == "included"]

    # SKU-Batch combo
    if INV_SKU_COL in df.columns and INV_BATCH_COL in df.columns:
        df["SKU_BATCH"] = (
            df[INV_SKU_COL].astype(str).str.strip()
            + "|"
            + df[INV_BATCH_COL].astype(str).str.strip()
        )
    else:
        df["SKU_BATCH"] = ""

    # HU code string
    if INV_HU_CODE_COL in df.columns:
        df["HU_CODE_STR"] = df[INV_HU_CODE_COL].astype(str).str.strip()
    else:
        df["HU_CODE_STR"] = ""

    return df


# -------------------------------
# MAIN ANALYSIS
# -------------------------------
def analyze(inv_df, conv_df, out_df, conv_hu_col, out_sku_col, out_batch_col):
    # 1) Clean inventory with your business rules
    clean_inv = clean_inventory(inv_df)

    # 2) Not-fed HUs (inventory HU not present in conveyor HU)
    conv = conv_df.copy()
    conv["HU_STR"] = conv[conv_hu_col].astype(str).str.strip()

    fed_hus = set(conv["HU_STR"].dropna())
    not_fed = clean_inv[~clean_inv["HU_CODE_STR"].isin(fed_hus)].copy()

    # 3) Outbound SKU-Batch
    out = out_df.copy()
    out["SKU_BATCH"] = (
        out[out_sku_col].astype(str).str.strip()
        + "|"
        + out[out_batch_col].astype(str).str.strip()
    )
    demand_batches = set(out["SKU_BATCH"].dropna())

    # 4) Not-fed but demanded
    not_fed_but_demanded = not_fed[not_fed["SKU_BATCH"].isin(demand_batches)].copy()

    return clean_inv, not_fed, not_fed_but_demanded


# -------------------------------
# STREAMLIT UI
# -------------------------------
st.set_page_config(page_title="Wave Inventory Analyzer", layout="wide")
st.title("📦 Wave Inventory Analyzer")

st.write(
    """
Upload the 3 files for a wave:

1. **Inventory file** (pre-wave, partial CLD etc.)
2. **Conveyor HU Events** report
3. **Outbound SBL** report

Then select the correct columns and run the analysis.
"""
)

inv_file = st.file_uploader("1️⃣ Upload Inventory File", type=["xlsx", "xls"])
conv_file = st.file_uploader("2️⃣ Upload Conveyor Report", type=["xlsx", "xls"])
out_file = st.file_uploader("3️⃣ Upload Outbound SBL Report", type=["xlsx", "xls"])

if inv_file and conv_file and out_file:
    # Read all three files
    inv_df = pd.read_excel(inv_file)
    conv_df = pd.read_excel(conv_file)
    out_df = pd.read_excel(out_file)

    st.success("Files uploaded successfully. Now choose the correct columns.")

    # --- Conveyor HU column choice ---
    st.subheader("Select HU column from Conveyor report")
    conv_hu_col = st.selectbox(
        "HU column in Conveyor file",
        options=list(conv_df.columns),
        index=list(conv_df.columns).index(CONV_HU_COL_DEFAULT)
        if CONV_HU_COL_DEFAULT in conv_df.columns
        else 0,
        key="conv_hu",
    )

    # --- Outbound SKU & Batch column choice ---
    st.subheader("Select SKU & Batch columns from Outbound SBL file")
    out_sku_col = st.selectbox(
        "SKU column in Outbound file (Column K in your sheet)",
        options=list(out_df.columns),
        key="out_sku",
    )
    out_batch_col = st.selectbox(
        "Batch column in Outbound file (Column N in your sheet)",
        options=list(out_df.columns),
        key="out_batch",
    )

    if st.button("🚀 Run Analysis"):
        clean_inv, not_fed, not_fed_but_demanded = analyze(
            inv_df, conv_df, out_df, conv_hu_col, out_sku_col, out_batch_col
        )

        st.markdown("### ✅ Clean Inventory (after filters)")
        st.dataframe(clean_inv.head(20))

        st.markdown("### ❌ Not Fed Inventory HUs")
        st.dataframe(not_fed.head(20))

        st.markdown("### 📌 Not Fed but Had Demand (main output)")
        st.dataframe(not_fed_but_demanded.head(20))

        # Prepare Excel download
        buffer = io.BytesIO()
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"wave_analysis_{ts}.xlsx"

        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            clean_inv.to_excel(writer, sheet_name="clean_inventory", index=False)
            not_fed.to_excel(writer, sheet_name="not_fed_inventory", index=False)
            not_fed_but_demanded.to_excel(writer, sheet_name="not_fed_but_demanded", index=False)
            conv_df.to_excel(writer, sheet_name="raw_conveyor", index=False)
            out_df.to_excel(writer, sheet_name="raw_outbound", index=False)

        buffer.seek(0)

        st.markdown("### ⬇️ Download full analysis")
        st.download_button(
            label="Download analyzed Excel",
            data=buffer,
            file_name=file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
else:
    st.info("Please upload all three files to continue.")
