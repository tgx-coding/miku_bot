# 1. 基础镜像
FROM python:3.10-slim

# 2. 设置环境变量（不生成 pyc 文件，实时打印日志）
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Shanghai

# 3. 设置容器内的工作目录
WORKDIR /app

# 4. 安装系统依赖 (如果你的库需要编译 C 代码，比如某些加密库)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# 5. 复制依赖清单并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 6. 复制项目代码
COPY . .

# 7. 暴露端口 (FastAPI 默认 8000，如果你改了 8080 就写 8080)
EXPOSE 8080

# 8. 启动命令
CMD ["python", "QQ_Bot.py"]