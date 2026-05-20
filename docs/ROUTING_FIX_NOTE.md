# Routing fix note

この版では経路を整理済み。

- ZIP直下に `cvd_monitor/` を配置。前版のような `cvd_phone/cvd_monitor/` ネストを廃止。
- `python -m cvd_monitor ...` がこの同梱コードを直接読む構成。
- `renderer.py` の `LAYOUT_VERSION` は `phone_portrait_cum_delta_v2`。
- CLI出力に `layout=phone_portrait_cum_delta_v2` と `renderer=<実際に読んだcli.py>` を表示。
- `out/` から古い横長PNGを削除。同梱するPNGは縦長のみ。

実行時に `layout=phone_portrait_cum_delta_v2` が出ない場合、古いフォルダ/古いインストール済みパッケージを実行している。
その場合はこのZIPを空フォルダへ展開し、ZIP直下で実行する。
