# Cross-Version Comparative Analysis: CT-200 v1 vs v2

## High-Level Document Metrics

| Metric | ct200_manual.pdf (v1) | ct200_manual_v2.pdf (v2) | Difference |
| :--- | :--- | :--- | :--- |
| Page Count | 6 | 7 | +1 page (text reflow spillover) |
| Character Count | 6172 | 6742 | +570 characters |
| Word Count | 949 | 1033 | +84 words |
| Typography | NimbusSans (11, 12.87, 16.5, 24.75pt) | NimbusSans (11, 12.87, 16.5, 24.75pt) | Identical typographic scale |
| Embedded Images | 0 | 0 | None in either version |
| Running Headers/Footers | None | None | No running headers or page numbers |

---

## Key Substantive Specification & Technical Changes

| Section | v1 Specification | v2 Specification | Technical Significance |
| :--- | :--- | :--- | :--- |
| **2.1.1.1 Battery Life** | 300 cycles; low battery icon at < 15% | 250 cycles; low battery icon at < 10% | Revised downward after extended testing |
| **3.2 Inflation Increment** | 40 mmHg increments | 30 mmHg increments | Reduced step size to improve pulse detection |
| **4.2 Error Code E3** | Auto-deflates within 2.0 s | Auto-deflates within 1.5 s | Faster emergency deflation response |
| **4.2 Error Code E6** | Does not exist (E1–E5) | E6: Bluetooth sync failure | New error state for companion app sync |
| **4.3 Alarm Range** | Audible alarms for E1–E5 | Audible alarms for E1–E6 | Updated to reflect E6 addition |
| **5.3 Data Export** | Not present | Section added: CSV export via app | Added feature starting firmware 1.4 |
| **8.1 Regulatory Spillover**| Fits entirely on Page 6 | Pushed onto Page 7 (82 chars) | Creates 1-page overflow with 2 trailing lines |

---

## Structural Irregularity Summary

A total of **22 structural hazards and version discrepancies** were identified and verified against the actual PDFs:

| ID | Category | Location | Severity | Key Hazard |
| :--- | :--- | :--- | :--- | :--- |
| `IRR-SEQ-v1-P3` | Out-of-Order Section Numbering | P3 | **High** | Section '3.4 Auto Shutoff' is physically positioned before Section '3.3 Res... |
| `IRR-SEQ-v2-P3` | Out-of-Order Section Numbering | P3 | **High** | Section '3.4 Auto Shutoff' is physically positioned before Section '3.3 Res... |
| `IRR-ORPHAN-v1-P3` | Orphan Heading at Page Bottom | P3 | **High** | Heading '4. Alarms and Safety Behavior' appears at the very bottom of Page ... |
| `IRR-ORPHAN-v1-P4` | Orphan Heading at Page Bottom | P4 | **High** | Heading '5. Data Management' appears at the very bottom of Page 4 (y ~ 800)... |
| `IRR-ORPHAN-v1-P5` | Orphan Heading at Page Bottom | P5 | **High** | Heading '7. Troubleshooting' appears at the very bottom of Page 5 (y ~ 800)... |
| `IRR-SPLIT-P4-P5` | Sentence Split Across Page Boundary | Page 4 -> Page 5 | **Medium** | Section 4.3 Alarm Thresholds ends on Page 4 with '...except for E3' and con... |
| `IRR-SPLIT-P5-P6` | Sentence Split Across Page Boundary | Page 5 -> Page 6 | **Medium** | Section 6.1 ends on Page 5 with '...Do not submerge the device or cuff, and... |
| `IRR-SPILLOVER-v2-P7` | Orphan Overflow Page / Split Regulatory Statement | Page 6 -> Page 7 | **High** | In v2, added content causes text reflow. Section 8.1 concludes with '...and... |
| `IRR-NO-PAGINATION` | Missing Header / Footer & Pagination Metadata | All Pages (Pages 1-6 / Pages 1-7) | **Medium** | Neither PDF contains running headers, running footers, copyright notices, o... |
| `IRR-TABLE-FRAGMENTATION` | Table Cell Border & Vector Drawing Fragmentation | Page 2 & Page 4 | **High** | Tables on Page 2 (specifications) and Page 4 (error codes) are rendered wit... |
| `IRR-BRAND-ANOMALY` | Manufacturer / Brand Entity Discrepancy | Page 5 (v1) / Page 6 (v2) | **Low** | Section 6.2 states: 'Anthropic recommends professional recalibration every ... |
| `DIFF-2_1_1_1_Battery_Life` | Document Version Difference | v1: P2 | v2: P2 | **Medium** | Specification/content change in 2.1.1.1 Battery Life: '300 measurement cycl... |
| `DIFF-3_1_Powering_On` | Document Version Difference | v1: P2 | v2: P3 | **Medium** | Specification/content change in 3.1 Powering On: 'First sentence located at... |
| `DIFF-3_2_Cuff_Inflation_Sequence` | Document Version Difference | v1: P3 | v2: P3 | **Medium** | Specification/content change in 3.2 Cuff Inflation Sequence: 'Inflates in 4... |
| `DIFF-4_1_&_4__Alarms_Header` | Document Version Difference | v1: P3 | v2: P4 | **Medium** | Specification/content change in 4.1 & 4. Alarms Header: 'Section 4 heading ... |
| `DIFF-4_2_Error_Codes_Table_(E3)` | Document Version Difference | v1: P4 | v2: P4 | **Medium** | Specification/content change in 4.2 Error Codes Table (E3): 'E3 auto-deflat... |
| `DIFF-4_2_Error_Codes_Table_(E6)` | Document Version Difference | v1: P4 | v2: P4 | **Medium** | Specification/content change in 4.2 Error Codes Table (E6): 'Error codes E1... |
| `DIFF-4_3_Alarm_Thresholds` | Document Version Difference | v1: P4 | v2: P4 | **Medium** | Specification/content change in 4.3 Alarm Thresholds: 'Audible alarms limit... |
| `DIFF-5__Data_Management_Header` | Document Version Difference | v1: P4 | v2: P5 | **Medium** | Specification/content change in 5. Data Management Header: 'Section 5 headi... |
| `DIFF-5_3_Data_Export_(New_Section)` | Document Version Difference | v1: PNone | v2: P5 | **Medium** | Specification/content change in 5.3 Data Export (New Section): 'Section doe... |
| `DIFF-7__Troubleshooting_Header` | Document Version Difference | v1: P5 | v2: P6 | **Medium** | Specification/content change in 7. Troubleshooting Header: 'Section 7 headi... |
| `DIFF-8_1_Classification_Spillover` | Document Version Difference | v1: P6 | v2: P6-7 | **Medium** | Specification/content change in 8.1 Classification Spillover: 'Entire secti... |
