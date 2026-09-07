import io

import qrcode
from aiogram.types import BufferedInputFile


def make_qr(data: str) -> BufferedInputFile:
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return BufferedInputFile(buf.read(), filename="subscription_qr.png")
