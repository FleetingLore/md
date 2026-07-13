# 部署变量
HOST   ?= root@160.202.47.107
DIR    ?= /var/www/jhljc

.PHONY: build deploy clean

# 构建站点
build:
	mkdocs build

# 上传到服务器
deploy: build
	rsync -avz --delete site/ $(HOST):$(DIR)/

# 清理构建产物
clean:
	rm -rf site/
