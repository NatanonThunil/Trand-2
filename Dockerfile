# ใช้ Python 3.10-slim (เสถียรสุด)
FROM python:3.10-slim

# ตั้งค่า Timezone
ENV TZ=Asia/Bangkok

# ✅ ลง git (จำเป็นมากสำหรับการโหลด tvDatafeed)
RUN apt-get update && apt-get install -y tzdata git && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# สร้างโฟลเดอร์ทำงาน
WORKDIR /app

# ก๊อปปี้ไฟล์ requirements
COPY requirements.txt .

# อัปเกรด pip
RUN pip install --upgrade pip

# ติดตั้ง Library (จะใช้ git clone อัตโนมัติ)
RUN pip install --no-cache-dir -r requirements.txt

# ก๊อปปี้โค้ดทั้งหมด
COPY . .

# สร้างโฟลเดอร์ charts
RUN mkdir -p charts

# คำสั่งรันบอท
CMD ["python", "bot.py"]