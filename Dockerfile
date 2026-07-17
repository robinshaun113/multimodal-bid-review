FROM python:3.11-slim

WORKDIR /app

# 系统依赖：Pillow 处理图像需要 libjpeg/zlib（slim 基础镜像缺）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY checklist.yaml .
COPY app.py .

# DASHSCOPE_API_KEY 运行时经 -e 注入，绝不打进镜像
ENV GRADIO_SERVER_NAME=0.0.0.0
EXPOSE 7860

CMD ["python", "app.py"]
