# Kế hoạch tiếp quản Giai đoạn 2 (tiếng Việt)

File này để dùng khi mở lại project trên một máy Linux mới. Gồm 2 phần: (A) tổng quan trạng
thái & kế hoạch, (B) prompt dán thẳng vào Claude Code để AI tiếp quản.

---

## A. Trạng thái & kế hoạch

**Dự án:** phát hiện lỗ hổng PHP *xuyên mô-đun* bằng Enhanced Code Property Graph (E-CPG) +
LLM. Đồ án thạc sĩ.

**Đã xong (thật):**
- Giai đoạn 1 — Bộ dữ liệu: **977 mẫu dương tính xuyên mô-đun / 13 CWE**, mỗi mẫu kèm mẫu âm
  tính (code sau vá). Nằm ở `build/dataset_xmodule/` (`index.json`, `splits.json` = chia
  train/val/test theo repo chống rò rỉ, và `meta.json` mỗi mẫu: repo/fix_commit/cwe/changed_php).

**Đã viết code nhưng CHƯA chạy (cần toolchain E-CPG + GPU):**
- `api-framework/apis/vuln_model.py` — model source/sink/sanitizer đã vá (`.bak` là bản gốc).
- `api-framework/apis/backward_slice.py` — B2: cắt lát taint ngược qua PDG/CG + MDG(INCLUDE)/
  CHG(EXTENDS,TRAIT); có cờ ablation `disable_include`/`disable_inherit`/`with_control_context`.
- `api-framework/apis/linearize.py` — B3: Slice → chuỗi hybrid; `build_ft_dataset` → `ft_dataset.jsonl`.
- `build/qlora_train_eval.py` — B4: QLoRA Qwen2.5-Coder + tính F1/PR-AUC theo variant.
- `build/perturb.py`, `build/eval_external.py` — Giai đoạn 3 (robustness + so sánh tool ngoài).
- `build/run_phase2.py` — driver batch; `build/env_setup.sh` — cài toolchain Ubuntu/WSL.

**Kế hoạch thực thi (thứ tự):**
1. Cài toolchain: `bash build/env_setup.sh`, đặt mật khẩu Neo4j = 123.
2. Smoke test 1 mẫu (`build/SMOKE_TEST.md`) để xác nhận cả chuỗi chạy.
3. Sửa các điểm `# VERIFY` (trong `backward_slice.py`) và `# ADJUST` (trong `run_phase2.py`)
   cho khớp graph Neo4j thật, tới khi `run_phase2.py --limit 1` ghi được dòng vào `ft_dataset.jsonl`.
4. Chạy batch: `run_phase2.py --split test` → `ft_dataset.jsonl` (3 variant/seed).
5. Fine-tune + đánh giá: `qlora_train_eval.py` (cần GPU).

**Tiêu chí đạt:** variant `cross-module` phải thắng `intra-file` và `no-slice` ở F1 và PR-AUC.

**Không nằm trong repo (tự tạo lại):** Neo4j/PHP/Java/venv (do `env_setup.sh` lo); `build/packagist/`
(dump OSV thô — chỉ cần khi harvest lại dataset, không cần để chạy lại Giai đoạn 2).

---

## B. Prompt tiếp quản — dán vào Claude Code trên Linux (đang ở trong thư mục repo)

```
Đọc HANDOFF.md, rồi build/METHODOLOGY.md, build/SMOKE_TEST.md và build/PHASE2_README.md.

Bạn đang tiếp quản việc THỰC THI Giai đoạn 2 của đồ án này (phát hiện lỗ hổng PHP xuyên
mô-đun bằng E-CPG). Toàn bộ code đã viết xong nhưng CHƯA từng chạy vì các máy trước không có
toolchain; máy Linux này thì có. Hãy làm theo đúng thứ tự:

1. Cài toolchain: chạy `bash build/env_setup.sh`, rồi đặt mật khẩu Neo4j = 123.

2. SMOKE TEST trên ĐÚNG 1 mẫu (theo build/SMOKE_TEST.md): dựng E-CPG cho tutorial/example,
   import vào Neo4j, chạy `cd tutorial && python main.py -1 example -vt 9` (kỳ vọng in
   "find N taint path"), rồi `python smoke_slice.py -1 example -vt 9` (kỳ vọng >=1 slice + một
   bản linearization hybrid).

3. SỬA các điểm tích hợp trên graph THẬT — đây chính là lý do cần bạn ở máy có Neo4j:
   - Các chỗ `# VERIFY` trong api-framework/apis/backward_slice.py (chữ ký match_relationship,
     fig_step.get_toplevel_file_first_statement, get_ast_root_node có trả về class của method
     không, find_cg_call_nodes với get_node_itself(funcid)). Xem SMOKE_TEST.md bước 7.
   - Các chỗ `# ADJUST` trong build/run_phase2.py (tên file output của Parser.php, cách gọi
     neo4j-admin-import.sh, cấp phát port/db).
   Mục tiêu: `python build/run_phase2.py --limit 1` chạy được và ghi được dòng vào
   build/ft_dataset.jsonl.

4. Chạy cả tập: `python build/run_phase2.py --split test` (có checkpoint/resume) để sinh
   build/ft_dataset.jsonl, mỗi seed xuất 3 biến thể (cross-module / intra-file / no-slice).

5. Fine-tune + đánh giá (cần GPU): `python build/qlora_train_eval.py --data
   build/ft_dataset.jsonl --model Qwen/Qwen2.5-Coder-7B-Instruct`. Nếu máy không có GPU, đẩy
   build/ft_dataset.jsonl sang GPU đám mây để chạy.

Tiêu chí đạt: biến thể cross-module phải THẮNG intra-file và no-slice ở F1 và PR-AUC
(qlora_train_eval.py in kết quả theo từng variant/CWE).

Lưu ý: chạy mọi thứ từ thư mục gốc repo với `. .venv/bin/activate` (trừ main.py và
smoke_slice.py chạy trong tutorial/). Bỏ qua các đường dẫn trong build/PACKAGE_INDEX.md (đó là
layout của gói zip, không phải repo này) — code thật nằm ở api-framework/apis/ và build/.

QUAN TRỌNG: Ở bước 3 bạn sẽ phải thực sự SỬA code (không chạy trơn ngay được, vì slicer/driver
chưa từng chạy trên graph thật). Hãy BÁO CÁO rõ từng thay đổi (diff) và DỪNG chờ tôi duyệt
trước khi chạy batch đầy đủ ở bước 4.
```
