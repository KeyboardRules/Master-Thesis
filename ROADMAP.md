# ROADMAP — Lộ trình 26 tuần (5 giai đoạn)

Bám theo kế hoạch gốc `26Weeks.txt`. Ký hiệu: ✅ xong · 🟡 code xong, chưa chạy · 🟠 kế hoạch
+ code stub, chưa chạy · ⬜ chưa bắt đầu.

| GĐ | Tuần | Mục tiêu | Tiêu chí đạt | Trạng thái |
|---|---|---|---|---|
| 0 | 1–2 | Khả thi + exporter MDG/CHG tối thiểu | Xuất được MDG+CHG cho ≥1 app (không thì lùi về PHPJoern) | ✅ |
| 1 | 3–8 | Dataset xuyên mô-đun | ≥150 mẫu dương / ~3 CWE + mẫu âm | ✅ (977 mẫu / 13 CWE) |
| 2 | 9–16 | Slicing → linearize → QLoRA | Thắng baseline no-slice / intra-file ở F1·PR-AUC | 🟡 **một phần** (corpus test xong; CHƯA train) |
| 3 | 17–22 | Ablation MDG/CHG + robustness + so sánh | Bỏ MDG/CHG ⇒ **giảm đáng kể** khả năng phát hiện | 🟠 |
| 4 | 23–26 | Viết báo cáo + công bố | Nộp hội nghị + công khai code/slice/split tái lập | ⬜ |

---

## GĐ0 — Khả thi & rủi ro công cụ (Tuần 1–2) ✅
Exporter MDG (phụ thuộc mô-đun) + CHG (phân cấp lớp) đã có ở `exporter/` (graph_builder.py,
php_parser.py). Không phải lùi về PHPJoern.

## GĐ1 — Benchmark xuyên mô-đun (Tuần 3–8) ✅
977 mẫu dương tính xuyên mô-đun / 13 CWE (mỗi mẫu kèm mẫu âm = code sau vá).
→ `build/dataset_xmodule/` · `build/METHODOLOGY.md` · `build/VERIFY.md` · `build/dataset_xmodule/STATS.md`

## GĐ2 — Pipeline + huấn luyện (Tuần 9–16) 🟡 MỘT PHẦN (corpus test xong; CHƯA train)
**Đã chạy thật trên Linux:** B1/B2/B3 đã sửa & xác minh trên E-CPG sống; corpus đã sinh cho
**riêng split=test** → `build/ft_dataset.jsonl.gz` (15 786 dòng = 3 variant × 5 262 seed;
89/144 mẫu xong, 55 bỏ do OOM RAM). Chi tiết + giới hạn: `build/FT_DATASET_README.md`,
`build/THREATS_TO_VALIDITY.md`.
- B1 source/sink/sanitizer (đối chiếu NAVEX+TChecker): `api-framework/apis/vuln_model.py` · `build/SOURCES_SINKS_XCHECK.md`
- B2 cắt lát ngược qua MDG/CHG: `api-framework/apis/backward_slice.py` · `build/SLICING.md`
- B3 hybrid linearization: `api-framework/apis/linearize.py` · `build/LINEARIZATION.md`
- B4 QLoRA Qwen2.5-Coder + F1/PR-AUC: `build/qlora_train_eval.py`

**CÒN THIẾU để đạt mốc "thắng baseline":**
1. **Sinh corpus train + val** (`run_phase2.py --split train`, `--split val`) — hiện `qlora_train_eval.py`
   train trên `split=="train"` mà corpus test-only ⇒ **train = 0 dòng, chưa train được**. Cần máy
   nhiều RAM hơn (box 3.9GB bỏ 38% mẫu test) + GPU.
2. **Train QLoRA + eval** trên GPU → F1/PR-AUC theo variant.
- Tín hiệu đã lộ *trước khi train*: intra-file chỉ 104 positive vs cross-module 210 (một nửa) —
  đúng giả thuyết, thấy ngay trong dữ liệu.
- Chạy: `build/env_setup.sh` → `build/SMOKE_TEST.md` → `build/run_phase2.py` → `qlora_train_eval.py`
- **Cần**: toolchain E-CPG (PHP8+Java11+Neo4j 4.4.4) + GPU.

## GĐ3 — Ablation / Robustness / So sánh (Tuần 17–22) 🟠 (plan + stub, CHƯA chạy)
- **Ablation** (cốt lõi chứng minh tính mới): bỏ MDG và/hoặc CHG phải làm **giảm đáng kể** khả
  năng phát hiện trên tập xuyên mô-đun. Cờ: `disable_include`/`disable_inherit`/
  `with_control_context` (backward_slice.py), `include_edges` (linearize.py), variant
  (qlora_train_eval.py).
- **Robustness**: `build/perturb.py` (đổi tên biến, dead code, thêm lớp include…) → đo consistency.
- **So sánh**: đối thủ theo plan = **RealVul, VulEye, DeepTective, và phân tích tĩnh của PHPJoy**;
  chấm ở mức mẫu bằng `build/eval_external.py`. (NAVEX/TChecker thuộc GĐ2, không phải đối thủ GĐ3.)
- Kế hoạch đầy đủ + tiêu chí + kiểm định (bootstrap CI, McNemar): `build/PHASE3_PLAN.md`.

## GĐ4 — Viết báo cáo & Công bố (Tuần 23–26) ⬜ (chưa bắt đầu)
- Viết luận văn (Intro / Related work / Method / Evaluation / Discussion / Conclusion) + threats
  to validity → **đã có `build/THREATS_TO_VALIDITY.md`** (ghi nhận từ lần chạy thật GĐ2: giới hạn
  sink model XSS, 19/144 mẫu mất do lỗi `phpast2cpg.jar`/RAM, dedup `ft_dataset.jsonl`).
- Nhắm hội nghị: **ISSTA, ASE, ICSE, USENIX Security, EMNLP-Findings**.
- Công khai để tái lập: code + đoạn slice + cách chia train/val/test.
  → Một phần đã có: repo công khai (github.com/KeyboardRules/Master-Thesis) với code + `splits.json`.
  Còn thiếu: bản thảo luận văn, `ft_dataset.jsonl` (sinh ở GĐ2), và trang README hướng dẫn tái lập.

---

**Việc kế tiếp theo đúng lộ trình:** thực thi GĐ2 (mốc "thắng baseline") → GĐ3 (ablation là điểm
mới) → GĐ4 (viết + công bố). Xem `KE_HOACH_TIEP_QUAN.md` cho prompt bắt đầu GĐ2 trên Linux.
