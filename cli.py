import argparse
import asyncio
import os
from core import OopsNote
from models import Request

async def main():
    parser = argparse.ArgumentParser(description="OopsNote 命令行模式")
    parser.add_argument('paths', nargs='+', help='图片文件或目录')
    parser.add_argument('-p', '--prompt', default='', help='附加描述')
    args = parser.parse_args()

    note = OopsNote(enable_bot=False)

    images = []
    for p in args.paths:
        if os.path.isdir(p):
            for fname in os.listdir(p):
                if fname.lower().endswith(('.jpg', '.jpeg', '.png')):
                    images.append(os.path.join(p, fname))
        else:
            images.append(p)

    for img in images:
        with open(img, 'rb') as f:
            await note.queue.put(Request(image=f.read(), image_path=img, prompt=args.prompt))

    await note.launch()

if __name__ == '__main__':
    asyncio.run(main())
