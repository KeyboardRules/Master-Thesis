# NEXT STEPS — trạng thái thật & việc kế tiếp (cập nhật 2026-09-15)

> File này ghi trạng thái SAU khi đã chạy thật GĐ2 một phần trên Linux. Nếu mở phiên Claude Code
> mới, đọc file này TRƯỚC `HANDOFF.md` (HANDOFF viết khi chưa chạy gì, nay đã lỗi thời).

## Đang ở đâu (GĐ2 — một phần)
- ✅ Pipeline B2 (backward_slice) + B3 (linearize) đã **sửa & chạy thật** trên E-CPG sống; các
  bug + giới hạn ghi trong `build/THREATS_TO_VALIDITY.md`.
- ✅ Corpus đã sinh **CHỈ cho split=test**: `build/ft_dataset.jsonl.gz` (15 786 dòng = 3 variant ×
  5 262 seed). Provenance: `build/FT_DATASET_README.md`.
- ❌ **CHƯA train**, và không train được ngay: `build/qlora_train_eval.py` train trên `split=="train"`,
  mà corpus hiện test-only ⇒ train = 0 dòng (script nay báo lỗi rõ nếu chạy thiếu train).
- 📌 Tín hiệu tiền-huấn-luyện: intra-file 104 positive vs cross-module 210 (một nửa) — đúng giả thuyết.

## Việc kế tiếp (để đạt mốc GĐ2 "thắng baseline")

### Bước 1 — Sinh corpus TRAIN + VAL (phạm vi small/medium → CHẠY ĐƯỢC trên box 3.9GB)
**Phạm vi đã chốt = small/medium PHP (b).** Dùng cổng `--max-php-kb` để loại repo lớn *trước khi*
build E-CPG → không còn OOM, không cần máy mạnh hơn. Chọn ngưỡng từ dữ liệu (nằm giữa repo
in-scope lớn nhất và repo retired nhỏ nhất; xem danh sách retired ở THREATS §3).
```bash
cd phpjoy_release && . .venv/bin/activate
# 0) chọn ngưỡng: đo KB .php của repo đã xong (in-scope) vs bị retired để tách 2 nhóm.
# 1) khôi phục corpus test đã có (run_phase2 ghi APPEND vào cùng file):
gunzip -c build/ft_dataset.jsonl.gz > build/ft_dataset.jsonl
# 2) sinh train/val với cổng phạm vi (ví dụ 30000 KB; TINH CHỈNH theo bước 0):
python build/run_phase2.py --split train --max-php-kb 30000   # resume trong phase2_state.json
python build/run_phase2.py --split val   --max-php-kb 30000
```
Mẫu bị loại a-priori ghi ở `build/phase2_out_of_scope.json` (khác với retired-do-lỗi). Sau đó
`build/ft_dataset.jsonl` có đủ 3 split. (Nén lại để commit: `gzip -k build/ft_dataset.jsonl`.)

### Bước 2 — Train QLoRA + đánh giá (bước DUY NHẤT cần GPU)
VM chỉ-CPU không train được. Bước này tự chứa (chỉ cần `ft_dataset.jsonl`) → đẩy lên **GPU đám mây
miễn phí** (Kaggle/Colab). Xem **`build/qlora_cloud.md`** (đủ lệnh + chọn cỡ model). Tóm tắt:
```bash
# trên GPU đám mây, sau khi clone repo + gunzip corpus:
pip install "transformers>=4.44" peft bitsandbytes datasets accelerate scikit-learn
python build/qlora_train_eval.py --data build/ft_dataset.jsonl \
       --model Qwen/Qwen2.5-Coder-1.5B-Instruct   # 1.5B hợp corpus nhỏ; script tự chọn fp16 trên T4
```
**Tuân THREATS khi báo số:** score trên file RAW (KHÔNG dedup — dedup làm no-slice sụp ~5×);
báo **PR-AUC** + positive rate cạnh F1; giữ 3 variant paired. Mốc: cross-module > intra-file > no-slice.

### Bước 3 — GĐ3 (ablation / robustness / so sánh)
Theo `build/PHASE3_PLAN.md`: cờ `disable_include`/`disable_inherit` (backward_slice), `include_edges`
(linearize), variant; `build/perturb.py`; so sánh RealVul/VulEye/DeepTective/PHPJoy-static qua `build/eval_external.py`.

## Quyết định phạm vi — ĐÃ CHỐT: (b) small/medium PHP projects
Không cần máy mạnh hơn. Repo lớn được loại *có chủ đích* bằng `--max-php-kb` (a-priori, trước khi
build E-CPG), ghi ở `phase2_out_of_scope.json`. Trong luận văn: nêu rõ kết quả áp dụng cho dự án
PHP nhỏ/vừa; hành vi trên codebase doanh nghiệp cực lớn **không được đánh giá** (THREATS §3, đã
cập nhật thành "scope decision"). Báo cáo ngưỡng KB đã dùng + số mẫu in-scope / out-of-scope.

---

## Prompt tiếp quản (dán vào Claude Code trên Linux, trong thư mục repo)

```
Đọc NEXT_STEPS.md, ROADMAP.md và build/THREATS_TO_VALIDITY.md. GĐ2 đã chạy một phần: pipeline
đã sửa & corpus split=test đã sinh, NHƯNG chưa có corpus train/val nên chưa train được. Nhiệm vụ:

1. Phạm vi đã chốt = small/medium PHP: chọn ngưỡng `--max-php-kb` từ dữ liệu (đo KB .php của
   repo đã-xong vs retired để tách 2 nhóm), rồi `gunzip -c build/ft_dataset.jsonl.gz >
   build/ft_dataset.jsonl` và `python build/run_phase2.py --split train --max-php-kb <N>` và
   `--split val --max-php-kb <N>` (có resume; repo lớn tự loại a-priori, không OOM). Báo cáo
   ngưỡng đã chọn + số in-scope/out-of-scope + retired theo repo/CWE. DỪNG cho tôi duyệt trước
   khi chạy toàn bộ.
2. Sau khi có đủ 3 split: `python build/qlora_train_eval.py --data build/ft_dataset.jsonl
   --model Qwen/Qwen2.5-Coder-7B-Instruct` (cần GPU). Báo F1/PR-AUC theo variant. Tuân THREATS:
   score trên file RAW, KHÔNG dedup, báo PR-AUC + positive rate.
3. Rồi mới sang GĐ3 (build/PHASE3_PLAN.md).

Quy tắc: chạy từ gốc repo với `. .venv/bin/activate`; báo cáo diff mọi thay đổi code; không
commit/push nếu tôi chưa yêu cầu.
```
