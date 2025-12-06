# Wave Inventory Analyzer

Streamlit app to analyze warehouse waves using three files:

1. **Inventory file (pre-wave)**  
2. **Conveyor HU Events report**  
3. **Outbound SBL report**

## What it does

For a given wave:

1. Filters the inventory to keep only:
   - Area = partial CLD (column C)
   - Bin Status = Active (column G)
   - HU Type = Cartons (column L)
   - Not expired and not blank in expiry column (column T)
   - Quality = Good (column W)
   - Inclusion Status = Included (column AD)
2. From that filtered inventory, finds HUs that were **not fed** to conveyor:
   - Inventory HU Code (column K) not present in Conveyor HU column (G).
3. For those **not-fed HUs**, checks which SKU–Batches had demand in the Outbound SBL report:
   - Inventory SKU (N) + Batch (Q)
   - Outbound SBL: SKU Allocated (K) + Batch Allocated (N)

Outputs:

- `clean_inventory`: filtered inventory after all rules  
- `not_fed_inventory`: all rows (all columns) for HUs not fed to conveyor  
- `not_fed_but_demanded`: all rows for HUs not fed **and** whose SKU–Batch had SBL demand  
- `raw_conveyor`, `raw_outbound`: raw helper sheets

All of this is exported into a single Excel file for download.

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
