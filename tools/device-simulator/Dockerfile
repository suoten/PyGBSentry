# PyGBSentry 内置 GB28181 设备模拟器
# 纯 Python + ffmpeg（仅用于生成测试 PS 流），无其他依赖
FROM python:3.12-alpine

# 国内网络环境切换 alpine apk 镜像源（海外部署可注释掉下一行）
RUN sed -i 's#dl-cdn.alpinelinux.org#mirrors.aliyun.com#g' /etc/apk/repositories || true \
    && apk add --no-cache ffmpeg

WORKDIR /app
COPY device_simulator.py .

# PS 流文件与 ffmpeg 缓存目录
ENV PS_FILE=/data/sample.ps
VOLUME ["/data"]

CMD ["python", "-u", "device_simulator.py"]
