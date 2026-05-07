FROM python:3.11-slim

ENV TZ=Asia/Shanghai
ENV LANG=zh_CN.UTF-8
ENV LANGUAGE=zh_CN:zh

# 清理所有旧源并使用阿里云镜像
RUN rm -f /etc/apt/sources.list /etc/apt/sources.list.d/*.sources /etc/apt/sources.list.d/*.list \
    && echo 'deb https://mirrors.aliyun.com/debian/ bookworm main' > /etc/apt/sources.list \
    && echo 'deb https://mirrors.aliyun.com/debian-security bookworm-security main' >> /etc/apt/sources.list \
    && echo 'deb https://mirrors.aliyun.com/debian/ bookworm-updates main' >> /etc/apt/sources.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    wget fonts-wqy-zenhei libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt \
    && playwright install chromium

COPY . .
RUN mkdir -p /app/data

EXPOSE 8000
CMD ["python", "-m", "app.main"]
