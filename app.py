import streamlit as st
import pandas as pd
import io
import datetime

# --------------------------------
# COLUMN NAME CONFIG (adjust if needed)
# --------------------------------
# These should match the header names in your Excel files.

# Inventory (Bin Inventory) file
INV_AREA_COL = "Area"              # Column C - values include "partial CLD"
INV_BIN_STATUS_COL = "Bin Status"  # Column G - "Active"
INV_HU_TYPE_COL = "HU Type"        # Column L - "Cartons"
INV_QUALITY_COL = "Quality"        # Column W - "Good"
INV_INCLUSION_COL = "Inclusion"    # Column AD - "Included"
INV_HU_CODE_COL = "HU Code"        # Column K - HU Code
INV_SKU_COL = "Sku Code"           # Column N - SKU
INV_BATCH_COL = "Batch"            # Column Q - Batch

# Conveyor file
CONV_INNER_HU_COL = "Inner HU"     # Column H - Inner HU

# Outbound SBL file
OUT_SKU_COL = "SKU Allocated"      # Column K - SKU in SBL
OUT_BATCH_COL = "Batch Allocated"  # Column O - Batch in SBL


# --------------------------------
# Helper: check columns
# --------------------------------
def require_columns(df, required_cols, df_name):
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        st.error(
            f"{df_name} is missing required columns: {missing}\n\n"
            f"Available columns: {list(df.columns)}"
        )
        return False
    return True


# --------------------------------
# Step 1: Clean inventory
# --------------------------------
def clean_inventory(inv_df: pd.DataFrame) -> pd.DataFrame:
    df = inv_df.copy()

    # Column C: keep only partial CLD
    if INV_AREA_COL in df.columns:
        df = df[df[INV_AREA_COL].astype(str).str.lower() == "partial cld"]

    # Column G: Bin Status = Active
    if INV_BIN_STATUS_COL in df.columns:
        df = df[df[INV_BIN_STATUS_COL].astype(str).str.lower() == "active"]

    # Column L: HU Type = Cartons
    if INV_HU_TYPE_COL in df.columns:
        df = df[df[INV_HU_TYPE_COL].astype(str).str.lower() == "cartons"]

    # Column W: Quality = Good
    if INV_QUALITY_COL in df.columns:
        df = df[df[INV_QUALITY_COL].astype(str).str.lower() == "good"]

    # Column AD: Inclusion = Included
    if INV_INCLUSION_COL in df.columns:
        df = df[df[INV_INCLUSION_COL].astype(str).str.lower() == "included"]

    # Standardised HU code string
    if INV_HU_CODE_COL in df.columns:
        df["HU_CODE_STR"] = df[INV_HU_CODE_COL].astype(str).str.strip()
    else:
        df["HU_CODE_STR"] = ""

    # Build SKU-Batch key from N & Q for later join with SBL
    if INV_SKU_COL in df.columns and INV_BATCH_COL in df.columns:
        df["SKU_BATCH_INV"] = (
            df[INV_SKU_COL].astype(str).str.strip()
            + "|"
            + df[INV_BATCH_COL].astype(str).str.strip()
        )
    else:
        df["SKU_BATCH_INV"] = ""

    return df


# --------------------------------
# Step 2 & 3: Full analysis
# --------------------------------
def analyze(inv_df: pd.DataFrame,
            conv_df: pd.DataFrame,
            out_df: pd.DataFrame):

    # 1) Clean inventory
    clean_inv = clean_inventory(inv_df)

    # 2) Not-fed HUs: compare Inventory HU (K) vs Conveyor Inner HU (H)
    conv = conv_df.copy()
    conv["INNER_HU_STR"] = conv[CONV_INNER_HU_COL].astype(str).str.strip()

    fed_hus = set(conv["INNER_HU_STR"].dropna())
    not_fed_inv = clean_inv[~clean_inv["HU_CODE_STR"].isin(fed_hus)].copy()

    # 3) Build SKU-Batch key in outbound SBL (K & O)
    out = out_df.copy()
    out["SKU_BATCH_SBL"] = (
        out[OUT_SKU_COL].astype(str).str.strip()
        + "|"
        + out[OUT_BATCH_COL].astype(str).str.strip()
    )

    demand_keys = set(out["SKU_BATCH_SBL"].dropna())

    # 4) Final output:
    #    Inventory rows that are NOT fed AND whose SKU-Batch key exists in SBL demand
    not_fed_and_demanded = not_fed_inv[
        not_fed_inv["SKU_BATCH_INV"].isin(demand_keys)
    ].copy()

    return clean_inv, not_fed_inv, not_fed_and_demanded


# --------------------------------
# Streamlit UI
# --------------------------------
st.set_page_config(page_title="Wave Inventory Analyzer", layout="wide")
st.title("📦 Wave Inventory Analyzer")

st.write(
    """
This app follows your exact manual process:

1. Filter Inventory by:
   - Column C = partial CLD
   - Column G = Bin Status Active
   - Column L = HU Type Cartons
   - Column W = Quality Good
   - Column AD = Inclusion Included
2. VLOOKUP Inventory HU Code (col K) with Conveyor Inner HU (col H) to find **not-fed HUs**.
3. From those not-fed HUs, build SKU-Batch from Inventory N+Q and match with SBL K+O.
4. Final result = Inventory rows that are not fed on conveyor but have demand in SBL.
"""
)

inv_file = st.file_uploader("1️⃣ Upload Inventory file", type=["xlsx", "xls"])
conv_file = st.file_uploader("2️⃣ Upload Conveyor file", type=["xlsx", "xls"])
out_file = st.file_uploader("3️⃣ Upload Outbound SBL file", type=["xlsx", "xls"])

if inv_file and conv_file and out_file:
    if st.button("🚀 Run Analysis"):
        # Read the files
        inv_df = pd.read_excel(inv_file)
        conv_df = pd.read_excel(conv_file)
        out_df = pd.read_excel(out_file)

        # Check required columns exist
        ok = True
        ok &= require_columns(
            inv_df,
            [INV_AREA_COL, INV_BIN_STATUS_COL, INV_HU_TYPE_COL,
             INV_QUALITY_COL, INV_INCLUSION_COL, INV_HU_CODE_COL,
             INV_SKU_COL, INV_BATCH_COL],
            "Inventory file",
        )
        ok &= require_columns(
            conv_df,
            [CONV_INNER_HU_COL],
            "Conveyor file",
        )
        ok &= require_columns(
            out_df,
            [OUT_SKU_COL, OUT_BATCH_COL],
            "Outbound SBL file",
        )

        if ok:
            clean_inv, not_fed_inv, not_fed_and_demanded = analyze(inv_df, conv_df, out_df)

            st.subheader("✅ Clean Inventory (after all filters)")
            st.dataframe(clean_inv.head(50))

            st.subheader("❌ Not Fed Inventory HUs (all rows for HUs not on conveyor)")
            st.dataframe(not_fed_inv.head(50))

            st.subheader("📌 Not Fed but Required in SBL Demand (final output)")
            st.dataframe(not_fed_and_demanded.head(50))

            # Prepare Excel for download
            buffer = io.BytesIO()
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"wave_analysis_{ts}.xlsx"

            with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                clean_inv.to_excel(writer, sheet_name="clean_inventory", index=False)
                not_fed_inv.to_excel(writer, sheet_name="not_fed_inventory", index=False)
                not_fed_and_demanded.to_excel(writer, sheet_name="not_fed_and_demanded", index=False)
                conv_df.to_excel(writer, sheet_name="raw_conveyor", index=False)
                out_df.to_excel(writer, sheet_name="raw_outbound", index=False)

            buffer.seek(0)

            st.markdown("### ⬇️ Download analyzed Excel")
            st.download_button(
                label="Download",
                data=buffer,
                file_name=file_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
else:
    st.info("Upload all three files and then click 'Run Analysis'.")
