import streamlit as st
import pandas as pd
import io
import datetime

# --------------------------
# FINAL CONFIG (matches your files)
# --------------------------
INV_SHEET_NAME = "HU level"        # inventory workbook sheet to use

# Inventory (HU level) columns
INV_AREA_COL = "Area Code"         # Column C
INV_BIN_STATUS_COL = "Bin Status"  # Column G
INV_HU_TYPE_COL = "HU Type"        # Column L
INV_QUALITY_COL = "Quality"        # Column W
INV_INCLUSION_COL = "Inclusion Status"  # Column AD
INV_HU_CODE_COL = "HU Code"        # Column K
INV_SKU_COL = "Sku Code"           # Column N
INV_BATCH_COL = "Batch"            # Column Q

# Conveyor
CONV_INNER_HU_COL = "InnerHU"      # Column H

# Outbound SBL
OUT_SKU_COL = "Sku"                # Column K
OUT_BATCH_COL = "Batch Allocated"  # Column N

# --------------------------
# Helpers
# --------------------------
def normalize_series(s: pd.Series) -> pd.Series:
    s2 = s.fillna("").astype(str)
    s2 = s2.str.replace("\u00A0", " ", regex=False)  # NBSP -> space
    s2 = s2.str.replace(r"\s+", " ", regex=True)     # collapse whitespace
    s2 = s2.str.strip()
    s2 = s2.str.lower()
    return s2

def concat_no_delim(a: pd.Series, b: pd.Series) -> pd.Series:
    # normalize then concat without delim, keeping casing/whitespace handled
    return normalize_series(a) + normalize_series(b)

# --------------------------
# Core pipeline
# --------------------------
def run_pipeline(inv_df: pd.DataFrame, conv_df: pd.DataFrame, out_df: pd.DataFrame):
    # 1) Use HU level sheet (inv_df already from that sheet)
    inv = inv_df.copy()

    # 2) Apply inventory filters (safe if columns missing)
    if INV_AREA_COL in inv.columns:
        inv = inv[inv[INV_AREA_COL].astype(str).str.lower().str.contains("partial", na=False)]
    if INV_BIN_STATUS_COL in inv.columns:
        inv = inv[inv[INV_BIN_STATUS_COL].astype(str).str.lower() == "active"]
    if INV_HU_TYPE_COL in inv.columns:
        inv = inv[inv[INV_HU_TYPE_COL].astype(str).str.lower() == "cartons"]
    if INV_QUALITY_COL in inv.columns:
        inv = inv[inv[INV_QUALITY_COL].astype(str).str.lower() == "good"]
    if INV_INCLUSION_COL in inv.columns:
        inv = inv[inv[INV_INCLUSION_COL].astype(str).str.lower().str.contains("included", na=False)]

    # 3) normalize and create inventory key (NO delimiter)
    if INV_SKU_COL in inv.columns and INV_BATCH_COL in inv.columns:
        inv["INV_KEY"] = concat_no_delim(inv[INV_SKU_COL], inv[INV_BATCH_COL])
    else:
        inv["INV_KEY"] = ""

    # 4) normalize HU codes in inventory
    if INV_HU_CODE_COL in inv.columns:
        inv["HU_norm"] = normalize_series(inv[INV_HU_CODE_COL])
    else:
        inv["HU_norm"] = ""

    # 5) conveyor normalize
    conv = conv_df.copy()
    if CONV_INNER_HU_COL in conv.columns:
        conv["INNER_norm"] = normalize_series(conv[CONV_INNER_HU_COL])
    else:
        # try to detect similar column if naming slightly different
        matched = [c for c in conv.columns if "inner" in c.lower() and "hu" in c.lower()]
        if matched:
            conv["INNER_norm"] = normalize_series(conv[matched[0]])
        else:
            conv["INNER_norm"] = ""

    # Map inventory HU -> conveyor HU (for rows that are fed)
    fed_set = set(conv["INNER_norm"].dropna().unique())

    # 6) outbound keys: create normalized key and also keep original concatenation for SBL Demand column
    out = out_df.copy()
    if OUT_SKU_COL in out.columns and OUT_BATCH_COL in out.columns:
        out["OUT_KEY"] = concat_no_delim(out[OUT_SKU_COL], out[OUT_BATCH_COL])
        # Original-style (exact concatenation without delimiter) to show in final sheet (preserve original values trimmed)
        out["OUT_CONCAT"] = out[OUT_SKU_COL].fillna("").astype(str).str.strip() + out[OUT_BATCH_COL].fillna("").astype(str).str.strip()
    else:
        out["OUT_KEY"] = ""
        out["OUT_CONCAT"] = ""

    # Build mapping OUT_KEY -> OUT_CONCAT (first occurrence)
    out_map = out.dropna(subset=["OUT_KEY"]).drop_duplicates(subset=["OUT_KEY"]).set_index("OUT_KEY")["OUT_CONCAT"].to_dict()
    demand_keys = set(out["OUT_KEY"].dropna().unique())

    # 7) Find not-fed inventory rows
    inv["Is_Fed"] = inv["HU_norm"].isin(fed_set)
    not_fed = inv[inv["Is_Fed"] == False].copy()

    # 8) From not_fed, keep only those whose INV_KEY is in demand_keys
    not_fed["INV_KEY"] = not_fed["INV_KEY"].fillna("")
    mask = not_fed["INV_KEY"].isin(demand_keys)
    final = not_fed[mask].copy()

    # 9) Add Conveyor_HU column (for context) - blank since these are not fed, but keep for parity
    #    For safety, we can attempt to map inventory HU to any conveyor HU if exists (probably none)
    final["Conveyor_HU"] = ""  # empty because these HUs are not fed
    # 10) Add SBL Demand column using mapping from OUT_KEY -> OUT_CONCAT
    final["SBL Demand"] = final["INV_KEY"].map(lambda k: out_map.get(k, ""))

    # Reorder to keep all original inventory columns first, then append Conveyor_HU and SBL Demand
    inventory_cols = list(inv_df.columns) if len(inv_df.columns) > 0 else list(final.columns)
    # ensure columns that may not exist are filtered
    inventory_cols = [c for c in inventory_cols if c in final.columns]
    extra_cols = [c for c in ["Conveyor_HU", "SBL Demand"] if c in final.columns]
    final = final.reindex(columns=inventory_cols + extra_cols)

    return final, {
        "counts": {
            "inventory_after_filters": len(inv),
            "not_fed_count": len(not_fed),
            "final_matched_count": len(final),
            "demand_keys": len(demand_keys)
        }
    }

# --------------------------
# Streamlit App UI
# --------------------------
st.set_page_config(page_title="Wave Inventory Analyzer — Final Output", layout="wide")
st.title("📦 Wave Inventory Analyzer — Final single-sheet output")

st.markdown("""
Upload the three files for one wave:
1. Inventory workbook (must contain **'HU level'** sheet)  
2. Conveyor HU Events report  
3. Outbound SBL report  

The output will be a single sheet containing full inventory rows for HUs that:
- were in partial CLD, Active, Cartons, Good, Included  
- were **NOT fed** to conveyor  
- and whose SKU+Batch (concatenated **without** delimiter) appears in the SBL outbound file.
""")

inv_file = st.file_uploader("1️⃣ Inventory workbook (with 'HU level')", type=["xlsx", "xls"])
conv_file = st.file_uploader("2️⃣ Conveyor HU Events file", type=["xlsx", "xls"])
out_file = st.file_uploader("3️⃣ Outbound SBL report", type=["xlsx", "xls"])

if inv_file and conv_file and out_file:
    if st.button("Run and produce final sheet"):
        # 1) load inventory HU level sheet
        try:
            xls = pd.ExcelFile(inv_file)
            if INV_SHEET_NAME not in xls.sheet_names:
                st.error(f"Inventory workbook does not contain sheet '{INV_SHEET_NAME}'. Available: {xls.sheet_names}")
                st.stop()
            inv_df = pd.read_excel(xls, sheet_name=INV_SHEET_NAME)
        except Exception as e:
            st.error(f"Failed reading inventory workbook: {e}")
            st.stop()

        # 2) load other files
        try:
            conv_df = pd.read_excel(conv_file)
        except Exception as e:
            st.error(f"Failed reading conveyor file: {e}")
            st.stop()

        try:
            out_df = pd.read_excel(out_file)
        except Exception as e:
            st.error(f"Failed reading outbound file: {e}")
            st.stop()

        # run pipeline
        final_sheet, meta = run_pipeline(inv_df, conv_df, out_df)

        st.markdown("### Summary")
        st.write(meta["counts"])

        st.markdown("### Final Output Preview (top 200 rows)")
        st.dataframe(final_sheet.head(200))

        # create downloadable single-sheet workbook
        buffer = io.BytesIO()
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"Not_Fed_and_Demanded_{ts}.xlsx"
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            final_sheet.to_excel(writer, sheet_name="Not_Fed_and_Demanded", index=False)
        buffer.seek(0)

        st.download_button("⬇️ Download final sheet (single-sheet Excel)", buffer, fname,
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
else:
    st.info("Please upload Inventory workbook, Conveyor file, and Outbound SBL file.")
