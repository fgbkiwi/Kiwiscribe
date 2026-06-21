import os
import sys

from PIL import Image


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "KiwiScribeSquared.png"
    dst = sys.argv[2] if len(sys.argv) > 2 else "KiwiScribeSquared.ico"

    if not os.path.exists(src):
        raise FileNotFoundError(f"Imagem de origem nao encontrada: {src}")

    with Image.open(src) as img:
        rgba = img.convert("RGBA")
        sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        rgba.save(dst, format="ICO", sizes=sizes)

    print(f"Icone gerado com sucesso: {dst}")


if __name__ == "__main__":
    main()