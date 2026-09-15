# Chạy bước GPU (QLoRA train + eval) khi VM không có GPU

VM Linux của bạn (chỉ CPU) làm được **gần như toàn bộ**; chỉ **một** bước cần GPU.

| Bước | Cần GPU? | Chạy ở đâu |
|---|---|---|
| Sinh corpus (`run_phase2.py`), ablation slicing, `perturb.py`, `eval_external.py` | ❌ Không | VM CPU của bạn |
| **Train QLoRA + chấm F1/PR-AUC (`qlora_train_eval.py`)** | ✅ Có | GPU đám mây |

Bước GPU **tự chứa**: nó chỉ cần **`build/ft_dataset.jsonl`** + `build/qlora_train_eval.py`. Nên
quy trình là: sinh corpus trên VM → đẩy file lên GitHub (nén) → kéo về máy GPU đám mây → chạy 1 lệnh
→ mang bảng F1/PR-AUC (vài dòng text) về.

## Chọn GPU đám mây (miễn phí trước)
| Dịch vụ | GPU | Giá | Ghi chú |
|---|---|---|---|
| **Kaggle Notebooks** | T4×2 / P100 16GB | **Miễn phí** 30h/tuần | Khuyến nghị — nhiều giờ, ổn định |
| Google Colab | T4 16GB | Miễn phí (giới hạn) | Nhanh gọn; Pro có L4/A100 |
| RunPod / Vast.ai / Lambda | 24GB (Ampere) | ~$0.2–0.5/giờ | Khi cần nhanh/mạnh hơn |

`qlora_train_eval.py` **tự chọn fp16 trên T4/P100** (Turing/Pascal không có bf16) và bf16 trên
Ampere+ — không cần chỉnh tay.

> **Cách nhanh nhất trên Kaggle:** tải lên notebook sẵn **`build/qlora_kaggle.ipynb`** (Kaggle →
> Create → Notebook → File → Upload), bật GPU + Internet, bấm Run All. Các ô đã lo clone, cài đặt,
> kiểm tra split, train và in bảng F1/PR-AUC.

## Chọn cỡ model
Corpus nhỏ (small/medium scope) → **`Qwen/Qwen2.5-Coder-1.5B-Instruct`** là hợp lý nhất: vừa T4
16GB thoải mái, train nhanh, **ít overfit** hơn 7B trên ~vài trăm–nghìn positive. 7B vẫn chạy được
trên T4 (4-bit) nhưng chật và chậm. Có thể chạy cả hai cỡ để so (ablation A6).

## Quy trình

### 1) Trên VM: sinh corpus đủ 3 split rồi đẩy lên GitHub
```bash
cd phpjoy_release && . .venv/bin/activate
gunzip -c build/ft_dataset.jsonl.gz > build/ft_dataset.jsonl
python build/run_phase2.py --split train --max-php-kb <N>
python build/run_phase2.py --split val   --max-php-kb <N>
gzip -kf build/ft_dataset.jsonl                 # -> build/ft_dataset.jsonl.gz (nén để commit)
git add build/ft_dataset.jsonl.gz build/phase2_*.json && git commit -m "train/val corpus" && git push
```

### 2) Trên Kaggle/Colab (GPU): kéo repo + chạy
```bash
git clone https://github.com/KeyboardRules/Master-Thesis.git && cd Master-Thesis
pip -q install "transformers>=4.44" peft bitsandbytes datasets accelerate scikit-learn
gunzip -c build/ft_dataset.jsonl.gz > build/ft_dataset.jsonl
python build/qlora_train_eval.py \
       --data build/ft_dataset.jsonl \
       --model Qwen/Qwen2.5-Coder-1.5B-Instruct \
       --output out
```
Script sẽ: fine-tune (LoRA adapter lưu ở `out/adapter`) rồi **in bảng F1 / PR-AUC theo variant &
CWE**. Chỉ cần copy bảng đó về.

> Repo private? Trên Kaggle/Colab đăng nhập bằng Personal Access Token:
> `git clone https://<TOKEN>@github.com/KeyboardRules/Master-Thesis.git`

### 3) Chỉ chấm điểm lại (không train lại)
```bash
python build/qlora_train_eval.py --data build/ft_dataset.jsonl --adapter out/adapter --eval_only \
       --model Qwen/Qwen2.5-Coder-1.5B-Instruct
```

## Tuân THREATS khi báo số (bắt buộc)
- Chấm trên file **RAW**, **KHÔNG dedup** (dedup làm no-slice sụp ~5×, phá seed pairing).
- Báo **PR-AUC** + positive rate cạnh F1; giữ 3 variant paired.
- Mốc đạt: `cross-module` > `intra-file` **và** > `no-slice`.

## Nếu hoàn toàn không có GPU nào
Có thể chạy CPU với model rất nhỏ (`Qwen2.5-Coder-0.5B`) **không** dùng 4-bit (`bitsandbytes` cần
CUDA) — rất chậm và kết quả yếu, chỉ để smoke-test đường ống, **không dùng cho số liệu luận văn**.
Thực tế nên dùng Kaggle/Colab miễn phí ở trên.
