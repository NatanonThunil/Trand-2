FROM python:3.10-slim

# ตั้งค่า Timezone
ENV TZ=Asia/Bangkok

# ✅ ตั้งค่า Cache ของ Matplotlib ให้ไปลง /tmp (แก้ปัญหา Read-only)
ENV MPLCONFIGDIR=/tmp/matplotlib

# ลง git และ tzdata
RUN apt-get update && apt-get install -y tzdata git && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ✅ ต้องมีบรรทัดนี้ ไม่งั้น /signal จะ Error เพราะเขียนไฟล์ไม่ได้
RUN mkdir -p /tmp/charts /tmp/data /tmp/matplotlib && \
    ln -s /tmp/charts /app/charts && \
    ln -s /tmp/data /app/data

# ปรับสิทธิ์ (เผื่อไว้)
RUN chmod -R 777 /tmp

CMD ["python", "bot.py"]