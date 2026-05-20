# Clean-root package note

このZIPはレガシー混在を避けるため、ZIP直下に `cvd_monitor/`, `config/`, `tests/` を置いた clean-root 構成です。

古いレイアウトが出る典型原因:

1. 旧フォルダへ上書きせず、ネストされたフォルダだけ展開している
2. 既存の `cvd_monitor/` が残っていて、Python がそちらを import している
3. pip install 済みの古い `cvd_monitor` を読んでいる
4. 実行ディレクトリがZIP展開先ではない

確認:

```bash
python VERIFY_RUNTIME.py
```

期待値:

```text
layout=phone_portrait_wide_label_margin_24h_rolling_cum_delta_v12_cleanroot
```

推奨実行:

```bash
./RUN_THIS_PHONE_RENDER.sh
```

このスクリプトは自分の配置場所へ `cd` し、`PYTHONPATH` にZIP展開先を先頭追加するため、古いインストール済みパッケージを踏みにくくしています。
