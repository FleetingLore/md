# ---- 部署 ----
HOST   ?= root@160.202.47.107
DIR    ?= /var/www/md

.PHONY: setup check build serve deploy clean

# 一键安装所有依赖（先 ngspice 再 Python）
setup:
	@echo "=== ngspice ==="
	@which ngspice >/dev/null 2>&1 && echo "✓ ngspice found" || (echo "✗ ngspice not found. Run: brew install ngspice"; exit 1)
	@echo "=== Python deps ==="
	pip install -r requirements.txt
	@echo "---"
	@echo "✓ All dependencies ready."

# 检查可用工具
check:
	@echo "ngspice:   $$(ngspice --version 2>&1 | head -1 || echo 'NOT FOUND')"
	@echo "Python:    $$(python3 --version 2>&1)"
	@echo "matplotlib: $$(python3 -c 'import matplotlib;print(matplotlib.__version__)' 2>&1 || echo 'NOT FOUND')"
	@echo "mkdocs:    $$(mkdocs --version 2>&1 || echo 'NOT FOUND')"

# 构建站点
build:
	mkdocs build

# 本地预览
serve:
	mkdocs serve

# 上传
deploy: build
	rsync -avz --delete site/ $(HOST):$(DIR)/

# 清理
clean:
	rm -rf site/
