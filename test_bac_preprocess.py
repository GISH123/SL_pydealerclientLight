# encoding=utf-8
"""Regression test for BAC Crop Tool-compatible preprocessing.

This test extracts the actual VideoManager method from videomanager.py by AST,
so it does not import the complete application or require config.xml,
models/videolist.xml, Twisted, dealer connections, or the model API.
"""

from __future__ import annotations

import ast
from pathlib import Path

import cv2
import numpy as np


TARGET_W = 150
TARGET_H = 100
METHOD_NAME = "_bac_keep_ratio_resize_center_pad"


def load_actual_method():
    source_path = Path(__file__).with_name("videomanager.py")
    source = source_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(source_path))

    method_node = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "VideoManager":
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name == METHOD_NAME:
                        method_node = item
                        break
        if method_node is not None:
            break

    if method_node is None:
        raise RuntimeError(
            f"{METHOD_NAME} was not found in {source_path.name}"
        )

    # Turn the class method into a temporary module-level function.
    extracted = ast.FunctionDef(
        name=method_node.name,
        args=method_node.args,
        body=method_node.body,
        decorator_list=[],
        returns=method_node.returns,
        type_comment=method_node.type_comment,
    )
    module = ast.Module(body=[extracted], type_ignores=[])
    ast.fix_missing_locations(module)

    namespace = {"cv2": cv2}
    exec(
        compile(module, filename=str(source_path), mode="exec"),
        namespace,
        namespace,
    )
    return namespace[METHOD_NAME]


def make_test_image(width: int, height: int) -> np.ndarray:
    """Create a non-uniform image so BORDER_REPLICATE can be checked."""
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :, 0] = np.arange(width, dtype=np.uint8)[None, :]
    image[:, :, 1] = np.arange(height, dtype=np.uint8)[:, None]
    image[:, :, 2] = 127
    return image


def run_case(method, original_w: int, original_h: int) -> None:
    source = make_test_image(original_w, original_h)
    dummy_self = object()

    output, meta = method(
        dummy_self,
        source,
        TARGET_W,
        TARGET_H,
    )

    output_h, output_w = output.shape[:2]
    assert (output_w, output_h) == (TARGET_W, TARGET_H), (
        f"original W:H={original_w}:{original_h} produced "
        f"W:H={output_w}:{output_h}"
    )

    resized_w, resized_h = meta["resized_wh"]
    pad_left, pad_top, pad_right, pad_bottom = meta["pad_ltrb"]

    assert resized_w + pad_left + pad_right == TARGET_W
    assert resized_h + pad_top + pad_bottom == TARGET_H
    assert meta["engine_wh"] == (TARGET_W, TARGET_H)
    assert meta["mode"] == "keep_ratio_center_pad"
    assert meta["original_wh"] == (original_w, original_h)
    assert meta["scale"] > 0

    # A fitted image must touch at least one target boundary before padding.
    assert resized_w == TARGET_W or resized_h == TARGET_H

    print(
        f"PASS original W:H={original_w}:{original_h} "
        f"-> resized W:H={resized_w}:{resized_h} "
        f"-> pad L:T:R:B="
        f"{pad_left}:{pad_top}:{pad_right}:{pad_bottom} "
        f"-> engine W:H={output_w}:{output_h}"
    )


def main() -> None:
    method = load_actual_method()

    cases = [
        (150, 100),  # already exact
        (146, 108),  # current real-world example
        (80, 60),    # smaller than target
        (50, 50),    # square
        (300, 200),  # larger, already 3:2
        (200, 80),   # wide
        (80, 200),   # tall
        (1, 1),      # smallest valid image
    ]

    for original_w, original_h in cases:
        run_case(method, original_w, original_h)

    print("ALL BAC PREPROCESS TESTS PASSED")


if __name__ == "__main__":
    main()
