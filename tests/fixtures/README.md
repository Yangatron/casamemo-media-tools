# Synthetic fixtures

These files contain only generated pixels. The images use four solid colour quadrants created as RGB PNGs and converted with macOS Image I/O via `sips`. `still.heic` and `still.avif` are 64 × 48. `tiled.heic` is 1024 × 768. `local-video.mp4` contains six 64 × 48 frames of a generated RGB gradient, encoded to H.264 by AVFoundation. The MP4 creation and modification timestamps are zeroed. They are available under this repository's MIT licence.

The test generates its PNG, JPEG orientation, ICC, TIFF and WebP inputs in a temporary directory. Do not replace these fixtures with private media.
