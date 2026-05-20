# Phone right-axis layout fix

- Moved all y-axis tick labels to the right side.
- Moved y-axis labels (`Price`, `cum ΔCVD`) to the right side.
- Hid the left spine to free the left edge for chart body scanning on phones.
- Kept canvas size at 1280x1920.
- Layout marker: `phone_portrait_wide_endpoint_labels_cum_delta_v6`.


## endpoint labels v6
- 従来の凡例を廃止。
- 各ラインの最新値付近、チャート右端の内側に、同色のシンボル名ラベルを直接表示。
- 縦軸は右側のまま維持。
- 実行時表示: `layout=phone_portrait_wide_endpoint_labels_cum_delta_v6`
