# ใช้ Python 3.10-slim
FROM python:3.10-slim

# ตั้งค่า Timezone เป็นไทย
ENV TZ=Asia/Bangkok

# ลง git, tzdata และเคลียร์ cache เพื่อลดขนาด image
RUN apt-get update && apt-get install -y tzdata git && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
    rm -rf /var/lib/apt/lists/*

# สร้างโฟลเดอร์ทำงาน
WORKDIR /app

# ก๊อปปี้ไฟล์ requirements และติดตั้ง
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ก๊อปปี้โค้ดทั้งหมด
COPY . .

# สร้างโฟลเดอร์ที่จำเป็น (charts และ data)
RUN mkdir -p charts data

# ==========================================
# ✅ ส่วนที่เพิ่มเพื่อแก้ CKV_DOCKER_3
# ==========================================

# 1. สร้าง User ใหม่ที่ไม่ใช่ Root (ชื่อ appuser ID 10014)
RUN groupadd -r appuser && useradd -r -g appuser -u 10014 appuser

# 2. เปลี่ยนเจ้าของโฟลเดอร์ /app ให้เป็นของ appuser (เพื่อให้เขียนไฟล์ลง data/charts ได้)
RUN chown -R appuser:appuser /app

# 3. สลับไปใช้ User นี้แทน Root
USER 10014

# ==========================================

# คำสั่งรันบอท
CMD ["python", "bot.py"]