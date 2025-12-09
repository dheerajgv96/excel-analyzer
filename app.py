import streamlit as st
import pandas as pd
import io
import datetime

# --------------------------------
# FINAL COLUMN CONFIG (MATCHES YOUR FILES)
# --------------------------------

# Inventory (HU Level sheet)
INV_AREA_COL = "Area Code"          # Col C
INV_BIN_STATUS_COL = "Bin Status"   # Col G
INV_HU_TYPE_COL = "HU Type"         # Col L
INV_QUALITY_COL = "Quality"         # Col W
INV_INCLUSION_COL = "Inclusion Status"  # Col AD
INV_HU_CODE_COL = "HU Code"         # Col K
INV_SKU_COL = "Sku Code"            # Col N
INV_BATCH_COL = "Batch"             # Col Q

# Conveyor file
CONV_INNER_HU_COL = "InnerHU"       # Col H

# Outbound SBL file
OUT_SKU_COL = "Sku"                 # Col K
OUT_BATCH_COL = "Batch Allocated"   # Col N

# Inventory sheet name
INV_SHEET_NAME = "HU level"         # sheet to use in inventory workbook


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
# Step 1: Clean inventory (from HU level sheet)
# --------------------------------
def clean_inventory(inv_df: pd.DataFrame) -> pd.DataFrame:
    df = inv_df.copy()

    # Area Code = partial CLD
    if INV_AREA_COL in df.columns:
        df = df[df[INV_AREA_COL].astype(str).str.lower() == "partial cld"]

    # Bin Status = Active
    if INV_BIN_STATUS_COL in df.columns:
        df = df[df[INV_BIN_STATUS_COL].astype(str).str.lower() == "active"]

    # HU Type = Cartons
    if INV_HU_TYPE_COL in df.columns:
        df = df[df[INV_HU_TYPE_COL].astype(str).str.lower() == "cartons"]

    # Quality = Good
    if INV_QUALITY_COL in df.columns:
        df = df[df[INV_QUALITY_COL].astype(str).str.lower() == "good"]

    # Inclusion Status = Included
    if INV_INCLUSION_COL in df.columns:
        df = df[df[INV_INCLUSION_COL].astype(str).str.lower() == "included"]

    # Normalised HO code string (join key with conveyor)
    if INV_HU_CODE_COL in df.columns:
        df["HO_CODE_STR"] = df[INV_HU_CODE_COL].astype(str).str.strip()
    else:
        df["HO_CODE_STR"] = ""

    # Build SKU-Batch key from SKU Code + Batch (N + Q)
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
# Step 2 & 3: Full analysis pipeline
# --------------------------------
def analyze(inv_df: pd.DataFrame,
            conv_df: pd.DataFrame,
            out_df: pd.DataFrame):

    # 1) Clean inventory (partial CLD, active, cartons, good, included)
    clean_inv = clean_inventory(inv_df)

    # 2) Not-fed HUs: Inventory HO Code (K) vs Conveyor InnerHU (H)
    conv = conv_df.copy()
    conv["INNER_HU_STR"] = conv[CONV_INNER_HU_COL].astype(str).str.strip()

    fed_hus = set(conv["INNER_HU_STR"].dropna())
    not_fed_inv = clean_inv[~clean_inv["HO_CODE_STR"].isin(fed_hus)].copy()

    # 3) Build SKU-Batch key in outbound SBL (Sku + Batch Allocated: K & N)
    out = out_df.copy()
    out["SKU_BATCH_SBL"] = (
        out[OUT_SKU_COL].astype(str).str.strip()
        + "|"
        + out[OUT_BATCH_COL].astype(str).str.strip()
    )

    demand_keys = set(out["SKU_BATCH_SBL"].dropna())

    # 4) Final output:
    #    Inventory rows that are NOT fed AND whose SKU-Batch exists in SBL demand
    not_fed_and_demanded = not_fed_inv[
        not_fed_inv["SKU_BATCH_INV"].isin(demand_keys)
    ].copy()

    return clean_inv, not_fed_inv, not_fed_and_demanded


# --------------------------------
# Streamlit UI
# --------------------------------
st.set_page_config(page_title="Wave Inventory Analyzer", layout="wide")
st.title("📦 Wave Inventory Analyzer (HU level inventory)")

st.write(
    """
This app automates your manual process:

1. From the Inventory workbook, it uses only the **'HU level'** sheet.
2. Filters rows where:
   - **Area Code** = `partial CLD`
   - **Bin Status** = `Active`
   - **HU Type** = `Cartons`
   - **Quality** = `Good`
   - **Inclusion Status** = `Included`
3. Finds **HUs not fed** by comparing:
   - Inventory **HO Code (K)**
   - Conveyor **InnerHU (H)**
4. Builds SKU–Batch:
   - Inventory: **Sku Code (N) + Batch (Q)**
   - SBL: **Sku (K) + Batch Allocated (N)**
5. Final result: inventory rows that were **not fed** but **had demand in SBL**.
"""
)

inv_file = st.file_uploader("1️⃣ Upload Inventory workbook (with 'HU level' sheet)", type=["xlsx", "xls"])
conv_file = st.file_uploader("2️⃣ Upload Conveyor file", type=["xlsx", "xls"])
out_file = st.file_uploader("3️⃣ Upload Outbound SBL file", type=["xlsx", "xls"])

if inv_file and conv_file and out_file:
    if st.button("🚀 Run Analysis"):
        # ----- Read Inventory: HU level sheet -----
        try:
            inv_xls = pd.ExcelFile(inv_file)
            if INV_SHEET_NAME not in inv_xls.sheet_names:
                st.error(
                    f"Inventory workbook does not contain a sheet named '{INV_SHEET_NAME}'.\n"
                    f"Available sheets: {inv_xls.sheet_names}"
                )
                st.stop()
            inv_df = pd.read_excel(inv_xls, sheet_name=INV_SHEET_NAME)
        except Exception as e:
            st.error(f"Failed to read inventory HU level sheet: {e}")
            st.stop()

        # ----- Read Conveyor & Outbound -----
        conv_df = pd.read_excel(conv_file)
        out_df = pd.read_excel(out_file)

        # Check required columns exist
        ok = True
        ok &= require_columns(
            inv_df,
            [
                INV_AREA_COL, INV_BIN_STATUS_COL, INV_HU_TYPE_COL,
                INV_QUALITY_COL, INV_INCLUSION_COL, INV_HU_CODE_COL,
                INV_SKU_COL, INV_BATCH_COL
            ],
            "Inventory (HU level) sheet",
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

            st.subheader("✅ Clean Inventory (HU level, after all filters)")
            st.dataframe(clean_inv.head(50))

            st.subheader("❌ Not Fed Inventory HUs (rows from HU level sheet)")
            st.dataframe(not_fed_inv.head(50))

            st.subheader("📌 Not Fed but Required in SBL Demand (final output)")
            st.dataframe(not_fed_and_demanded.head(50))

            # Prepare Excel for download
            buffer = io.BytesIO()
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"wave_analysis_{ts}.xlsx"

            with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                clean_inv.to_excel(writer, sheet_name="clean_inventory_HU_level", index=False)
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

