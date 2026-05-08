# ============================================================
# Stage 1: 安装依赖（requirements.txt 不变时，这层会被 Docker 缓存）
# ============================================================
FROM docker.m.daocloud.io/library/python:3.11-slim AS builder

ENV TZ=Asia/Shanghai
ENV LANG=zh_CN.UTF-8
ENV LANGUAGE=zh_CN:zh

# 装系统依赖（浏览器需要的库）
RUN rm -f /etc/apt/sources.list /etc/apt/sources.list.d/*.sources /etc/apt/sources.list.d/*.list \
    && echo 'deb https://mirrors.aliyun.com/debian/ bookworm main' > /etc/apt/sources.list \
    && echo 'deb https://mirrors.aliyun.com/debian-security bookworm-security main' >> /etc/apt/sources.list \
    && echo 'deb https://mirrors.aliyun.com/debian/ bookworm-updates main' >> /etc/apt/sources.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    wget fonts-wqy-zenhei libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先只 COPY requirements.txt，安装依赖（这行不改则依赖层始终命中缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

# Playwright 浏览器单独装（变化极少，缓存命中后跳过）
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ playwright \
    && playwright install chromium

# ============================================================
# Stage 2: 运行镜像（依赖和浏览器都从 builder copy，只跑代码层）
# ============================================================
FROM docker.m.daocloud.io/library/python:3.11-slim

ENV TZ=Asia/Shanghai
ENV LANG=zh_CN.UTF-8
ENV LANGUAGE=zh_CN:zh

RUN rm -f /etc/apt/sources.list /etc/apt/sources.list.d/*.sources /etc/apt/sources.list.d/*.list \
    && echo 'deb https://mirrors.aliyun.com/debian/ bookworm main' > /etc/apt/sources.list \
    && echo 'deb https://mirrors.aliyun.com/debian-security bookworm-security main' >> /etc/apt/sources.list \
    && echo 'deb https://mirrors.aliyun.com/debian/ bookworm-updates main' >> /etc/apt/sources.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    fonts-wqy-zenhei libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 从 builder 复制已安装的 Python 包和 Playwright 浏览器
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /root/.cache/ms-playwright /root/.cache/ms-playwright

COPY . .
RUN mkdir -p /app/data

EXPOSE 8000
CMD ["python", "-m", "app.main"]
