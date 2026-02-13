FROM python:3.10-slim

# ตั้งค่า Timezone
ENV TZ=Asia/Bangkok

# ตั้งค่า Cache ของ Matplotlib ให้ไปลง /tmp
ENV MPLCONFIGDIR=/tmp/matplotlib

# ลง git และ tzdata
RUN apt-get update && apt-get install -y tzdata git && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# ✅ 1. สร้าง User ใหม่ชื่อ 'appuser' (UID 10014) ตามที่ระบบแนะนำ
RUN groupadd -g 10014 appuser && \
    useradd -m -u 10014 -g appuser appuser

WORKDIR /app

# ก๊อปปี้และติดตั้ง Library (ทำในฐานะ Root ก่อน)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# ✅ 2. สร้างโฟลเดอร์ใน /tmp และกำหนดสิทธิ์ให้ User 10014 เป็นเจ้าของ
# ต้องลบโฟลเดอร์ data/charts เดิมใน /app (ถ้ามี) แล้วทำ Symlink ใหม่
RUN rm -rf /app/data /app/charts && \
    mkdir -p /tmp/charts /tmp/data /tmp/matplotlib && \
    ln -s /tmp/charts /app/charts && \
    ln -s /tmp/data /app/data && \
    # เปลี่ยนเจ้าของไฟล์ทั้งหมดให้เป็น User 10014
    chown -R 10014:10014 /app /tmp/charts /tmp/data /tmp/matplotlib

# ✅ 3. สลับไปใช้ User 10014 ในการรัน (ผ่าน Checkov แน่นอน)
USER 10014

CMD ["python", "bot.py"]